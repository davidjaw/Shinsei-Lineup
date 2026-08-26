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
import os
import re
import yaml
from pathlib import Path

from llm_core import load_overrides
from merge_sources import opencc_s2tw
from paths import (
    BUILD_DIR,
    CFG_CURRENT_JSON,
    HEROES_CRAWLED, HEROES_TRANSLATED,
    SKILLS_CANONICAL, TRAITS_CANONICAL, BINGXUE_CANONICAL,
    STATUSES_YAML,
    HEROES_JSON, SKILLS_JSON, STATUSES_JSON, BINGXUE_JSON,
    BINGXUE_JP_TO_CHT_DIR,
    PROTOTYPE_DIR,
)

# When CFG_AUTHORITATIVE=1 (default), cfg.json wins over LLM output for
# names and top-level metadata (skill names, target, brief_description,
# type, hero clan/faction/cost/rarity/unique_skill). Description text
# still comes from the LLM in Phase 3 — Phase 4 will swap in cfg-derived
# descriptions. Set CFG_AUTHORITATIVE=0 to roll back to legacy behavior.
CFG_AUTHORITATIVE = os.environ.get("CFG_AUTHORITATIVE", "1") == "1"

# cfg.skill_kind is zh-hans; the build emits zh-hant `type`.
# Key set must stay in sync with the SKILL_KINDS / TRAIT_KINDS / BINGXUE_KINDS /
# ASSEMBLY_KINDS constants in merge_sources.py — when cfg adds a new skill_kind,
# update both files.
ZH_HANS_TO_HANT_TYPE = {
    "主动": "主動", "被动": "被動", "指挥": "指揮", "突击": "突擊",
    "阵法": "陣法", "兵种": "兵種",
    "特性": "特性", "天赋": "天賦", "评定众": "評定眾",
}

CFG_HERO_DRIFT_PATH = BUILD_DIR / "cfg_hero_drift.yaml"
CFG_OVERRIDE_CONFLICTS_PATH = BUILD_DIR / "cfg_override_conflicts.yaml"

# cfg.tips / short_tips / target_tips wrap highlighted spans in
# <font color='...'>...</font>. The frontend renders text content (not HTML),
# so tags surface as literal characters in brief descriptions. Strip at the
# cfg-read boundary; mirrors the same helper in merge_sources.py.
_FONT_TAG_RE = re.compile(r"</?font[^>]*>", re.IGNORECASE)


def _strip_font_tags(text):
    if not text:
        return text
    return _FONT_TAG_RE.sub("", text)


def _load_cfg_lookups() -> tuple[dict, dict]:
    """Single cfg.json read → (skill_by_hant, hero_by_hant).

    Both lookups are zh-hant-keyed projections of cfg.json, used so
    override-added entries (which bypass the prototype path) can still
    resolve cfg fields by their CHT key. This re-parses cfg.json because
    `data/prototype/*_proto.yaml` is game8-bounded — entries that exist
    only on the cfg side (e.g. heroes/skills not yet on game8.jp) never
    reach the prototype layer, so the lookup must come from cfg directly.
    """
    if not CFG_CURRENT_JSON.exists():
        return {}, {}
    cfg = json.loads(CFG_CURRENT_JSON.read_text("utf-8"))
    ml = cfg.get("multi_lang", [])
    by_hans = {e["zh-hans"]: e for e in ml if e.get("zh-hans")}
    skill_by_name = {s["name"]: s for s in cfg.get("skill", []) if s.get("name")}
    hero_by_name = {h["name"]: h for h in cfg.get("hero", []) if h.get("name")}

    def hant_of(hans):
        if not hans:
            return None
        e = by_hans.get(hans) or {}
        return e.get("zh-hant") or opencc_s2tw(hans)

    skill_out: dict = {}
    hero_out: dict = {}
    for entry in ml:
        hant = entry.get("zh-hant")
        if not hant:
            continue
        ml_id = entry.get("id")
        ja = entry.get("ja")

        cfg_skill = skill_by_name.get(ml_id)
        if cfg_skill:
            skill_out[hant] = {
                "id": cfg_skill.get("id"),
                "name_ja": ja,
                "skill_kind": cfg_skill.get("skill_kind"),
                "short_tips_zh_hant": _strip_font_tags(hant_of(cfg_skill.get("short_tips"))),
                "target_tips_zh_hant": _strip_font_tags(hant_of(cfg_skill.get("target_tips"))),
            }

        cfg_hero = hero_by_name.get(ml_id)
        if cfg_hero:
            hero_out[hant] = {
                "id": cfg_hero.get("id"),
                "name_ja": ja,
                "camp_zh_hant": hant_of(cfg_hero.get("camp")),
                "family_zh_hant": hant_of(cfg_hero.get("family")),
                "cost": cfg_hero.get("cost"),
                "star": cfg_hero.get("star"),
                "born_skill_zh_hant": hant_of(cfg_hero.get("born_skill")),
            }

    return skill_out, hero_out


def _cfg_fields_for_skill_override(key: str, lookup: dict) -> dict:
    """Override-shaped projection of the cfg skill block keyed by zh-hant."""
    block = lookup.get(key)
    if not block:
        return {}
    out: dict = {}
    if block.get("short_tips_zh_hant"):
        out["brief_description"] = block["short_tips_zh_hant"]
    if block.get("target_tips_zh_hant"):
        out["target"] = block["target_tips_zh_hant"]
    kind_hans = block.get("skill_kind")
    if kind_hans in ZH_HANS_TO_HANT_TYPE:
        out["type"] = ZH_HANS_TO_HANT_TYPE[kind_hans]
    if block.get("id") is not None:
        out["cfg_id"] = block["id"]
    if block.get("name_ja"):
        out["name_jp"] = block["name_ja"]
    return out


def _cfg_fields_for_hero_override(key: str, lookup: dict) -> dict:
    block = lookup.get(key)
    if not block:
        return {}
    out: dict = {}
    if block.get("camp_zh_hant"):
        out["faction"] = block["camp_zh_hant"]
    if block.get("family_zh_hant"):
        out["clan"] = block["family_zh_hant"]
    if block.get("cost") is not None:
        out["cost"] = block["cost"]
    if block.get("star") is not None:
        out["rarity"] = block["star"]
    if block.get("born_skill_zh_hant"):
        out["unique_skill"] = block["born_skill_zh_hant"]
    if block.get("id") is not None:
        out["cfg_id"] = block["id"]
    if block.get("name_ja"):
        out["name_jp"] = block["name_ja"]
    return out


def _classify_add_overrides(
    overrides_section: dict,
    cfg_lookup: dict,
    g8_jp_keys: set,
) -> dict:
    """Bucket `_action: add` overrides by data-source coverage.

    Lifecycle of an override-added entry (TW server runs ahead of JP, so
    new heroes/skills land in override first via OCR → override.py):

      pre_launch  — neither cfg nor game8 know about it yet; override is
                    the only source.
      cfg_only    — cfg has identity + zh-hant metadata, game8 doesn't yet;
                    override fields cfg covers can be trimmed.
      cfg_and_g8  — both upstream sources have it; the entire override
                    entry can usually be deleted (or downgraded to modify
                    if a specific field still needs project-specific tweaks).
    """
    out = {"pre_launch": [], "cfg_only": [], "cfg_and_g8": []}
    for key, ov in (overrides_section or {}).items():
        if not isinstance(ov, dict) or ov.get("_action") != "add":
            continue
        cfg_block = cfg_lookup.get(key)
        if not cfg_block:
            out["pre_launch"].append(key)
            continue
        ja = cfg_block.get("name_ja")
        if ja and ja in g8_jp_keys:
            out["cfg_and_g8"].append(key)
        else:
            out["cfg_only"].append(key)
    return out


def _print_coverage_hint(scope: str, cls: dict) -> None:
    total = sum(len(v) for v in cls.values())
    if not total:
        return
    print(f"[info] override-added {scope} lifecycle ({total} entries):")
    bucket_msg = [
        ("cfg_and_g8", "in cfg + in game8 → override entry likely removable"),
        ("cfg_only",   "in cfg only       → cfg-covered fields can be trimmed"),
        ("pre_launch", "pre-launch        → override is the only source"),
    ]
    for k, msg in bucket_msg:
        items = cls[k]
        if not items:
            continue
        sample = ", ".join(items[:5])
        more = f" (+ {len(items) - 5} more)" if len(items) > 5 else ""
        print(f"  {len(items):>3}  {msg}: {sample}{more}")


def _detect_override_cfg_conflicts(overrides_dict: dict, cfg_fields_fn) -> list[dict]:
    """Detect conflicts where the override AND cfg both define a field with
    differing values. Read-only — does NOT mutate the override dict.

    The cfg-fill itself happens in `apply_skill_overrides` / `apply_hero_overrides`
    on the per-entry `clean` dict (not on the user's YAML data), so override
    structure stays a clean snapshot of user intent.

    Conflicts are reported, never auto-resolved: the warning often means the
    override predates the official cfg release and may now be redundant.
    """
    conflicts: list[dict] = []
    for key, ov in (overrides_dict or {}).items():
        if not isinstance(ov, dict):
            continue
        if ov.get("_action") == "delete":
            continue
        cfg_fields = cfg_fields_fn(key)
        if not cfg_fields:
            continue
        for field, cfg_val in cfg_fields.items():
            ov_val = ov.get(field)
            if ov_val is not None and ov_val != cfg_val:
                conflicts.append({
                    "key": key,
                    "field": field,
                    "override": ov_val,
                    "cfg": cfg_val,
                })
    return conflicts

# LLM skill name corrections (wrong CHT → correct CHT). Active only when
# CFG_AUTHORITATIVE=0 (rollback path); cfg.json supplies these names directly
# in the default cfg-on path. Phase 5 retires these alongside the flag.
SKILL_NAME_FIXES = {
    "血戰奮鬥": "浴血奮戰",
    "所向無敵": "所向披靡",
    "歸還的凱歌": "振旅凱歌",
}

# LLM alias → spec canonical name
STATUS_ALIASES = {
    "震懾": "威壓", "恐慌": "混亂", "攪亂": "混亂",
    "嘲諷": "挑釁", "挑撥": "挑釁",
    "繳械": "封擊", "計窮": "無策",
    "潰逃": "潰走", "消沈": "消沉",
    "回避": "閃避", "回生": "休養",
    "心攻": "攻心", "奇策": "奇謀",
}


def _load_prototype(name: str) -> dict:
    """Load data/prototype/{name}_proto.yaml. Empty dict if missing."""
    path = PROTOTYPE_DIR / f"{name}_proto.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text("utf-8")) or {}


def _index_proto_skills_by_jp(proto: dict) -> dict:
    """Return {jp_key: proto_entry} keyed on BOTH the effective and the
    pre-rename JP name. Lets canonical lookups (which use the original
    game8 key) find a renamed prototype entry without a separate map.
    """
    out = {}
    for eff_jp, p in proto.items():
        out[eff_jp] = p
        sc = p.get("source_correction_applied") or {}
        renamed_from = sc.get("renamed_from")
        if renamed_from:
            out[renamed_from] = p
    return out


def _build_skill_name_map(skills_data: dict, proto_by_jp: dict) -> dict:
    """JP key (orig and corrected) → CHT name. Used to translate hero
    unique_skill / teachable_skill text refs."""
    name_map = {
        jp_key: entry.get("text", {}).get("name", jp_key)
        for jp_key, entry in skills_data.items()
    }
    if CFG_AUTHORITATIVE:
        for eff_jp, p in proto_by_jp.items():
            cfg_name = (p.get("cfg") or {}).get("name_zh_hant")
            if cfg_name:
                name_map[eff_jp] = cfg_name
    return name_map


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


def _normalize_replaces(replaces) -> list[str]:
    """`_replaces` may be a single str (legacy) or a list. Always return a
    deduplicated list preserving order."""
    if not replaces:
        return []
    items = [replaces] if isinstance(replaces, str) else list(replaces)
    return list(dict.fromkeys(items))




def _skill_stub_defaults(clean: dict) -> dict:
    """Fill in default fields for an added/replaced skill entry."""
    # name_jp = None for override-added skills means "no JP source key" — the
    # frontend's CHT⇄JP fallback (`?? cht`, `s.name === key`) only fires on
    # nullish, so emitting "" would defeat both legs and write empty keys to
    # user profiles. None is the honest "absent" sentinel.
    clean.setdefault("name_jp", None)
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


def _apply_overrides(
    items: list[dict],
    overrides: dict,
    stub_defaults_fn,
    cfg_fields_fn=None,
) -> list[dict]:
    """Generic override applier shared by skills and heroes.

    Supported actions:
      - `modify` (default): deep-merge into existing item matched by dict key
      - `add`: append new item. Auto-dedups via legacy `_replaces` field.
      - `replace`: drop existing item matched by dict key, then append.
      - `delete`: remove existing item matched by dict key.

    `stub_defaults_fn(clean, key)` fills in default fields for added entries.
    `cfg_fields_fn(key)` (optional) fills missing fields from cfg on add/replace.
    """
    name_index = {it["name"]: i for i, it in enumerate(items)}
    jp_index = {it.get("name_jp"): i for i, it in enumerate(items) if it.get("name_jp")}

    def _find(key: str) -> int | None:
        idx = name_index.get(key)
        return jp_index.get(key) if idx is None else idx

    def _drop(victim_key: str):
        idx = _find(victim_key)
        if idx is not None and items[idx] is not None:
            items[idx] = None

    def _build_new(key: str, ov: dict) -> dict:
        aliases = _normalize_replaces(ov.get("_replaces"))
        for old in aliases:
            _drop(old)
        clean = {k: v for k, v in ov.items() if not k.startswith("_")}
        if aliases:
            clean["aliases"] = aliases
        if cfg_fields_fn:
            for field, cfg_val in (cfg_fields_fn(key) or {}).items():
                clean.setdefault(field, cfg_val)
        return stub_defaults_fn(clean, key)

    for key, ov in overrides.items():
        action = ov.get("_action", "modify")
        if action == "delete":
            _drop(key)
        elif action == "replace":
            _drop(key)
            items.append(_build_new(key, ov))
        elif action == "add":
            # Only honor explicit _replaces. Duplicate-name detection is
            # check_build.py's job — silently dropping a same-named existing
            # entry here would mask typos.
            items.append(_build_new(key, ov))
        else:  # modify: deep merge into existing item
            idx = _find(key)
            if idx is not None:
                clean = {k: v for k, v in ov.items() if not k.startswith("_")}
                items[idx] = deep_merge(items[idx], clean)

    return [it for it in items if it is not None]


def apply_skill_overrides(
    skills: list[dict], overrides: dict, cfg_fields_fn=None,
) -> list[dict]:
    return _apply_overrides(
        skills, overrides,
        stub_defaults_fn=lambda clean, _key: _skill_stub_defaults(clean),
        cfg_fields_fn=cfg_fields_fn,
    )


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


def apply_hero_overrides(
    heroes: list[dict], overrides: dict, cfg_fields_fn=None,
) -> list[dict]:
    return _apply_overrides(
        heroes, overrides,
        stub_defaults_fn=_hero_stub_defaults,
        cfg_fields_fn=cfg_fields_fn,
    )


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


def build_heroes(
    heroes_raw: list[dict],
    traits_data: dict,
    skill_name_map: dict,
    heroes_translated: dict,
    proto_heroes: dict | None = None,
    drift_log: list | None = None,
) -> list[dict]:
    """traits_data: JP name → trait entry (canonical or legacy shape).
    skill_name_map: JP name → CHT name for skill reference translation.
    heroes_translated: JP name → {name, faction, clan} CHT mapping.
    proto_heroes: JP name → prototype entry (for CFG_AUTHORITATIVE path).
    drift_log: optional sink for game8/cfg cost+rarity disagreements.
    """
    proto_heroes = proto_heroes or {}
    out = []
    for h in heroes_raw:
        jp = h["name"]
        traits = []
        for t in h.get("traits") or []:
            jp_name = t["name"]
            tr = traits_data.get(jp_name, {})
            traits.append(_flatten_trait(jp_name, tr))

        ht = heroes_translated.get(jp, {})
        cfg = (proto_heroes.get(jp) or {}).get("cfg") or {}

        name = ht.get("name", jp)
        faction = ht.get("faction", h.get("faction", ""))
        clan = ht.get("clan", h.get("clan", ""))
        cost = int(h.get("cost") or 0)
        rarity = int(h.get("rarity") or 0)

        if CFG_AUTHORITATIVE and cfg:
            if cfg.get("name_zh_hant"):
                name = cfg["name_zh_hant"]
            if cfg.get("camp_zh_hant"):
                faction = cfg["camp_zh_hant"]
            if cfg.get("family_zh_hant"):
                clan = cfg["family_zh_hant"]
            if cfg.get("cost") is not None and cfg["cost"] != cost:
                if drift_log is not None:
                    drift_log.append({"hero": jp, "field": "cost", "game8": cost, "cfg": cfg["cost"]})
                cost = cfg["cost"]
            if cfg.get("star") is not None and cfg["star"] != rarity:
                if drift_log is not None:
                    drift_log.append({"hero": jp, "field": "rarity", "game8": rarity, "cfg": cfg["star"]})
                rarity = cfg["star"]

        entry = {
            "name": name,
            "name_jp": jp,
            "rarity": rarity,
            "cost": cost,
            "faction": faction,
            "clan": clan,
            "gender": h.get("gender", ""),
            "portrait": h.get("portrait", ""),
            "detail_url": h.get("detail_url", ""),
            "unique_skill": skill_name_map.get(h.get("unique_skill"), h.get("unique_skill")),
            "teachable_skill": skill_name_map.get(h.get("teachable_skill"), h.get("teachable_skill")),
            "assembly_skill": h.get("assembly_skill"),
            "stats": h.get("stats", {}),
            "traits": traits,
            "bingxue": h.get("bingxue"),  # JP-direction-keyed; re-keyed to CHT in main()
        }
        if CFG_AUTHORITATIVE and cfg.get("id") is not None:
            entry["cfg_id"] = cfg["id"]
        out.append(entry)
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


def build_skills(skills_data: dict, proto_by_jp: dict | None = None) -> list[dict]:
    """Build frontend skill list from canonical data dict.
    Each entry has raw/vars/text/battle sub-keys.
    proto_by_jp: optional {jp_key: proto_entry} keyed on both eff and orig
    JP. When CFG_AUTHORITATIVE, cfg fields override LLM names + metadata."""
    proto_by_jp = proto_by_jp or {}
    out = []

    for key, entry in skills_data.items():
        cr = entry.get("raw", {})
        tr = entry.get("text", {})
        bt = entry.get("battle", {})
        vars_dict = entry.get("vars", {})
        cfg = (proto_by_jp.get(key) or {}).get("cfg") or {}

        tr_desc = (tr.get("description") or "").strip()
        raw_desc = tr_desc or cr.get("description", "")
        description, commander_description = split_commander_description(raw_desc)
        if not commander_description:
            commander_description = _extract_commander_desc(tr, bt)

        name_cht = tr.get("name") or key
        skill_type = cr.get("type", tr.get("type", ""))
        target = cr.get("target", tr.get("target", ""))
        brief = tr.get("brief_description", "")

        if CFG_AUTHORITATIVE and cfg:
            if cfg.get("name_zh_hant"):
                name_cht = cfg["name_zh_hant"]
            if cfg.get("target_tips_zh_hant"):
                target = cfg["target_tips_zh_hant"]
            if cfg.get("short_tips_zh_hant"):
                brief = cfg["short_tips_zh_hant"]
            kind_hans = cfg.get("skill_kind")
            if kind_hans and kind_hans in ZH_HANS_TO_HANT_TYPE:
                skill_type = ZH_HANS_TO_HANT_TYPE[kind_hans]

        is_unique = bool(cr.get("is_unique"))
        source_hero = cr.get("source_hero", "")

        out_entry = {
            "name": name_cht,
            "name_jp": key,
            "type": skill_type,
            "rarity": cr.get("rarity", tr.get("rarity", "")),
            "target": target,
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
            "brief_description": brief,
        }
        if CFG_AUTHORITATIVE and cfg.get("id") is not None:
            out_entry["cfg_id"] = cfg["id"]
        out.append(out_entry)

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

    # Phase 3: when CFG_AUTHORITATIVE=1, prototype's `cfg` block overrides
    # LLM names + metadata. Loaded unconditionally so the off-path is also
    # exercised (and so future flips don't surprise).
    proto_skills = _load_prototype("skills")
    proto_skills_by_jp = _index_proto_skills_by_jp(proto_skills)
    proto_heroes = _load_prototype("heroes")

    skill_name_map = _build_skill_name_map(skills_data, proto_skills_by_jp)
    drift_log: list = []

    heroes = build_heroes(
        heroes_raw, traits_data, skill_name_map, heroes_translated,
        proto_heroes=proto_heroes, drift_log=drift_log,
    )
    skills = build_skills(skills_data, proto_by_jp=proto_skills_by_jp)

    # Apply overrides (highest priority).
    # When CFG_AUTHORITATIVE, fill missing fields on `_action: add` entries
    # from cfg, and surface override↔cfg disagreements for review. Override
    # values still win — cfg only fills via setdefault.
    overrides = load_overrides()
    override_conflicts: list[dict] = []
    skill_classification: dict = {"pre_launch": [], "cfg_only": [], "cfg_and_g8": []}
    hero_classification: dict = {"pre_launch": [], "cfg_only": [], "cfg_and_g8": []}
    skill_cfg_fn = None
    hero_cfg_fn = None
    if CFG_AUTHORITATIVE:
        cfg_skill_lookup, cfg_hero_lookup = _load_cfg_lookups()

        g8_skill_jp_keys = set(proto_skills_by_jp)
        g8_hero_jp_keys = {h.get("name") for h in heroes_raw if h.get("name")}
        skill_classification = _classify_add_overrides(
            overrides.get("skills", {}), cfg_skill_lookup, g8_skill_jp_keys,
        )
        hero_classification = _classify_add_overrides(
            overrides.get("heroes", {}), cfg_hero_lookup, g8_hero_jp_keys,
        )

        skill_cfg_fn = lambda k: _cfg_fields_for_skill_override(k, cfg_skill_lookup)
        hero_cfg_fn = lambda k: _cfg_fields_for_hero_override(k, cfg_hero_lookup)

        skill_conflicts = _detect_override_cfg_conflicts(
            overrides.get("skills", {}), skill_cfg_fn,
        )
        hero_conflicts = _detect_override_cfg_conflicts(
            overrides.get("heroes", {}), hero_cfg_fn,
        )
        override_conflicts = (
            [{"scope": "skill", **c} for c in skill_conflicts]
            + [{"scope": "hero", **c} for c in hero_conflicts]
        )

    override_count = 0
    if overrides.get("skills"):
        skills = apply_skill_overrides(skills, overrides["skills"], skill_cfg_fn)
        override_count += len(overrides["skills"])
    if overrides.get("heroes"):
        heroes = apply_hero_overrides(heroes, overrides["heroes"], hero_cfg_fn)
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
    if CFG_AUTHORITATIVE:
        print(f"[info] CFG_AUTHORITATIVE=1 (cfg.json wins for names + metadata)")
        _print_coverage_hint("heroes", hero_classification)
        _print_coverage_hint("skills", skill_classification)
        if drift_log:
            CFG_HERO_DRIFT_PATH.write_text(
                yaml.safe_dump(drift_log, allow_unicode=True, sort_keys=False),
                "utf-8",
            )
            print(f"[info] {len(drift_log)} hero cost/rarity drifts → {CFG_HERO_DRIFT_PATH}")
        elif CFG_HERO_DRIFT_PATH.exists():
            CFG_HERO_DRIFT_PATH.unlink()
        if override_conflicts:
            CFG_OVERRIDE_CONFLICTS_PATH.write_text(
                yaml.safe_dump(override_conflicts, allow_unicode=True, sort_keys=False),
                "utf-8",
            )
            print(
                f"[warn] {len(override_conflicts)} override fields differ from cfg "
                f"→ {CFG_OVERRIDE_CONFLICTS_PATH}"
            )
            print(f"       (review whether the override is now redundant — cfg may have caught up)")
        elif CFG_OVERRIDE_CONFLICTS_PATH.exists():
            CFG_OVERRIDE_CONFLICTS_PATH.unlink()
    else:
        # Stale cfg-mode artifacts from a previous =1 run shouldn't linger
        # in =0 mode — they no longer reflect the build that just ran.
        for p in (CFG_HERO_DRIFT_PATH, CFG_OVERRIDE_CONFLICTS_PATH):
            if p.exists():
                p.unlink()


if __name__ == "__main__":
    main()
