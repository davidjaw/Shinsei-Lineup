"""
Build frontend JSON from crawled + canonical YAML data.

Reads:
  data/heroes_crawled.yaml
  data/skills.yaml        (canonical)
  data/traits.yaml        (canonical)

Outputs:
  .build/heroes.json  (array of heroes)
  .build/skills.json  (array of skills)

Usage:
    python script/build_frontend_data.py
"""

import json
import re
import yaml
from pathlib import Path

from llm_core import clean_strings, load_overrides
from paths import (
    HEROES_CRAWLED, HEROES_TRANSLATED,
    SKILLS_CANONICAL, TRAITS_CANONICAL, BINGXUE_CANONICAL,
    STATUSES_YAML,
    HEROES_JSON, SKILLS_JSON, STATUSES_JSON, BINGXUE_JSON,
    BINGXUE_JP_TO_CHT_DIR,
)

# Untranslated-text warnings collected during build_skills/build_heroes.
# Surfaced at end of main() so admin sees a summary, but does not fail the
# build (check_build.py + check_coverage.py are the gatekeepers that fail CI).
_BUILD_WARNINGS: list[str] = []

# LLM skill name corrections (wrong CHT → correct CHT)
SKILL_NAME_FIXES = {
    "盤石耽々": "盤石耽耽",
    "血戰奮鬥": "浴血奮戰",
    "所向無敵": "所向披靡",
    "歸還的凱歌": "振旅凱歌",
    "文武兩道": "文武雙全",
    "破陣": "陣型崩毀",
}

# LLM alias → spec canonical name
STATUS_ALIASES = {
    "震懾": "威壓", "恐慌": "混亂", "攪亂": "混亂",
    "嘲諷": "挑釁", "挑撥": "挑釁",
    "繳械": "封擊", "計窮": "無策",
    "潰逃": "潰走", "消沈": "消沉",
    "回避": "閃避", "回生": "休養",
    "心攻": "攻心", "奇策": "奇謀",
    "反擊": "連擊",
}


def deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base. Override values win."""
    result = base.copy()
    for k, v in override.items():
        if k.startswith("_"):
            continue
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result




def _skill_stub_defaults(clean: dict) -> dict:
    """Fill in default fields for an added/replaced skill entry."""
    clean.setdefault("name_jp", "")
    clean.setdefault("vars", {})
    clean.setdefault("commander_description", "")
    clean.setdefault("source_hero", "")
    clean.setdefault("unique_hero", "")
    clean.setdefault("is_unique", bool(clean.get("unique_hero")))
    # Teachable only if explicitly has source_hero or is_teachable set
    clean.setdefault("is_teachable", bool(clean.get("source_hero")))
    clean.setdefault("is_fixed", clean.get("is_unique", False) and not clean.get("is_teachable", False))
    clean.setdefault("icon", "")
    clean.setdefault("tags", [])
    clean.setdefault("brief_description", "")
    return clean


def apply_skill_overrides(skills: list[dict], overrides: dict) -> list[dict]:
    """Apply skill overrides.

    Supported actions:
      - `modify` (default): deep-merge into existing skill matched by dict key
      - `add`: append new skill (key is JP or CHT name). Auto-dedups by same
        `name` and honors the legacy `_replaces: <jp_name>` field.
      - `replace`: drop existing skill matched by dict key (must be JP name),
        then append the entry. The symmetric "delete-then-add" form.
      - `delete`: remove existing skill matched by dict key.
    """
    skill_index = {s["name"]: i for i, s in enumerate(skills)}
    skill_index_jp = {s.get("name_jp"): i for i, s in enumerate(skills) if s.get("name_jp")}

    def _find(key: str) -> int | None:
        idx = skill_index.get(key)
        return skill_index_jp.get(key) if idx is None else idx

    def _drop(victim_key: str):
        idx = _find(victim_key)
        if idx is not None and skills[idx] is not None:
            skills[idx] = None

    for key, ov in overrides.items():
        action = ov.get("_action", "modify")
        if action == "delete":
            _drop(key)
            continue
        if action == "replace":
            _drop(key)
            clean = {k: v for k, v in ov.items() if not k.startswith("_")}
            skills.append(_skill_stub_defaults(clean))
            continue
        if action == "add":
            # Only honor explicit _replaces. Duplicate-name detection is
            # check_build.py's job — silently dropping a same-named existing
            # entry here would mask typos.
            if ov.get("_replaces"):
                _drop(ov["_replaces"])
            clean = {k: v for k, v in ov.items() if not k.startswith("_")}
            skills.append(_skill_stub_defaults(clean))
            continue
        # modify: deep merge into existing skill
        idx = _find(key)
        if idx is not None:
            clean = {k: v for k, v in ov.items() if not k.startswith("_")}
            skills[idx] = deep_merge(skills[idx], clean)

    return [s for s in skills if s is not None]


def _hero_stub_defaults(clean: dict, key: str) -> dict:
    """Fill in default fields for an added/replaced hero entry."""
    clean.setdefault("name", key)
    clean.setdefault("rarity", 5)
    clean.setdefault("cost", 0)
    clean.setdefault("faction", "")
    clean.setdefault("clan", "")
    clean.setdefault("gender", "")
    clean.setdefault("portrait", "")
    clean.setdefault("detail_url", "")
    clean.setdefault("unique_skill", "")
    clean.setdefault("teachable_skill", "")
    clean.setdefault("assembly_skill", "")
    clean.setdefault("stats", {})
    clean.setdefault("traits", [])
    return clean


def apply_hero_overrides(heroes: list[dict], overrides: dict) -> list[dict]:
    """Apply hero overrides.

    Supported actions:
      - `modify` (default): deep-merge into existing hero matched by dict key
      - `add`: append new hero. Honors legacy `_replaces: <jp_name>` and
        auto-dedups by same `name`.
      - `replace`: drop existing hero matched by dict key (must be JP name)
        then append the new entry. Symmetric delete-then-add.
      - `delete`: remove existing hero matched by dict key.
    """
    hero_index = {h["name"]: i for i, h in enumerate(heroes)}
    hero_index_jp = {h.get("name_jp"): i for i, h in enumerate(heroes) if h.get("name_jp")}

    def _find(key: str) -> int | None:
        idx = hero_index.get(key)
        return hero_index_jp.get(key) if idx is None else idx

    def _drop(victim_key: str):
        idx = _find(victim_key)
        if idx is not None and heroes[idx] is not None:
            heroes[idx] = None

    for key, ov in overrides.items():
        action = ov.get("_action", "modify")
        if action == "delete":
            _drop(key)
            continue
        if action == "replace":
            _drop(key)
            clean = {k: v for k, v in ov.items() if not k.startswith("_")}
            heroes.append(_hero_stub_defaults(clean, key))
            continue
        if action == "add":
            if ov.get("_replaces"):
                _drop(ov["_replaces"])
            clean = {k: v for k, v in ov.items() if not k.startswith("_")}
            heroes.append(_hero_stub_defaults(clean, key))
            continue
        # modify
        idx = _find(key)
        if idx is not None:
            clean = {k: v for k, v in ov.items() if not k.startswith("_")}
            heroes[idx] = deep_merge(heroes[idx], clean)

    return [h for h in heroes if h is not None]


def ensure_str(val) -> str:
    """Ensure a value is a string. Converts floats < 1 to percentage."""
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, float) and 0 < val < 1:
        return f"{val * 100:.0f}%"
    return str(val).strip() if val is not None else ""



SCALE_ALIASES = {
    "知略": "智略",
    "intellect": "智略",
    "intelligence": "智略",
    "command": "統率",
    "valor": "武勇",
    "speed": "速度",
    "charm": "魅力",
    "politics": "政務",
}


def normalize_status_refs(text: str) -> str:
    """Replace {status:alias} with {status:canonical} and {scale:alias} with {scale:canonical}."""
    def replace_status(m):
        name = m.group(1)
        canonical = STATUS_ALIASES.get(name, name)
        return f"{{status:{canonical}}}"
    def replace_scale(m):
        name = m.group(1)
        canonical = SCALE_ALIASES.get(name, name)
        return f"{{scale:{canonical}}}"
    text = re.sub(r"\{status:([^}]+)\}", replace_status, text)
    text = re.sub(r"\{scale:([^}]+)\}", replace_scale, text)
    # Fix LLM producing {var:name:%} → {var:name}%
    text = re.sub(r"\{var:(\w+):%\}", r"{var:\1}%", text)
    # Fix LLM wrapping {scale:} with redundant 受...影響
    text = re.sub(r"受\{scale:([^}]+)\}影響", r"{scale:\1}", text)
    # Also fix plain-text occurrences of known aliases
    text = text.replace("知略", "智略")
    text = text.replace("計略傷害", "謀略傷害")
    return text

def normalize_vars(vars_dict: dict) -> dict:
    """Fix scale aliases in vars (e.g., 知略 → 智略)."""
    out = {}
    for k, v in vars_dict.items():
        if isinstance(v, dict) and "scale" in v:
            scale = v["scale"]
            if isinstance(scale, list):
                scale = "/".join(str(s) for s in scale)
            scale = SCALE_ALIASES.get(scale, scale)
            v = {**v, "scale": scale}
        out[k] = v
    return out


# ---------------------------------------------------------------------------
# Post-processing: normalize all text and type issues in final output
# ---------------------------------------------------------------------------

def fix_skill_name(name: str) -> str:
    return SKILL_NAME_FIXES.get(name, name)


VALID_SKILL_TYPES = {"被動", "主動", "指揮", "突擊", "兵種", "陣法"}


def normalize_skill_type(t: str) -> str:
    if t in VALID_SKILL_TYPES:
        return t
    cleaned = t.replace("戰法", "").replace("战法", "").strip()
    return cleaned if cleaned in VALID_SKILL_TYPES else t


def postprocess_skill(skill: dict) -> dict:
    """Normalize a single skill entry after all merges/overrides."""
    skill["name"] = fix_skill_name(skill.get("name", ""))
    skill["is_event_skill"] = bool(skill.get("is_event_skill", False))
    if skill.get("type"):
        skill["type"] = normalize_skill_type(skill["type"])
    for field in ("description", "commander_description"):
        if skill.get(field):
            skill[field] = normalize_status_refs(skill[field])
    if "activation_rate" in skill:
        skill["activation_rate"] = ensure_str(skill["activation_rate"])
    if skill.get("vars"):
        skill["vars"] = normalize_vars(skill["vars"])
    return skill


def postprocess_hero(hero: dict) -> dict:
    """Normalize a single hero entry after all merges/overrides."""
    # Fix skill name references on heroes
    for field in ("unique_skill", "teachable_skill"):
        if hero.get(field):
            hero[field] = fix_skill_name(hero[field])
    for t in hero.get("traits") or []:
        if t.get("description"):
            t["description"] = normalize_status_refs(t["description"])
        if t.get("vars"):
            t["vars"] = normalize_vars(t["vars"])
        # Re-derive rank from name so overrides without an explicit rank get tiered too.
        # Overrides that explicitly set "rank" still win (deep_merge already applied).
        if not t.get("rank"):
            t["rank"] = infer_trait_rank(t.get("name") or t.get("name_jp", ""))
    return hero


def postprocess(heroes: list[dict], skills: list[dict]) -> tuple[list[dict], list[dict]]:
    """Run all post-processing on final heroes and skills lists."""
    skills = [postprocess_skill(s) for s in skills]
    heroes = [postprocess_hero(h) for h in heroes]
    heroes.sort(key=lambda h: (-h.get("rarity", 0), -h.get("cost", 0)))
    return heroes, skills


def infer_trait_rank(name: str) -> str:
    """Rule-based tier from trait name suffix:
    III → A, II → B, I → C, anything else → S.
    Match the longest suffix first to avoid 'III' matching as 'I'.
    """
    if not name:
        return "S"
    n = name.rstrip()
    for suffix, rank in (("III", "A"), ("Ⅲ", "A"),
                         ("II", "B"),  ("Ⅱ", "B"),
                         ("I", "C"),   ("Ⅰ", "C")):
        if n.endswith(suffix):
            return rank
    return "S"


def _flatten_trait(jp_name: str, tr: dict) -> dict:
    """Flatten a canonical or legacy trait entry into the frontend JSON shape."""
    # Canonical shape has text/vars/kind/passive sub-keys
    if "text" in tr:
        text = tr["text"]
        cht_name = text.get("name", jp_name)
        desc = text.get("description", "")
        vars_dict = tr.get("vars", {})
    else:
        # Legacy shape (traits_translated): flat name/description/vars
        cht_name = tr.get("name", jp_name)
        desc = tr.get("description", "")
        vars_dict = tr.get("vars", {})

    rank = infer_trait_rank(cht_name) if cht_name != jp_name else infer_trait_rank(jp_name)

    result = {
        "name": cht_name,
        "name_jp": jp_name,
        "description": desc,
        "vars": vars_dict,
        "rank": rank,
        "active": True,
    }

    # Carry affinity info through to frontend for useTroopLevels
    passive = tr.get("passive")
    if isinstance(passive, dict) and passive.get("affinity"):
        result["affinity"] = passive["affinity"]

    return result


def build_heroes(heroes_raw: list[dict], traits_data: dict, skill_name_map: dict, heroes_translated: dict) -> list[dict]:
    """traits_data: JP name → trait entry (canonical or legacy shape).
    skill_name_map: JP name → CHT name for skill reference translation.
    heroes_translated: JP name → {name, faction, clan} CHT mapping."""
    out = []
    for h in heroes_raw:
        traits = []
        for t in h.get("traits") or []:
            jp_name = t["name"]
            tr = traits_data.get(jp_name, {})
            traits.append(_flatten_trait(jp_name, tr))

        ht = heroes_translated.get(h["name"], {})
        out.append({
            "name": ht.get("name", h["name"]),
            "name_jp": h["name"],
            "rarity": int(h.get("rarity", 0)),
            "cost": int(h.get("cost", 0)),
            "faction": ht.get("faction", h.get("faction", "")),
            "clan": ht.get("clan", h.get("clan", "")),
            "gender": h.get("gender", ""),
            "portrait": h.get("portrait", ""),
            "detail_url": h.get("detail_url", ""),
            "unique_skill": skill_name_map.get(h.get("unique_skill"), h.get("unique_skill")),
            "teachable_skill": skill_name_map.get(h.get("teachable_skill"), h.get("teachable_skill")),
            "assembly_skill": h.get("assembly_skill"),
            "stats": h.get("stats", {}),
            "traits": traits,
            "bingxue": h.get("bingxue"),  # JP-direction-keyed; re-keyed to CHT in main()
        })
    return out


def split_commander_description(desc: str) -> tuple[str, str]:
    # Match patterns: 大將技：, 大將技:, 【大將技】
    m = re.search(r"[。\n\s]*(?:【大將技】|大將技[：:])\s*", desc)
    if m:
        main = desc[:m.start()].rstrip()
        commander = desc[m.end():].rstrip(" 。\n")
        return main, commander
    return desc, ""


def _extract_commander_desc(tr: dict, battle: dict) -> str:
    """Try multiple sources for commander description."""
    # 1. Explicit field in frontend
    if tr.get("commander_description"):
        return tr["commander_description"]
    # 2. bonus.commander in frontend
    bonus = tr.get("bonus", {})
    if isinstance(bonus, dict):
        cmd = bonus.get("commander", {})
        if isinstance(cmd, dict) and cmd.get("description"):
            return cmd["description"]
    # 3. bonus.commander in battle
    bonus = battle.get("bonus", {})
    if isinstance(bonus, dict):
        cmd = bonus.get("commander", {})
        if isinstance(cmd, dict) and cmd.get("description"):
            return cmd["description"]
    return ""


def build_skills(skills_data: dict) -> list[dict]:
    """Build frontend skill list from canonical data dict.
    Each entry has raw/vars/text/battle sub-keys."""
    out = []

    for key, entry in skills_data.items():
        cr = entry.get("raw", {})
        tr = entry.get("text", {})
        bt = entry.get("battle", {})
        vars_dict = entry.get("vars", {})

        tr_desc = (tr.get("description") or "").strip()
        if tr_desc:
            raw_desc = tr_desc
        else:
            raw_desc = cr.get("description", "")
            if raw_desc:
                _BUILD_WARNINGS.append(f"skill '{key}': translated description missing, falling back to JP")
        description, commander_description = split_commander_description(raw_desc)
        if not commander_description:
            commander_description = _extract_commander_desc(tr, bt)

        name_cht = tr.get("name") or key
        if not tr.get("name"):
            _BUILD_WARNINGS.append(f"skill '{key}': translated name missing, using JP key")
        is_unique = bool(cr.get("is_unique"))
        source_hero = cr.get("source_hero", "")

        out.append({
            "name": name_cht,
            "name_jp": key,
            "type": cr.get("type", tr.get("type", "")),
            "rarity": cr.get("rarity", tr.get("rarity", "")),
            "target": cr.get("target", tr.get("target", "")),
            "activation_rate": cr.get("activation_rate", tr.get("activation_rate", "")),
            "description": description,
            "commander_description": commander_description,
            "vars": vars_dict,
            "source_hero": source_hero,
            "unique_hero": source_hero if is_unique else "",
            "is_unique": is_unique,
            "is_teachable": bool(cr.get("is_teachable")),
            "is_fixed": is_unique and not cr.get("is_teachable"),
            "icon": "",
            "tags": tr.get("tags", []),
            "brief_description": tr.get("brief_description", ""),
        })

    return out


def main():
    heroes_raw = yaml.safe_load(HEROES_CRAWLED.read_text("utf-8"))

    # Load hero name translations (optional)
    heroes_translated = {}
    ht_path = HEROES_TRANSLATED
    if ht_path.exists():
        heroes_translated = yaml.safe_load(ht_path.read_text("utf-8")) or {}

    skills_data = yaml.safe_load(SKILLS_CANONICAL.read_text("utf-8")) or {}
    traits_data = yaml.safe_load(TRAITS_CANONICAL.read_text("utf-8")) or {}
    skill_name_map = {
        jp_key: entry.get("text", {}).get("name", jp_key)
        for jp_key, entry in skills_data.items()
    }

    heroes = build_heroes(heroes_raw, traits_data, skill_name_map, heroes_translated)
    skills = build_skills(skills_data)

    # Apply overrides (highest priority)
    overrides = load_overrides()
    override_count = 0
    if overrides.get("skills"):
        skills = apply_skill_overrides(skills, overrides["skills"])
        override_count += len(overrides["skills"])
    if overrides.get("heroes"):
        heroes = apply_hero_overrides(heroes, overrides["heroes"])
        override_count += len(overrides["heroes"])

    # Enrich override-added hero traits with affinity from canonical traits.yaml.
    # Override heroes have inline trait dicts that lack affinity; the canonical
    # traits.yaml (populated by migration) has the structured data.
    for h in heroes:
        for t in h.get("traits") or []:
            if t.get("affinity"):
                continue
            canon = traits_data.get(t.get("name_jp", "")) or traits_data.get(t.get("name", ""))
            if canon and isinstance(canon, dict):
                passive = canon.get("passive")
                if isinstance(passive, dict) and passive.get("affinity"):
                    t["affinity"] = passive["affinity"]

    # Post-process: normalize text, fix types, sort
    heroes, skills = postprocess(heroes, skills)

    # Build bingxue catalog + re-key each hero's bingxue from JP direction to
    # CHT direction (handles the 臨戦↔機略 localization swap) so the frontend
    # can display without knowing about the swap. Done BEFORE writing heroes.json
    # so a single write produces the final file.
    bingxue_data = yaml.safe_load(BINGXUE_CANONICAL.read_text("utf-8")) if BINGXUE_CANONICAL.exists() else {}
    bingxue_out = {}
    for jp_name, entry in (bingxue_data or {}).items():
        raw = entry.get("raw", {})
        jp_dir = raw.get("direction", "")
        cht_dir = BINGXUE_JP_TO_CHT_DIR.get(jp_dir, jp_dir)
        bingxue_out[jp_name] = {
            "name": entry.get("name") or jp_name,
            "name_jp": jp_name,
            "direction": cht_dir,
            "direction_jp": jp_dir,
            "tier": raw.get("tier", ""),
            "description": (entry.get("text") or {}).get("description", ""),
            "description_jp": raw.get("effect", ""),
            "vars": entry.get("vars") or {},
        }

    for h in heroes:
        hero_bx = h.get("bingxue")
        if not hero_bx:
            continue
        h["bingxue"] = {
            BINGXUE_JP_TO_CHT_DIR.get(jp_dir, jp_dir): groups
            for jp_dir, groups in hero_bx.items()
        }

    # Write all build artifacts
    HEROES_JSON.parent.mkdir(parents=True, exist_ok=True)
    HEROES_JSON.write_text(json.dumps(heroes, ensure_ascii=False, indent=2), "utf-8")
    SKILLS_JSON.write_text(json.dumps(skills, ensure_ascii=False, indent=2), "utf-8")
    BINGXUE_JSON.write_text(json.dumps(bingxue_out, ensure_ascii=False, indent=2), "utf-8")

    statuses_yaml = yaml.safe_load(STATUSES_YAML.read_text("utf-8"))
    STATUSES_JSON.write_text(json.dumps(statuses_yaml, ensure_ascii=False, indent=2), "utf-8")

    # Stats
    traits_with_translation = sum(
        1 for h in heroes for t in h["traits"] if t["name"] != t.get("name_jp", t["name"])
    )
    heroes_with_cht = sum(1 for h in heroes if h.get("name") != h.get("name_jp"))
    print(f"[done] {len(heroes)} heroes → {HEROES_JSON}")
    print(f"[done] {len(skills)} skills → {SKILLS_JSON}")
    print(f"[done] {len(bingxue_out)} bingxue options → {BINGXUE_JSON}")
    print(f"[info] {heroes_with_cht} hero names translated to CHT")
    print(f"[info] {traits_with_translation} traits translated to CHT")
    if override_count:
        print(f"[info] {override_count} overrides applied")

    if _BUILD_WARNINGS:
        print(f"\n[warn] {len(_BUILD_WARNINGS)} translation gaps detected during build:")
        for w in _BUILD_WARNINGS[:20]:
            print(f"  {w}")
        if len(_BUILD_WARNINGS) > 20:
            print(f"  ... and {len(_BUILD_WARNINGS) - 20} more")
        print("[hint] run: python3 script/llm_translate.py --skills    # to fill in missing translations")


if __name__ == "__main__":
    main()
