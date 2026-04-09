"""
Phase 0: Dry-run audit for the canonical skill/trait schema migration.

Reads ALL existing source YAMLs and the override layer. Reports drift,
schema fit, and what manual cleanup will be needed before Phase 1.

DOES NOT modify any existing file. DOES NOT call the LLM. Writes a single
human-readable Markdown report to .build/audit_canonical.md.

Run manually:
    python script/audit_canonical.py
"""

from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

# Audit script lives in script/, repo root is its parent
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "script"))

from models import (  # noqa: E402
    Affinity,
    BattleSkill,
    BattleTrait,
    PassiveBlock,
    PassiveBuff,
    RawSkill,
    RawTrait,
    Skill,
    TextSkill,
    TextTrait,
    Trait,
    TroopType,
)
from paths import (  # noqa: E402
    ASSEMBLY_CRAWLED,
    BUILD_DIR,
    OVERRIDES_YAML,
    SKILLS_BATTLE,
    SKILLS_CRAWLED,
    SKILLS_TRANSLATED,
    TRAITS_BATTLE,
    TRAITS_CRAWLED,
    TRAITS_TRANSLATED,
)

REPORT_PATH = BUILD_DIR / "audit_canonical.md"

ALLOWED_TROOP_TYPES = {"足輕", "弓兵", "騎兵", "鐵炮", "器械"}
LEGACY_TROOP_TYPES = {"兵器", "槍兵", "鐵砲"}  # 鐵砲 with 砲 not 炮
TROOP_TYPE_DELIMITERS = re.compile(r"[、，,/／・]")


def _load(path: Path) -> dict | list:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text("utf-8")) or {}


# ---------------------------------------------------------------------------
# Section 1: schema dry-fit
# ---------------------------------------------------------------------------

def assemble_skill(name: str, raw: dict, translated: dict, battle: dict) -> tuple[Skill | None, str | None]:
    """Try to construct a target Skill from current 3-file source data.
    Returns (skill, None) on success or (None, error_message) on failure."""
    try:
        raw_obj = RawSkill(name=name, **{k: v for k, v in raw.items() if k != "name"})
    except ValidationError as e:
        return None, f"raw: {_short_err(e)}"

    # Use translated as the canonical vars source (it has nested base/max);
    # battle's flattened vars (e.g. damage_reduction_base) are a derivation.
    vars_dict = translated.get("vars", {}) or {}

    text_payload = {k: translated.get(k) for k in (
        "name", "type", "rarity", "target", "activation_rate", "description",
        "brief_description", "tags", "commander_description"
    ) if translated.get(k) is not None}
    if "tags" not in text_payload:
        text_payload["tags"] = []
    try:
        text_obj = TextSkill(**text_payload)
    except ValidationError as e:
        return None, f"text: {_short_err(e)}"

    battle_payload = {
        "type": battle.get("type"),
        "trigger": battle.get("trigger"),
        "do": battle.get("do") or [],
        "bonus": battle.get("bonus"),
    }
    try:
        battle_obj = BattleSkill(**{k: v for k, v in battle_payload.items() if v is not None or k == "do"})
    except ValidationError as e:
        return None, f"battle: {_short_err(e)}"

    try:
        return Skill(raw=raw_obj, vars=vars_dict, text=text_obj, battle=battle_obj), None
    except ValidationError as e:
        return None, f"skill: {_short_err(e)}"


def assemble_trait(name: str, raw: dict, translated: dict, battle: dict) -> tuple[Trait | None, str | None, str]:
    """Try to construct a target Trait. Also returns the inferred kind so
    the caller can bucket it. Affinity-shaped battle entries become passive;
    trigger-shaped become triggered."""
    try:
        raw_payload = {k: raw.get(k) for k in ("description", "category", "source_heroes") if raw.get(k) is not None}
        raw_obj = RawTrait(name=name, **raw_payload)
    except ValidationError as e:
        return None, f"raw: {_short_err(e)}", "unknown"

    vars_dict = translated.get("vars", {}) or {}

    try:
        text_obj = TextTrait(name=translated.get("name") or name, description=translated.get("description") or "")
    except ValidationError as e:
        return None, f"text: {_short_err(e)}", "unknown"

    # Decide kind from battle yaml shape
    is_affinity = battle.get("category") == "troop_affinity" or "troop_type" in battle or "level" in battle
    has_trigger = "trigger" in battle and battle.get("trigger")

    kind: str
    passive_obj: PassiveBlock | None = None
    battle_obj: BattleTrait | None = None

    if is_affinity:
        kind = "passive"
        # Coerce troop_type (string or list) into a list, then validate against vocab
        tt_raw = battle.get("troop_type")
        if isinstance(tt_raw, str):
            parts = [p.strip() for p in TROOP_TYPE_DELIMITERS.split(tt_raw) if p.strip()]
        elif isinstance(tt_raw, list):
            parts = list(tt_raw)
        else:
            parts = []
        # Normalize legacy 鐵砲 → 鐵炮 for the dry-fit (audit will still flag the original)
        normalized = ["鐵炮" if p == "鐵砲" else p for p in parts]
        try:
            affinity = Affinity(
                troop_types=normalized,
                level=int(battle.get("level", 0)),
                level_cap_bonus=int(battle.get("max_level_bonus", battle.get("level_cap_bonus", 0)) or 0),
            )
            passive_obj = PassiveBlock(affinity=affinity, buffs=[])
        except ValidationError as e:
            return None, f"affinity: {_short_err(e)}", kind
    elif has_trigger:
        kind = "triggered"
        try:
            battle_obj = BattleTrait(trigger=battle.get("trigger"), do=battle.get("do") or [])
        except ValidationError as e:
            return None, f"battle: {_short_err(e)}", kind
    else:
        # Trait has no battle data at all — can't classify yet
        return None, "no battle data; needs manual review", "needs_review"

    try:
        return Trait(raw=raw_obj, vars=vars_dict, text=text_obj, kind=kind, passive=passive_obj, battle=battle_obj), None, kind
    except ValidationError as e:
        return None, f"trait: {_short_err(e)}", kind


def _short_err(e: ValidationError) -> str:
    """One-line summary of a Pydantic validation error."""
    errs = e.errors()
    if not errs:
        return str(e)
    parts = []
    for err in errs[:3]:
        loc = ".".join(str(x) for x in err.get("loc", []))
        parts.append(f"{loc}={err.get('msg', '?')}")
    suffix = f" (+{len(errs) - 3} more)" if len(errs) > 3 else ""
    return "; ".join(parts) + suffix


# ---------------------------------------------------------------------------
# Section 2: vars drift
# ---------------------------------------------------------------------------

def vars_drift(translated: dict, battle: dict) -> dict:
    """Compare a translated entry's vars vs the battle entry's vars.
    Returns {only_in_translated, only_in_battle, mismatched, base_max_split}."""
    t_vars = translated.get("vars") or {}
    b_vars = battle.get("vars") or {}

    t_keys = set(t_vars.keys())
    b_keys = set(b_vars.keys())

    # Detect base/max split: translated has 'damage_rate', battle has
    # 'damage_rate_base' + 'damage_rate_max' instead.
    base_max_split = []
    for tk, tv in t_vars.items():
        if isinstance(tv, dict) and "base" in tv and "max" in tv:
            if f"{tk}_base" in b_vars or f"{tk}_max" in b_vars:
                base_max_split.append(tk)

    only_in_t = t_keys - b_keys
    only_in_b = b_keys - t_keys
    # Filter out the base_max split keys from "only in" lists
    for k in base_max_split:
        only_in_t.discard(k)
        only_in_b.discard(f"{k}_base")
        only_in_b.discard(f"{k}_max")

    mismatched = {}
    for k in t_keys & b_keys:
        if t_vars[k] != b_vars[k]:
            mismatched[k] = (t_vars[k], b_vars[k])

    return {
        "only_in_translated": sorted(only_in_t),
        "only_in_battle": sorted(only_in_b),
        "mismatched": mismatched,
        "base_max_split": base_max_split,
    }


# ---------------------------------------------------------------------------
# Section 7: override trait migration preview
# ---------------------------------------------------------------------------

# Regex to extract troop affinity info from override trait descriptions
TROOP_LEVEL_RE = re.compile(
    r"(?P<type>足輕|弓兵|騎兵|鐵炮|鐵砲|器械|兵器|槍兵)等級.{0,3}(?:增加|上升|提升|\+)\s*(?P<level>\d+)"
)
LEVEL_CAP_RE = re.compile(r"等級上限.{0,3}(?:增加|提升|\+)\s*(?P<bonus>\d+)")


def classify_override_trait(trait: dict) -> dict:
    """Try to convert an override-inline trait dict into a top-level trait
    entry. Returns {status, proposed, reason}."""
    name = trait.get("name", "?")
    desc = trait.get("description", "") or ""

    # Affinity inference
    troop_matches = TROOP_LEVEL_RE.findall(desc)
    cap_match = LEVEL_CAP_RE.search(desc)

    if troop_matches:
        # Collect (type, level) pairs
        troop_types = []
        levels = []
        for tt, lv in troop_matches:
            normalized = "鐵炮" if tt == "鐵砲" else tt
            if normalized in ALLOWED_TROOP_TYPES:
                troop_types.append(normalized)
                levels.append(int(lv))
            else:
                return {"status": "MANUAL_FIX", "name": name,
                        "reason": f"unsupported troop type '{tt}' in description"}
        if len(set(levels)) > 1:
            return {"status": "NEEDS_REVIEW", "name": name,
                    "reason": f"multiple distinct levels {levels} in one description; pick aggregation rule"}
        cap_bonus = int(cap_match.group("bonus")) if cap_match else 0
        return {
            "status": "AUTO_OK",
            "name": name,
            "kind": "passive",
            "proposed": {
                "passive": {
                    "affinity": {
                        "troop_types": list(dict.fromkeys(troop_types)),
                        "level": levels[0],
                        "level_cap_bonus": cap_bonus,
                    }
                }
            },
        }

    # Non-affinity → can't auto-classify; flag for manual review
    return {
        "status": "NEEDS_REVIEW",
        "name": name,
        "reason": "no recognizable troop affinity pattern; needs human classification (passive %buff vs triggered)",
    }


# ---------------------------------------------------------------------------
# Audit driver
# ---------------------------------------------------------------------------

def run() -> None:
    out: list[str] = []
    write = out.append

    write("# Canonical Schema Migration: Phase 0 Audit\n")
    write(f"_Generated by `script/audit_canonical.py` — does not modify any source file._\n")

    # Load all sources
    skills_crawled = _load(SKILLS_CRAWLED) or {}
    skills_translated = _load(SKILLS_TRANSLATED) or {}
    skills_battle = _load(SKILLS_BATTLE) or {}
    traits_crawled = _load(TRAITS_CRAWLED) or {}
    traits_translated = _load(TRAITS_TRANSLATED) or {}
    traits_battle = _load(TRAITS_BATTLE) or {}
    overrides = _load(OVERRIDES_YAML) or {}
    assembly = _load(ASSEMBLY_CRAWLED) or {}

    write(f"**Source counts**: "
          f"{len(skills_crawled)} skills crawled / "
          f"{len(skills_translated)} translated / "
          f"{len(skills_battle)} battle · "
          f"{len(traits_crawled)} traits crawled / "
          f"{len(traits_translated)} translated / "
          f"{len(traits_battle)} battle · "
          f"{len(assembly)} assembly skills · "
          f"{len(overrides.get('heroes', {}))} hero overrides / "
          f"{len(overrides.get('skills', {}))} skill overrides\n")

    # ----- Section 1: Schema dry-fit ---------------------------------------
    write("\n## 1. Schema dry-fit\n")
    write("Attempts to assemble each entry into the target Pydantic model. "
          "Failures here are entries whose current data shape is missing required fields.\n")

    skill_fits = 0
    skill_fails: list[tuple[str, str]] = []
    for name, raw in skills_crawled.items():
        translated = skills_translated.get(name, {})
        battle = skills_battle.get(name, {})
        if not translated:
            skill_fails.append((name, "missing translated entry"))
            continue
        obj, err = assemble_skill(name, raw, translated, battle)
        if obj:
            skill_fits += 1
        else:
            skill_fails.append((name, err or "unknown"))

    write(f"\n### Skills\n- ✅ fit: **{skill_fits} / {len(skills_crawled)}**\n- ❌ fail: **{len(skill_fails)}**\n")
    if skill_fails:
        write("\n<details><summary>Failing skills</summary>\n\n")
        for n, err in skill_fails[:50]:
            write(f"- `{n}` — {err}\n")
        if len(skill_fails) > 50:
            write(f"- _...and {len(skill_fails) - 50} more_\n")
        write("\n</details>\n")

    trait_fits = 0
    trait_fails: list[tuple[str, str]] = []
    trait_kind_buckets: Counter = Counter()
    for name, raw in traits_crawled.items():
        translated = traits_translated.get(name, {})
        battle = traits_battle.get(name, {})
        if not translated:
            trait_fails.append((name, "missing translated entry"))
            continue
        obj, err, kind = assemble_trait(name, raw, translated, battle)
        trait_kind_buckets[kind] += 1
        if obj:
            trait_fits += 1
        else:
            trait_fails.append((name, err or "unknown"))

    write(f"\n### Traits\n- ✅ fit: **{trait_fits} / {len(traits_crawled)}**\n- ❌ fail: **{len(trait_fails)}**\n")
    if trait_fails:
        write("\n<details><summary>Failing traits</summary>\n\n")
        for n, err in trait_fails[:50]:
            write(f"- `{n}` — {err}\n")
        if len(trait_fails) > 50:
            write(f"- _...and {len(trait_fails) - 50} more_\n")
        write("\n</details>\n")

    # ----- Section 2: Vars drift -------------------------------------------
    write("\n## 2. Vars drift (translated.vars vs battle.vars)\n")
    write("Strongest evidence for the 'shared vars at entry level' hypothesis. "
          "Drift means the same logical number is being maintained in two places and may diverge.\n")

    drift_summary: dict[str, dict] = {}
    base_max_total = 0
    pure_drift = 0  # Entries with mismatched/orphan keys NOT explained by base/max split
    for domain, translated_dict, battle_dict in (
        ("skills", skills_translated, skills_battle),
        ("traits", traits_translated, traits_battle),
    ):
        domain_drift = []
        for name, t_entry in translated_dict.items():
            b_entry = battle_dict.get(name, {})
            if not (t_entry.get("vars") or b_entry.get("vars")):
                continue
            d = vars_drift(t_entry, b_entry)
            base_max_total += len(d["base_max_split"])
            if d["only_in_translated"] or d["only_in_battle"] or d["mismatched"]:
                pure_drift += 1
                domain_drift.append((name, d))
        drift_summary[domain] = domain_drift

    write(f"\n- **base/max-split vars** (translated has nested `{{base, max}}`, battle has flattened `_base`/`_max`): "
          f"**{base_max_total}** instances. This is structural divergence (not value drift). "
          "The Phase 1 schema collapses these by keeping the nested form.\n")
    write(f"- **pure drift** (vars present in only one side OR mismatched values, after accounting for base/max split): "
          f"**{pure_drift}** entries.\n")

    for domain, items in drift_summary.items():
        if not items:
            continue
        write(f"\n<details><summary>{domain} with pure drift ({len(items)})</summary>\n\n")
        for name, d in items[:30]:
            bits = []
            if d["only_in_translated"]:
                bits.append(f"only-in-text: {d['only_in_translated']}")
            if d["only_in_battle"]:
                bits.append(f"only-in-battle: {d['only_in_battle']}")
            if d["mismatched"]:
                bits.append(f"mismatched: {list(d['mismatched'].keys())}")
            write(f"- `{name}` — {' · '.join(bits)}\n")
        if len(items) > 30:
            write(f"- _...and {len(items) - 30} more_\n")
        write("\n</details>\n")

    # ----- Section 3: Trait kind auto-classification -----------------------
    write("\n## 3. Trait kind auto-classification\n")
    write("Buckets every trait into `passive` (always-on, troop affinity or %buff) "
          "or `triggered` (engine event). Entries with no battle data go to `needs_review`.\n")
    write(f"\n- passive: **{trait_kind_buckets.get('passive', 0)}**\n"
          f"- triggered: **{trait_kind_buckets.get('triggered', 0)}**\n"
          f"- needs_review: **{trait_kind_buckets.get('needs_review', 0)}**\n"
          f"- unknown (validation error): **{trait_kind_buckets.get('unknown', 0)}**\n")

    # List the needs_review explicitly so user can act on them
    needs_review_list = []
    for name, raw in traits_crawled.items():
        battle = traits_battle.get(name, {})
        is_affinity = battle.get("category") == "troop_affinity" or "troop_type" in battle
        has_trigger = bool(battle.get("trigger"))
        if not is_affinity and not has_trigger:
            needs_review_list.append(name)
    if needs_review_list:
        write(f"\n<details><summary>Traits flagged needs_review ({len(needs_review_list)})</summary>\n\n")
        for n in needs_review_list:
            desc = (traits_translated.get(n, {}) or {}).get("description") or (traits_crawled.get(n, {}) or {}).get("description") or ""
            write(f"- `{n}` — {desc[:80]}\n")
        write("\n</details>\n")

    # ----- Section 4: Closed troop vocabulary violations -------------------
    write("\n## 4. Closed troop vocabulary violations\n")
    write(f"Allowed: `{sorted(ALLOWED_TROOP_TYPES)}`. Anything else is a violation.\n")

    vocab_violations: list[tuple[str, str]] = []
    for name, b in traits_battle.items():
        tt = b.get("troop_type")
        if tt is None:
            continue
        values = []
        if isinstance(tt, str):
            values = [p.strip() for p in TROOP_TYPE_DELIMITERS.split(tt) if p.strip()]
        elif isinstance(tt, list):
            values = list(tt)
        for v in values:
            if v not in ALLOWED_TROOP_TYPES:
                vocab_violations.append((name, v))

    write(f"\nTotal violations: **{len(vocab_violations)}**\n")
    if vocab_violations:
        write("\n| trait | bad value | suggested |\n|---|---|---|\n")
        for name, val in vocab_violations:
            suggestion = "鐵炮" if val == "鐵砲" else "(human review)"
            write(f"| `{name}` | `{val}` | {suggestion} |\n")

    # ----- Section 5: String-as-list bugs ----------------------------------
    write("\n## 5. String-as-list `troop_type` bugs\n")
    string_troop = [(name, b.get("troop_type")) for name, b in traits_battle.items()
                    if isinstance(b.get("troop_type"), str)]
    write(f"\nTotal: **{len(string_troop)}** entries store `troop_type` as a string instead of a list.\n")
    if string_troop:
        write("\n<details><summary>Affected traits</summary>\n\n")
        for n, v in string_troop:
            write(f"- `{n}` → `{v}`\n")
        write("\n</details>\n")

    # ----- Section 6: max_level_bonus legacy -------------------------------
    write("\n## 6. `max_level_bonus` legacy field\n")
    legacy_uses = [(name, b.get("max_level_bonus")) for name, b in traits_battle.items()
                   if "max_level_bonus" in b]
    write(f"\nFound **{len(legacy_uses)}** uses of the model-invented `max_level_bonus` field. "
          "Phase 1 will rename to `level_cap_bonus`.\n")
    if legacy_uses:
        write("\n<details><summary>Affected traits</summary>\n\n")
        for n, v in legacy_uses:
            write(f"- `{n}` → `{v}`\n")
        write("\n</details>\n")

    # ----- Section 7: Override trait migration preview ---------------------
    write("\n## 7. Override trait migration preview\n")
    write("For each override-authored hero with inline traits, attempts to lift each "
          "trait into a top-level entry and infer its `kind` + affinity from the "
          "description.\n")

    override_heroes = (overrides.get("heroes") or {})
    auto_ok: list[dict] = []
    needs_review: list[dict] = []
    manual_fix: list[dict] = []

    for hero_name, hero_block in override_heroes.items():
        traits_inline = hero_block.get("traits") or []
        for t in traits_inline:
            res = classify_override_trait(t)
            res["hero"] = hero_name
            if res["status"] == "AUTO_OK":
                auto_ok.append(res)
            elif res["status"] == "NEEDS_REVIEW":
                needs_review.append(res)
            else:
                manual_fix.append(res)

    write(f"\n- ✅ AUTO_OK: **{len(auto_ok)}** (mechanically convertible)\n"
          f"- ⚠️ NEEDS_REVIEW: **{len(needs_review)}** (human classification required)\n"
          f"- ❌ MANUAL_FIX: **{len(manual_fix)}** (unsupported tokens / contradictions)\n")

    if auto_ok:
        write("\n<details><summary>AUTO_OK entries</summary>\n\n")
        for r in auto_ok:
            aff = r["proposed"]["passive"]["affinity"]
            write(f"- `{r['name']}` (on `{r['hero']}`) → "
                  f"types={aff['troop_types']} level={aff['level']} cap_bonus={aff['level_cap_bonus']}\n")
        write("\n</details>\n")
    if needs_review:
        write("\n<details><summary>NEEDS_REVIEW entries</summary>\n\n")
        for r in needs_review:
            write(f"- `{r['name']}` (on `{r['hero']}`) — {r['reason']}\n")
        write("\n</details>\n")
    if manual_fix:
        write("\n<details><summary>MANUAL_FIX entries</summary>\n\n")
        for r in manual_fix:
            write(f"- `{r['name']}` (on `{r['hero']}`) — {r['reason']}\n")
        write("\n</details>\n")

    # ----- Section 8: Hero reference orphans -------------------------------
    write("\n## 8. Hero reference orphans\n")
    write("Hero skill/trait name references that don't resolve to any source entry.\n")

    skill_universe = set(skills_crawled.keys()) | set(skills_translated.keys()) | set((overrides.get("skills") or {}).keys())
    trait_universe = set(traits_crawled.keys()) | set(traits_translated.keys())
    # Override trait names (currently inline) — collect them
    for hero_name, hero_block in override_heroes.items():
        for t in hero_block.get("traits") or []:
            if t.get("name"):
                trait_universe.add(t["name"])

    # Heroes come from heroes_crawled.yaml (a list)
    heroes_crawled = yaml.safe_load((ROOT / "data" / "heroes_crawled.yaml").read_text("utf-8")) or []
    orphans: list[str] = []
    for h in heroes_crawled:
        for ref_field in ("unique_skill", "teachable_skill"):
            ref = h.get(ref_field)
            if ref and ref not in skill_universe:
                orphans.append(f"hero `{h.get('name')}` {ref_field}=`{ref}` (not in any skills source)")
        for t in h.get("traits") or []:
            tn = t.get("name")
            if tn and tn not in trait_universe:
                orphans.append(f"hero `{h.get('name')}` trait=`{tn}` (not in any traits source)")

    write(f"\nTotal orphans: **{len(orphans)}**\n")
    if orphans:
        write("\n<details><summary>List</summary>\n\n")
        for o in orphans[:50]:
            write(f"- {o}\n")
        if len(orphans) > 50:
            write(f"- _...and {len(orphans) - 50} more_\n")
        write("\n</details>\n")

    # ----- Section 9: Assembly skills survey -------------------------------
    write("\n## 9. Assembly skills survey\n")
    write("Assembly skills (`assembly_skills_crawled.yaml`) currently have no LLM "
          "translation pipeline. Confirms whether they need one.\n")

    assembly_fields: Counter = Counter()
    for name, entry in assembly.items():
        for k in (entry or {}).keys():
            assembly_fields[k] += 1
    write(f"\n- Total entries: **{len(assembly)}**\n- Field frequencies: {dict(assembly_fields)}\n")
    has_description = any((e or {}).get("description") for e in assembly.values())
    write(f"- Any entry has a description? **{'YES' if has_description else 'NO'}**\n")
    if not has_description:
        write("- → Assembly skills carry only `name` + `source_heroes`. Phase 1 just renames "
              "the file to `data/assembly_skills.yaml`; no canonical schema needed.\n")

    # ----- Verdict ---------------------------------------------------------
    write("\n## Verdict (for human review)\n")
    write("Use these numbers to gate Phase 1:\n")
    write(f"- Skills schema fit: **{skill_fits}/{len(skills_crawled)}** "
          f"({100 * skill_fits / max(len(skills_crawled), 1):.0f}%)\n")
    write(f"- Traits schema fit: **{trait_fits}/{len(traits_crawled)}** "
          f"({100 * trait_fits / max(len(traits_crawled), 1):.0f}%)\n")
    write(f"- Pure vars drift entries (post base/max accounting): **{pure_drift}**\n")
    write(f"- Trait kind auto-classified: "
          f"**{trait_kind_buckets.get('passive', 0) + trait_kind_buckets.get('triggered', 0)} / "
          f"{sum(trait_kind_buckets.values())}**\n")
    write(f"- Override trait AUTO_OK / NEEDS_REVIEW / MANUAL_FIX: "
          f"**{len(auto_ok)} / {len(needs_review)} / {len(manual_fix)}**\n")
    write(f"- Closed troop vocab violations: **{len(vocab_violations)}**\n")
    write(f"- Hero reference orphans: **{len(orphans)}**\n")

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("".join(out), encoding="utf-8")
    print(f"[audit] wrote {REPORT_PATH}")
    print(f"[audit] skills fit {skill_fits}/{len(skills_crawled)}, traits fit {trait_fits}/{len(traits_crawled)}")


if __name__ == "__main__":
    run()
