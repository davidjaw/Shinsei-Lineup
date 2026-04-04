"""
Build frontend JSON from crawled + translated YAML data.

Reads:
  data/heroes_crawled.yaml
  data/skills_crawled.yaml
  data/skills_translated.yaml
  data/traits_translated.yaml

Outputs:
  data/heros.json   (array of heroes)
  data/skills.json  (array of skills)

Usage:
    python script/build_frontend_data.py
"""

import json
import re
import yaml
from pathlib import Path

HEROES_INPUT = "data/heroes_crawled.yaml"
HEROES_TRANSLATED = "data/heroes_translated.yaml"
SKILLS_CRAWLED = "data/skills_crawled.yaml"
SKILLS_TRANSLATED = "data/skills_translated.yaml"
TRAITS_TRANSLATED = "data/traits_translated.yaml"
STATUSES_INPUT = "data/statuses.yaml"
OVERRIDES_INPUT = "data/overrides.yaml"
HEROES_OUTPUT = ".build/heros.json"
SKILLS_OUTPUT = ".build/skills.json"

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
    "鐵壁": "抵禦", "反擊": "連擊",
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


def load_overrides() -> dict:
    """Load overrides.yaml if it exists. Returns {skills: {}, heroes: []}."""
    p = Path(OVERRIDES_INPUT)
    if not p.exists():
        return {}
    data = yaml.safe_load(p.read_text("utf-8"))
    return clean_strings(data) if isinstance(data, dict) else {}


def apply_skill_overrides(skills: list[dict], overrides: dict) -> list[dict]:
    """Apply skill overrides: modify existing or add new skills."""
    skill_index = {s["name"]: i for i, s in enumerate(skills)}
    skill_index_jp = {s["name_jp"]: i for i, s in enumerate(skills)}

    for key, ov in overrides.items():
        action = ov.get("_action", "modify")
        if action == "delete":
            idx = skill_index.get(key) or skill_index_jp.get(key)
            if idx is not None:
                skills[idx] = None
            continue
        if action == "add":
            clean = {k: v for k, v in ov.items() if not k.startswith("_")}
            clean.setdefault("name_jp", "")
            clean.setdefault("vars", {})
            clean.setdefault("commander_description", "")
            clean.setdefault("source_hero", "")
            clean.setdefault("unique_hero", "")
            clean.setdefault("is_unique", bool(clean.get("unique_hero")))
            clean.setdefault("is_teachable", not ov.get("is_event_skill", False))
            clean.setdefault("is_fixed", clean.get("is_unique", False) and not clean.get("is_teachable", False))
            clean.setdefault("icon", "")
            clean.setdefault("tags", [])
            clean.setdefault("brief_description", "")
            skills.append(clean)
            continue
        # modify: deep merge into existing skill
        idx = skill_index.get(key) or skill_index_jp.get(key)
        if idx is not None:
            clean = {k: v for k, v in ov.items() if not k.startswith("_")}
            skills[idx] = deep_merge(skills[idx], clean)

    return [s for s in skills if s is not None]


def apply_hero_overrides(heroes: list[dict], overrides: dict) -> list[dict]:
    """Apply hero overrides: modify existing or add new heroes."""
    hero_index = {h["name"]: i for i, h in enumerate(heroes)}

    for key, ov in overrides.items():
        action = ov.get("_action", "modify")
        if action == "delete":
            idx = hero_index.get(key)
            if idx is not None:
                heroes[idx] = None
            continue
        if action == "add":
            clean = {k: v for k, v in ov.items() if not k.startswith("_")}
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
            heroes.append(clean)
            continue
        # modify
        idx = hero_index.get(key)
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


def clean_strings(obj):
    """Recursively strip trailing whitespace from all string values."""
    if isinstance(obj, str):
        return obj.strip()
    if isinstance(obj, dict):
        return {k: clean_strings(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_strings(v) for v in obj]
    return obj


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
    # Also fix plain-text occurrences of known aliases
    text = text.replace("知略", "智略")
    return text

def normalize_vars(vars_dict: dict) -> dict:
    """Fix scale aliases in vars (e.g., 知略 → 智略)."""
    out = {}
    for k, v in vars_dict.items():
        if isinstance(v, dict) and "scale" in v:
            v = {**v, "scale": SCALE_ALIASES.get(v["scale"], v["scale"])}
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
    return hero


def postprocess(heroes: list[dict], skills: list[dict]) -> tuple[list[dict], list[dict]]:
    """Run all post-processing on final heroes and skills lists."""
    skills = [postprocess_skill(s) for s in skills]
    heroes = [postprocess_hero(h) for h in heroes]
    heroes.sort(key=lambda h: (-h.get("rarity", 0), -h.get("cost", 0)))
    return heroes, skills


TRAIT_RANKS = ["S", "A", "B", "C"]


def build_heroes(heroes_raw: list[dict], traits_translated: dict, skill_name_map: dict, heroes_translated: dict) -> list[dict]:
    """skill_name_map: JP name → CHT name for skill reference translation.
    heroes_translated: JP name → {name, faction, clan} CHT mapping."""
    out = []
    for h in heroes_raw:
        traits = []
        for i, t in enumerate(h.get("traits") or []):
            jp_name = t["name"]
            tr = traits_translated.get(jp_name, {})
            traits.append({
                "name": tr.get("name", jp_name),
                "name_jp": jp_name,
                "description": tr.get("description", t.get("description", "")),
                "vars": tr.get("vars", {}),
                "rank": TRAIT_RANKS[i] if i < len(TRAIT_RANKS) else "C",
                "active": True,
            })

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


def build_skills(crawled: dict, translated: dict) -> list[dict]:
    out = []

    for key in crawled:
        cr = crawled.get(key, {})
        tr = translated.get(key, {})

        raw_desc = tr.get("description", cr.get("description", ""))
        description, commander_description = split_commander_description(raw_desc)

        name_cht = tr.get("name", key)
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
            "vars": tr.get("vars", {}),
            "source_hero": source_hero,
            "unique_hero": source_hero if is_unique else "",
            "is_unique": is_unique,
            "is_teachable": bool(cr.get("is_teachable")),
            "is_fixed": is_unique and not cr.get("is_teachable"),
            "icon": "",
            "tags": tr.get("tags", []),
            "brief_description": tr.get("brief_description", ""),
        })

    missing = set(translated.keys()) - set(crawled.keys())
    if missing:
        print(f"[warn] {len(missing)} skills in translated but not crawled: {missing}")

    return out


def main():
    heroes_raw = yaml.safe_load(Path(HEROES_INPUT).read_text("utf-8"))
    crawled = yaml.safe_load(Path(SKILLS_CRAWLED).read_text("utf-8"))
    translated = yaml.safe_load(Path(SKILLS_TRANSLATED).read_text("utf-8"))
    traits_translated = yaml.safe_load(Path(TRAITS_TRANSLATED).read_text("utf-8"))

    # Load hero name translations (optional)
    heroes_translated = {}
    ht_path = Path(HEROES_TRANSLATED)
    if ht_path.exists():
        heroes_translated = yaml.safe_load(ht_path.read_text("utf-8")) or {}

    # Build JP→CHT skill name map from translated data
    skill_name_map = {jp_key: tr.get("name", jp_key) for jp_key, tr in translated.items()}

    heroes = build_heroes(heroes_raw, traits_translated, skill_name_map, heroes_translated)
    skills = build_skills(crawled, translated)

    # Apply overrides (highest priority)
    overrides = load_overrides()
    override_count = 0
    if overrides.get("skills"):
        skills = apply_skill_overrides(skills, overrides["skills"])
        override_count += len(overrides["skills"])
    if overrides.get("heroes"):
        heroes = apply_hero_overrides(heroes, overrides["heroes"])
        override_count += len(overrides["heroes"])

    # Post-process: normalize text, fix types, sort
    heroes, skills = postprocess(heroes, skills)

    Path(HEROES_OUTPUT).parent.mkdir(parents=True, exist_ok=True)
    Path(HEROES_OUTPUT).write_text(
        json.dumps(heroes, ensure_ascii=False, indent=2), "utf-8"
    )
    Path(SKILLS_OUTPUT).write_text(
        json.dumps(skills, ensure_ascii=False, indent=2), "utf-8"
    )

    # Build statuses.json from YAML
    statuses_yaml = yaml.safe_load(Path("data/statuses.yaml").read_text("utf-8"))
    Path(HEROES_OUTPUT).parent.joinpath("statuses.json").write_text(
        json.dumps(statuses_yaml, ensure_ascii=False, indent=2), "utf-8"
    )

    # Stats
    traits_with_translation = sum(
        1 for h in heroes for t in h["traits"] if t["name"] != t.get("name_jp", t["name"])
    )
    heroes_with_cht = sum(1 for h in heroes if h.get("name") != h.get("name_jp"))
    print(f"[done] {len(heroes)} heroes → {HEROES_OUTPUT}")
    print(f"[done] {len(skills)} skills → {SKILLS_OUTPUT}")
    print(f"[info] {heroes_with_cht} hero names translated to CHT")
    print(f"[info] {traits_with_translation} traits translated to CHT")
    if override_count:
        print(f"[info] {override_count} overrides applied")


if __name__ == "__main__":
    main()
