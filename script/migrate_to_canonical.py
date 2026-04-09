"""
Phase 1a: Migrate existing 3-file YAML data → canonical data/skills.yaml + data/traits.yaml.

Reads:
  - data/skills_crawled.yaml, data/skills_translated.yaml, data/skills_battle.yaml
  - data/traits_crawled.yaml, data/traits_translated.yaml, data/traits_battle.yaml
  - data/overrides.yaml (hero-inline traits only, lifted to top-level trait entries)

Writes:
  - data/skills.yaml (NEW canonical)
  - data/traits.yaml (NEW canonical)
  - .build/migration_failures.md (entries that need LLM re-run or human review)

Does NOT modify or delete any existing file. Old pipeline keeps working.

Usage:
    python script/migrate_to_canonical.py
    python script/migrate_to_canonical.py --dry-run   # only produce failures report
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "script"))

from paths import (
    BUILD_DIR,
    OVERRIDES_YAML,
    SKILLS_BATTLE,
    SKILLS_CRAWLED,
    SKILLS_TRANSLATED,
    TRAITS_BATTLE,
    TRAITS_CRAWLED,
    TRAITS_TRANSLATED,
)

ALLOWED_TROOP_TYPES = {"足輕", "弓兵", "騎兵", "鐵炮", "器械"}
TROOP_DELIM = re.compile(r"[、，,/／・]")
TROOP_NORMALIZE = {"鐵砲": "鐵炮", "兵器": "器械", "槍兵": "足輕"}  # 砲→炮, ghost→real


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text("utf-8")) or {}


def _save(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------

def migrate_skill(name: str, crawled: dict, translated: dict, battle: dict) -> tuple[dict | None, str | None]:
    """Assemble one canonical skill entry. Returns (entry, error)."""
    raw = dict(crawled)  # shallow copy
    raw.setdefault("name", name)

    if not translated:
        return None, "missing translated entry"

    # Vars: translated is canonical (has nested {base, max})
    vars_dict = translated.get("vars") or {}

    text = {}
    for k in ("name", "type", "rarity", "target", "activation_rate", "description",
              "brief_description", "tags", "commander_description", "is_event_skill"):
        v = translated.get(k)
        if v is not None:
            text[k] = v

    battle_out = {}
    for k in ("type", "trigger", "do", "bonus", "rate"):
        v = battle.get(k)
        if v is not None:
            battle_out[k] = v

    entry = {"raw": raw, "vars": vars_dict, "text": text, "battle": battle_out}
    return entry, None


# ---------------------------------------------------------------------------
# Traits
# ---------------------------------------------------------------------------

def _parse_troop_type(raw_value) -> tuple[list[str] | None, str | None]:
    """Coerce troop_type (string or list) → normalized list. Returns (list, error)."""
    if raw_value is None:
        return None, None
    if isinstance(raw_value, str):
        parts = [p.strip() for p in TROOP_DELIM.split(raw_value) if p.strip()]
    elif isinstance(raw_value, list):
        parts = list(raw_value)
    else:
        return None, f"unexpected troop_type type: {type(raw_value)}"

    normalized = []
    for p in parts:
        p = TROOP_NORMALIZE.get(p, p)
        if p not in ALLOWED_TROOP_TYPES:
            return None, f"invalid troop type '{p}' (ghost data?)"
        normalized.append(p)
    return normalized, None


def migrate_trait(name: str, crawled: dict, translated: dict, battle: dict) -> tuple[dict | None, str | None]:
    """Assemble one canonical trait entry. Returns (entry, error)."""
    raw = dict(crawled)
    raw.setdefault("name", name)

    if not translated:
        return None, "missing translated entry"

    vars_dict = translated.get("vars") or {}

    text = {
        "name": translated.get("name") or name,
        "description": translated.get("description") or "",
    }

    # Decide kind from battle shape
    is_affinity = battle.get("category") == "troop_affinity" or "troop_type" in battle or "level" in battle
    has_trigger = bool(battle.get("trigger"))

    if is_affinity:
        troop_types, err = _parse_troop_type(battle.get("troop_type"))
        if err:
            return None, err
        level = int(battle.get("level", 0))
        cap = int(battle.get("max_level_bonus", battle.get("level_cap_bonus", 0)) or 0)
        entry = {
            "raw": raw, "vars": vars_dict, "text": text,
            "kind": "passive",
            "passive": {
                "affinity": {
                    "troop_types": troop_types or [],
                    "level": level,
                    "level_cap_bonus": cap,
                },
            },
        }
        return entry, None

    if has_trigger:
        battle_out = {}
        for k in ("trigger", "do", "rate"):
            v = battle.get(k)
            if v is not None:
                battle_out[k] = v
        entry = {
            "raw": raw, "vars": vars_dict, "text": text,
            "kind": "triggered",
            "battle": battle_out,
        }
        return entry, None

    if not battle:
        return None, "no battle data; needs LLM re-run"

    # Battle exists with do[] but no top-level trigger — trigger lives inside
    # do items (e.g. 側撃, 瓶割り, 短刀の契). Treat as triggered.
    if battle.get("do"):
        battle_out = {}
        for k in ("trigger", "do", "rate"):
            v = battle.get(k)
            if v is not None:
                battle_out[k] = v
        entry = {
            "raw": raw, "vars": vars_dict, "text": text,
            "kind": "triggered",
            "battle": battle_out,
        }
        return entry, None

    return None, f"unclassifiable battle shape (keys: {list(battle.keys())})"


# ---------------------------------------------------------------------------
# Override trait extraction
# ---------------------------------------------------------------------------

TROOP_LEVEL_RE = re.compile(
    r"(?P<type>足輕|弓兵|騎兵|鐵炮|鐵砲|器械)等級.{0,3}(?:增加|上升|提升|\+)\s*(?P<level>\d+)"
)
LEVEL_CAP_RE = re.compile(r"等級上限.{0,3}(?:增加|提升|\+)\s*(?P<bonus>\d+)")


def _resolve_vars(desc: str, vars_dict: dict) -> str:
    """Replace {var:X} and {var:X:%} templates with their literal values
    so that regex-based troop inference can see the actual numbers."""
    def _repl(m):
        key = m.group(1).split(":")[0]  # strip format spec like :%
        val = vars_dict.get(key)
        if val is None:
            return m.group(0)
        if isinstance(val, dict):
            return str(val.get("base", val.get("max", "")))
        return str(val)
    return re.sub(r"\{var:([^}]+)\}", _repl, desc)


def migrate_override_trait(trait: dict) -> tuple[dict | None, str | None]:
    """Convert an override-inline trait dict to a top-level canonical entry.
    Only handles troop affinity inference; non-affinity traits are flagged
    for manual review."""
    name = trait.get("name", "?")
    desc = trait.get("description") or ""

    raw = {"name": name, "description": desc, "source_heroes": [], "source": "override"}
    text = {"name": name, "description": desc}
    vars_dict = trait.get("vars") or {}
    # Clean out the lv_up/cap_up hacks from vars
    clean_vars = {k: v for k, v in vars_dict.items() if k not in ("lv_up", "cap_up")}

    # Resolve {var:X} so regex can see literal numbers
    resolved_desc = _resolve_vars(desc, vars_dict)
    troop_matches = TROOP_LEVEL_RE.findall(resolved_desc)
    cap_match = LEVEL_CAP_RE.search(resolved_desc)

    if troop_matches:
        troop_types = []
        levels = []
        for tt, lv in troop_matches:
            tt = TROOP_NORMALIZE.get(tt, tt)
            if tt not in ALLOWED_TROOP_TYPES:
                return None, f"unsupported troop type '{tt}'"
            troop_types.append(tt)
            levels.append(int(lv))
        cap = int(cap_match.group("bonus")) if cap_match else 0
        return {
            "raw": raw, "vars": clean_vars, "text": text,
            "kind": "passive",
            "passive": {
                "affinity": {
                    "troop_types": list(dict.fromkeys(troop_types)),
                    "level": levels[0],
                    "level_cap_bonus": cap,
                },
            },
        }, None

    # Non-affinity: auto-classify by suffix.
    # Traits with I/II/III/Ⅰ/Ⅱ/Ⅲ suffix are %buff passives; others are triggered.
    has_numeral = bool(re.search(r"(?:III|II|I|Ⅲ|Ⅱ|Ⅰ)\s*$", name))
    if has_numeral:
        return {
            "raw": raw, "vars": clean_vars, "text": text,
            "kind": "passive",
            "passive": {"buffs": []},  # placeholder — will be filled by LLM re-run
        }, None
    else:
        return {
            "raw": raw, "vars": clean_vars, "text": text,
            "kind": "triggered",
            "battle": {"do": []},  # placeholder — will be filled by LLM re-run
        }, None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(dry_run: bool = False):
    skills_crawled = _load(SKILLS_CRAWLED)
    skills_translated = _load(SKILLS_TRANSLATED)
    skills_battle = _load(SKILLS_BATTLE)
    traits_crawled = _load(TRAITS_CRAWLED)
    traits_translated = _load(TRAITS_TRANSLATED)
    traits_battle = _load(TRAITS_BATTLE)
    overrides = _load(OVERRIDES_YAML)

    failures: list[str] = []

    # --- Skills ---
    skills_out = {}
    for name in skills_crawled:
        entry, err = migrate_skill(
            name,
            skills_crawled.get(name, {}),
            skills_translated.get(name, {}),
            skills_battle.get(name, {}),
        )
        if entry:
            skills_out[name] = entry
        else:
            failures.append(f"skill `{name}` — {err}")

    # Skills from translated but not crawled (edge case)
    for name in set(skills_translated) - set(skills_crawled):
        failures.append(f"skill `{name}` — in translated but not crawled (orphan translation)")

    print(f"[migrate] skills: {len(skills_out)} OK, {sum(1 for f in failures if f.startswith('skill'))} fail")

    # --- Traits ---
    traits_out = {}
    for name in traits_crawled:
        entry, err = migrate_trait(
            name,
            traits_crawled.get(name, {}),
            traits_translated.get(name, {}),
            traits_battle.get(name, {}),
        )
        if entry:
            traits_out[name] = entry
        else:
            failures.append(f"trait `{name}` — {err}")

    for name in set(traits_translated) - set(traits_crawled):
        failures.append(f"trait `{name}` — in translated but not crawled (orphan translation)")

    print(f"[migrate] traits: {len(traits_out)} OK, {sum(1 for f in failures if f.startswith('trait'))} fail")

    # --- Override traits (lift inline → top-level) ---
    override_heroes = overrides.get("heroes") or {}
    override_lifted = 0
    override_failed = 0
    for hero_name, hero_block in override_heroes.items():
        for t in hero_block.get("traits") or []:
            tname = t.get("name")
            if not tname:
                continue
            # Skip if already in traits_out (LLM-sourced takes precedence)
            if tname in traits_out:
                continue
            entry, err = migrate_override_trait(t)
            if entry:
                traits_out[tname] = entry
                override_lifted += 1
            else:
                failures.append(f"override-trait `{tname}` (on hero `{hero_name}`) — {err}")
                override_failed += 1

    print(f"[migrate] override traits lifted: {override_lifted}, failed: {override_failed}")

    # --- Write outputs ---
    if not dry_run:
        skills_path = ROOT / "data" / "skills.yaml"
        traits_path = ROOT / "data" / "traits.yaml"
        _save(skills_path, skills_out)
        _save(traits_path, traits_out)
        print(f"[migrate] wrote {skills_path} ({len(skills_out)} entries)")
        print(f"[migrate] wrote {traits_path} ({len(traits_out)} entries)")

    # --- Failures report ---
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    report_path = BUILD_DIR / "migration_failures.md"
    report = ["# Migration Failures\n",
              f"Total: **{len(failures)}** entries need attention.\n\n"]
    for f in sorted(failures):
        report.append(f"- {f}\n")
    report_path.write_text("".join(report), encoding="utf-8")
    print(f"[migrate] wrote {report_path} ({len(failures)} failures)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="only produce failures report, don't write canonical files")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
