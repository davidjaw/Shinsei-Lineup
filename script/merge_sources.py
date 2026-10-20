"""
Merge game8 (data/*_crawled.yaml) and Sialia cfg (data/cfg/cfg_current.json)
into lossless prototype YAMLs under data/prototype/, applying the manual
file data/source_corrections.yaml (corrections + alias maps).

This stage is purely deterministic — no LLM. Match confidence is logged so
later stages (llm_fill, build) can decide what to trust.

Outputs:
  data/prototype/skills_proto.yaml
  data/prototype/heroes_proto.yaml
  data/prototype/traits_proto.yaml
  data/prototype/bingxue_proto.yaml
  data/prototype/assembly_proto.yaml
  .build/source_correction_candidates.yaml   — auto-suggestions for review
  .build/key_normalization_candidates.yaml   — auto-suggestions for review
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from paths import (
    ASSEMBLY_CRAWLED,
    BINGXUE_CRAWLED,
    BUILD_DIR,
    CFG_CURRENT_JSON,
    HEROES_CRAWLED,
    PROTOTYPE_DIR,
    SKILLS_CRAWLED,
    SOURCE_CORRECTIONS_PATH,
    TRAITS_CRAWLED,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# cfg.skill_kind buckets per source kind. cfg.skill[] is a flat array
# distinguished by `skill_kind`. We only consider the kinds that map onto
# the corresponding user yaml.
SKILL_KINDS = {"主动", "被动", "指挥", "突击", "阵法", "兵种"}
TRAIT_KINDS = {"特性"}
BINGXUE_KINDS = {"天赋"}
ASSEMBLY_KINDS = {"评定众"}

# Out-of-scope kinds. 战前 = pre-battle/round-scheduled skills (疾行, 守御,
# 齊射, 破軍 etc.) that aren't user-selectable in the lineup builder. 特技 =
# 装備特技 + UI 卡框. merge_sources.py never produces entries for these.
OUT_OF_SCOPE_KINDS = {"特技", "卡框", "战前"}

# Roman numeral normalization for matching cfg.skill.name vs multi_lang.
ROMAN_MAP = {
    "Ⅰ": "I", "Ⅱ": "II", "Ⅲ": "III", "Ⅳ": "IV", "Ⅴ": "V",
    "Ⅵ": "VI", "Ⅶ": "VII", "Ⅷ": "VIII", "Ⅸ": "IX", "Ⅹ": "X",
}

# Assembly tier suffix (单字: 普 / 良 / 优). Some cfg.skill[skill_kind=评定众]
# entries are split into three quality tiers (e.g. 增强兵役普/良/优), some
# are single-tier (e.g. 别动奇袭). Tier rank for picking primary id.
ASSEMBLY_TIER_RANK = {"优": 3, "良": 2, "普": 1}


def _norm(s: str | None) -> str:
    """NFC + Unicode-roman → ASCII-roman, used for join comparisons."""
    if not s:
        return ""
    out = unicodedata.normalize("NFC", s)
    for k, v in ROMAN_MAP.items():
        out = out.replace(k, v)
    return out


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Match:
    """Result of resolving a user-side JP key to a cfg.skill / cfg.hero entry."""
    cfg_entry: dict | None
    matched_via: str   # ja_id | hans_norm | hant_norm | jp_norm | manual_alias | none
    multi_lang_id: str | None = None
    confidence: str = "none"  # high | low | none

    @property
    def hit(self) -> bool:
        return self.cfg_entry is not None


@dataclass
class CorrectionCandidate:
    kind: str       # skill | hero | trait
    jp_key: str
    issue: str
    suggested_action: dict
    evidence: dict


@dataclass
class NormalizationCandidate:
    kind: str
    user_key: str
    suggested_key: str
    cfg_id: int | None
    reason: str


@dataclass
class MergeStats:
    by_kind: dict[str, dict[str, int]] = field(default_factory=dict)
    correction_candidates: list[CorrectionCandidate] = field(default_factory=list)
    normalization_candidates: list[NormalizationCandidate] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _load_yaml(path: Path, default):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or default


def load_inputs() -> dict:
    if not CFG_CURRENT_JSON.exists():
        raise SystemExit(
            f"{CFG_CURRENT_JSON} missing. Run `npm run refresh` first."
        )
    with CFG_CURRENT_JSON.open("r", encoding="utf-8") as f:
        cfg = json.load(f)

    return {
        "cfg": cfg,
        "heroes_crawled": _load_yaml(HEROES_CRAWLED, []),
        "skills_crawled": _load_yaml(SKILLS_CRAWLED, {}),
        "traits_crawled": _load_yaml(TRAITS_CRAWLED, {}),
        "bingxue_crawled": _load_yaml(BINGXUE_CRAWLED, {}),
        "assembly_crawled": _load_yaml(ASSEMBLY_CRAWLED, {}),
        "corrections": _load_yaml(SOURCE_CORRECTIONS_PATH, {}),
    }


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


class Resolver:
    """Find a cfg.skill / cfg.hero entry from a JP-side user key."""

    def __init__(self, cfg: dict, corrections: dict):
        self.cfg = cfg
        self.corrections = corrections or {}

        ml = cfg.get("multi_lang", [])
        self.ml_by_ja = {e["ja"]: e for e in ml if "ja" in e}
        self.ml_by_hans = {e["zh-hans"]: e for e in ml if "zh-hans" in e}
        self.ml_by_id = {e["id"]: e for e in ml if "id" in e}

        skill_list = cfg.get("skill", [])
        self.cfg_skill_by_name = {s["name"]: s for s in skill_list if s.get("name")}
        self.cfg_skill_by_norm: dict[str, list[dict]] = {}
        for s in skill_list:
            if not s.get("name"):
                continue
            self.cfg_skill_by_norm.setdefault(_norm(s["name"]), []).append(s)

        hero_list = cfg.get("hero", [])
        self.cfg_hero_by_name = {h["name"]: h for h in hero_list}
        self.cfg_hero_by_norm: dict[str, list[dict]] = {}
        for h in hero_list:
            self.cfg_hero_by_norm.setdefault(_norm(h.get("name", "")), []).append(h)

    # --- skill resolution -------------------------------------------------

    def _filter_by_kind(self, candidates: list[dict], target_kinds: set[str]) -> dict | None:
        for s in candidates:
            if s.get("skill_kind") in target_kinds:
                return s
        return None

    def resolve_skill(self, jp_key: str, target_kinds: set[str]) -> Match:
        # Strategy 1: ja → multi_lang.id → cfg.skill.name (exact).
        ml = self.ml_by_ja.get(jp_key)
        if ml:
            mid = ml.get("id")
            if mid:
                s = self.cfg_skill_by_name.get(mid)
                if s and s.get("skill_kind") in target_kinds:
                    return Match(s, "ja_id", ml.get("id"), "high")

        # Strategy 2: ja → multi_lang.zh-hans → norm(cfg.skill.name).
        if ml:
            hans = ml.get("zh-hans")
            if hans:
                cands = self.cfg_skill_by_norm.get(_norm(hans), [])
                hit = self._filter_by_kind(cands, target_kinds)
                if hit:
                    return Match(hit, "hans_norm", ml.get("id"), "high")

        # Strategy 3: ja → multi_lang.zh-hant → norm(cfg.skill.name).
        if ml:
            hant = ml.get("zh-hant")
            if hant:
                cands = self.cfg_skill_by_norm.get(_norm(hant), [])
                hit = self._filter_by_kind(cands, target_kinds)
                if hit:
                    return Match(hit, "hant_norm", ml.get("id"), "high")

        # Strategy 4: norm(jp_key) → norm(cfg.skill.name) (last automatic).
        cands = self.cfg_skill_by_norm.get(_norm(jp_key), [])
        hit = self._filter_by_kind(cands, target_kinds)
        if hit:
            return Match(hit, "jp_norm", None, "low")

        # Strategy 5: manual alias (source_corrections.yaml skill_name_alias).
        alias_map = self.corrections.get("skill_name_alias", {}) or {}
        target = alias_map.get(jp_key)
        if target:
            s = self.cfg_skill_by_name.get(target)
            if s and s.get("skill_kind") in target_kinds:
                return Match(s, "manual_alias", None, "high")

        return Match(None, "none", None, "none")

    # --- hero resolution --------------------------------------------------

    def resolve_hero(self, jp_key: str) -> Match:
        ml = self.ml_by_ja.get(jp_key)
        if ml:
            mid = ml.get("id")
            if mid and mid in self.cfg_hero_by_name:
                return Match(self.cfg_hero_by_name[mid], "ja_id", mid, "high")
            hans = ml.get("zh-hans")
            if hans:
                cands = self.cfg_hero_by_norm.get(_norm(hans), [])
                if cands:
                    return Match(cands[0], "hans_norm", ml.get("id"), "high")
            hant = ml.get("zh-hant")
            if hant:
                cands = self.cfg_hero_by_norm.get(_norm(hant), [])
                if cands:
                    return Match(cands[0], "hant_norm", ml.get("id"), "high")

        cands = self.cfg_hero_by_norm.get(_norm(jp_key), [])
        if cands:
            return Match(cands[0], "jp_norm", None, "low")

        alias_map = self.corrections.get("hero_name_alias", {}) or {}
        target = alias_map.get(jp_key)
        if target and target in self.cfg_hero_by_name:
            return Match(self.cfg_hero_by_name[target], "manual_alias", None, "high")

        return Match(None, "none", None, "none")


# ---------------------------------------------------------------------------
# Merger — produces prototype entries
# ---------------------------------------------------------------------------


_FONT_TAG_RE = re.compile(r"</?font[^>]*>", re.IGNORECASE)


def _strip_font_tags(text: str | None) -> str | None:
    """cfg.tips / short_tips / target_tips wrap highlighted spans in
    <font color='...'>...</font>. The frontend renders text content, not
    HTML, so the tags would surface as literal characters. Strip them at
    the cfg-read boundary so prototype yaml stays clean."""
    if not text:
        return text
    return _FONT_TAG_RE.sub("", text)


_opencc_converter = None


def opencc_s2tw(text: str | None) -> str | None:
    """Deterministic zh-hans → zh-hant character conversion (Taiwan variant).

    Used as a fallback for cfg short_tips/target_tips fields whose zh-hans
    text has no zh-hant entry in cfg.multi_lang (~15% of cfg skills as of
    Phase 3). cfg's `tips` field is intentionally NOT routed through this
    fallback — placeholder mapping happens upstream and that work belongs
    to a future Phase 4 if it ever lands.
    """
    if not text:
        return text
    global _opencc_converter
    if _opencc_converter is None:
        from opencc import OpenCC
        _opencc_converter = OpenCC("s2tw")
    return _opencc_converter.convert(text)


def _translate_short(text: str | None, ml_index: dict, opencc_fallback: bool = False) -> str | None:
    """Best-effort zh-hans → zh-hant for short cfg fields (target_tips, etc.).

    `ml_index` is a dict zh-hans → multi_lang_entry. Returns the zh-hant if
    found in multi_lang. When `opencc_fallback=True` and the lookup misses,
    falls back to character-level OpenCC conversion.
    """
    if not text:
        return None
    e = ml_index.get(text)
    if e and e.get("zh-hant"):
        return _strip_font_tags(e["zh-hant"])
    if opencc_fallback:
        return _strip_font_tags(opencc_s2tw(text))
    return None


def _cfg_block_for_skill(resolver: Resolver, cfg_skill: dict) -> dict:
    """Build the `cfg` section of a prototype entry for a skill-like item."""
    if not cfg_skill:
        return {}
    by_hans = resolver.ml_by_hans

    name_entry = resolver.ml_by_id.get(cfg_skill.get("name")) or {}
    short_tips_hans = cfg_skill.get("short_tips")
    target_tips_hans = cfg_skill.get("target_tips")
    tips_hans = cfg_skill.get("tips")

    block = {
        "id": cfg_skill.get("id"),
        "skill_kind": cfg_skill.get("skill_kind"),
        "name_zh_hans": cfg_skill.get("name"),
        "name_zh_hant": name_entry.get("zh-hant"),
        "name_ja": name_entry.get("ja"),
        "grade": cfg_skill.get("grade"),
        "skill_buff": cfg_skill.get("skill_buff") or [],
        "effect_type_list": cfg_skill.get("effect_type_list") or [],
        "arm_limit": cfg_skill.get("arm_limit") or [],
        "icon": cfg_skill.get("icon"),
        "short_tips_zh_hans": _strip_font_tags(short_tips_hans),
        "short_tips_zh_hant": _translate_short(short_tips_hans, by_hans, opencc_fallback=True),
        "target_tips_zh_hans": _strip_font_tags(target_tips_hans),
        "target_tips_zh_hant": _translate_short(target_tips_hans, by_hans, opencc_fallback=True),
        "tips_zh_hans": _strip_font_tags(tips_hans),
        "tips_zh_hant": _translate_short(tips_hans, by_hans),
    }
    block["has_official_tips_hant"] = block["tips_zh_hant"] is not None
    return block


def _cfg_block_for_hero(resolver: Resolver, cfg_hero: dict) -> dict:
    if not cfg_hero:
        return {}
    by_hans = resolver.ml_by_hans
    name_entry = resolver.ml_by_id.get(cfg_hero.get("name")) or {}

    family_entry = by_hans.get(cfg_hero.get("family")) or {}
    camp_entry = by_hans.get(cfg_hero.get("camp")) or {}
    born_skill_entry = by_hans.get(cfg_hero.get("born_skill")) or {}
    return {
        "id": cfg_hero.get("id"),
        "name_zh_hans": cfg_hero.get("name"),
        "name_zh_hant": name_entry.get("zh-hant"),
        "name_ja": name_entry.get("ja"),
        "family_zh_hans": cfg_hero.get("family"),
        "family_zh_hant": family_entry.get("zh-hant"),
        "camp_zh_hans": cfg_hero.get("camp"),
        "camp_zh_hant": camp_entry.get("zh-hant"),
        "cost": cfg_hero.get("cost"),
        "star": cfg_hero.get("star"),
        "born_skill_zh_hans": cfg_hero.get("born_skill"),
        "born_skill_zh_hant": born_skill_entry.get("zh-hant"),
        "icon": cfg_hero.get("icon"),
        "family_icon": cfg_hero.get("family_icon"),
        "camp_icon": cfg_hero.get("camp_icon"),
    }


# ---------------------------------------------------------------------------
# Per-kind merge functions
# ---------------------------------------------------------------------------


def merge_skills(
    resolver: Resolver,
    skills_crawled: dict,
    corrections: dict,
    stats: MergeStats,
) -> dict:
    out: dict[str, dict] = {}
    confidence = Counter()
    via_counter = Counter()

    renames = (corrections.get("game8_skill_renames") or {})
    reattributions = (corrections.get("game8_skill_reattributions") or {})

    for jp_key, entry in skills_crawled.items():
        # Apply pre-merge rename: source-correction overrides the JP key.
        rename_info = renames.get(jp_key)
        effective_key = rename_info["rename_to"] if rename_info else jp_key

        match = resolver.resolve_skill(effective_key, SKILL_KINDS)
        confidence[match.confidence] += 1
        via_counter[match.matched_via] += 1

        proto = {
            "match": {
                "confidence": match.confidence,
                "matched_via": match.matched_via,
                "cfg_id": match.cfg_entry.get("id") if match.cfg_entry else None,
                "multi_lang_id": match.multi_lang_id,
            },
            "game8": entry,
            "cfg": _cfg_block_for_skill(resolver, match.cfg_entry),
        }

        # Carry corrections forward into the prototype so downstream stages
        # honour them without reading source_corrections.yaml themselves.
        applied: dict = {}
        if rename_info:
            applied["renamed_from"] = jp_key
            applied["renamed_to"] = rename_info["rename_to"]
        re_info = reattributions.get(jp_key)
        if re_info:
            applied["reattribution"] = re_info
        if applied:
            proto["source_correction_applied"] = applied

        out[effective_key] = proto

    stats.by_kind["skills"] = {
        "total": len(skills_crawled),
        "matched": confidence["high"] + confidence["low"],
        **{f"confidence_{k}": v for k, v in confidence.items()},
        **{f"via_{k}": v for k, v in via_counter.items()},
    }
    return out


def merge_heroes(
    resolver: Resolver,
    heroes_crawled: list,
    corrections: dict,
    stats: MergeStats,
) -> dict:
    out: dict[str, dict] = {}
    confidence = Counter()
    via_counter = Counter()

    renames = (corrections.get("game8_skill_renames") or {})

    for entry in heroes_crawled:
        jp_key = entry.get("name")
        if not jp_key:
            continue
        match = resolver.resolve_hero(jp_key)
        confidence[match.confidence] += 1
        via_counter[match.matched_via] += 1

        # Apply skill-rename source corrections to hero's skill-name fields,
        # so prototype carries corrected values (matches the corrected key in
        # skills_proto.yaml).
        game8_corrected = dict(entry)
        applied_renames: list[str] = []
        for fld in ("unique_skill", "teachable_skill", "assembly_skill"):
            v = game8_corrected.get(fld)
            if v and v in renames:
                game8_corrected[fld] = renames[v]["rename_to"]
                applied_renames.append(f"{fld}: {v} → {renames[v]['rename_to']}")

        proto = {
            "match": {
                "confidence": match.confidence,
                "matched_via": match.matched_via,
                "cfg_id": match.cfg_entry.get("id") if match.cfg_entry else None,
                "multi_lang_id": match.multi_lang_id,
            },
            "game8": game8_corrected,
            "cfg": _cfg_block_for_hero(resolver, match.cfg_entry),
        }
        if applied_renames:
            proto["source_correction_applied"] = {"renames": applied_renames}
        out[jp_key] = proto

        # Surface candidate when game8 unique_skill (jp) doesn't agree with
        # cfg's born_skill_ja, AND the rename is not already covered by
        # source_corrections.yaml. This auto-suggestion is the early-warning
        # for cfg drift after subsequent fetches.
        cfg_hero = match.cfg_entry
        if cfg_hero:
            cfg_born_hans = cfg_hero.get("born_skill")
            cfg_born_entry = resolver.ml_by_hans.get(cfg_born_hans) if cfg_born_hans else None
            cfg_born_ja = cfg_born_entry.get("ja") if cfg_born_entry else None
            user_unique_orig = entry.get("unique_skill")  # before correction
            user_unique_eff = game8_corrected.get("unique_skill")  # after
            already_corrected = user_unique_orig in renames
            if (
                cfg_born_ja
                and user_unique_eff
                and cfg_born_ja != user_unique_eff
                and not already_corrected
            ):
                stats.correction_candidates.append(CorrectionCandidate(
                    kind="hero_unique_skill",
                    jp_key=jp_key,
                    issue=(
                        f"game8 unique_skill={user_unique_eff!r} differs from "
                        f"cfg.born_skill_ja={cfg_born_ja!r}"
                    ),
                    suggested_action={
                        "yaml_section": "game8_skill_renames",
                        "key": user_unique_eff,
                        "rename_to": cfg_born_ja,
                    },
                    evidence={
                        "hero": jp_key,
                        "cfg_hero_id": cfg_hero.get("id"),
                        "cfg_born_skill_zh_hans": cfg_born_hans,
                        "cfg_born_skill_zh_hant": (
                            cfg_born_entry.get("zh-hant") if cfg_born_entry else None
                        ),
                    },
                ))

    stats.by_kind["heroes"] = {
        "total": len(heroes_crawled),
        "matched": confidence["high"] + confidence["low"],
        **{f"confidence_{k}": v for k, v in confidence.items()},
        **{f"via_{k}": v for k, v in via_counter.items()},
    }
    return out


def merge_traits(
    resolver: Resolver,
    traits_crawled: dict,
    corrections: dict,
    stats: MergeStats,
) -> dict:
    out: dict[str, dict] = {}
    confidence = Counter()
    via_counter = Counter()

    alias = (corrections.get("trait_key_alias") or {})

    for jp_key, entry in traits_crawled.items():
        effective_key = alias.get(jp_key, jp_key)
        match = resolver.resolve_skill(effective_key, TRAIT_KINDS)
        confidence[match.confidence] += 1
        via_counter[match.matched_via] += 1

        proto = {
            "match": {
                "confidence": match.confidence,
                "matched_via": match.matched_via,
                "cfg_id": match.cfg_entry.get("id") if match.cfg_entry else None,
                "multi_lang_id": match.multi_lang_id,
                "key_normalized_from": jp_key if effective_key != jp_key else None,
            },
            "game8": entry,
            "cfg": _cfg_block_for_skill(resolver, match.cfg_entry),
        }
        out[effective_key] = proto

        # Surface a normalization candidate if a low-confidence match looks
        # like character-mixing (same norm but different chars).
        if not match.hit:
            cfg_norm_match = resolver.cfg_skill_by_norm.get(_norm(jp_key), [])
            for cand in cfg_norm_match:
                if cand.get("skill_kind") in TRAIT_KINDS and cand["name"] != jp_key:
                    stats.normalization_candidates.append(NormalizationCandidate(
                        kind="trait",
                        user_key=jp_key,
                        suggested_key=cand["name"],
                        cfg_id=cand.get("id"),
                        reason="char-mixing or roman-numeral variant",
                    ))
                    break

    stats.by_kind["traits"] = {
        "total": len(traits_crawled),
        "matched": confidence["high"] + confidence["low"],
        **{f"confidence_{k}": v for k, v in confidence.items()},
        **{f"via_{k}": v for k, v in via_counter.items()},
    }
    return out


def merge_bingxue(
    resolver: Resolver,
    bingxue_crawled: dict,
    stats: MergeStats,
) -> dict:
    out: dict[str, dict] = {}
    confidence = Counter()
    via_counter = Counter()

    for jp_key, entry in bingxue_crawled.items():
        match = resolver.resolve_skill(jp_key, BINGXUE_KINDS)
        confidence[match.confidence] += 1
        via_counter[match.matched_via] += 1
        out[jp_key] = {
            "match": {
                "confidence": match.confidence,
                "matched_via": match.matched_via,
                "cfg_id": match.cfg_entry.get("id") if match.cfg_entry else None,
                "multi_lang_id": match.multi_lang_id,
            },
            "game8": entry,
            "cfg": _cfg_block_for_skill(resolver, match.cfg_entry),
        }

    stats.by_kind["bingxue"] = {
        "total": len(bingxue_crawled),
        "matched": confidence["high"] + confidence["low"],
        **{f"confidence_{k}": v for k, v in confidence.items()},
        **{f"via_{k}": v for k, v in via_counter.items()},
    }
    return out


def _index_assembly_by_base(cfg: dict) -> dict[str, list[dict]]:
    """Group cfg.skill[skill_kind=评定众] entries by their base name (after
    stripping `评定众` prefix and optional 普/良/优 tier suffix)."""
    out: dict[str, list[dict]] = {}
    for s in cfg.get("skill", []):
        if s.get("skill_kind") not in ASSEMBLY_KINDS:
            continue
        nm = s.get("name") or ""
        base = nm.removeprefix("评定众").strip()
        if base and base[-1] in ASSEMBLY_TIER_RANK:
            base = base[:-1]
        out.setdefault(base, []).append(s)
    return out


def merge_assembly(
    resolver: Resolver,
    assembly_crawled: dict,
    stats: MergeStats,
) -> dict:
    out: dict[str, dict] = {}
    confidence = Counter()
    via_counter = Counter()

    cfg_by_base = _index_assembly_by_base(resolver.cfg)
    ml_by_ja = resolver.ml_by_ja

    for jp_key, entry in assembly_crawled.items():
        ml = ml_by_ja.get(jp_key)
        # multi_lang.zh-hans is the bare base name (no 评定众 prefix)
        hans_base = ml.get("zh-hans") if ml else None
        candidates = cfg_by_base.get(hans_base, []) if hans_base else []

        if candidates:
            tiers: dict[str, dict] = {}
            for s in candidates:
                nm = s.get("name") or ""
                tier_suffix = nm[-1] if nm and nm[-1] in ASSEMBLY_TIER_RANK else "single"
                tiers[tier_suffix] = s
            primary = max(
                candidates,
                key=lambda s: ASSEMBLY_TIER_RANK.get(
                    (s.get("name") or "")[-1] if (s.get("name") or "") else "", 0,
                ),
            )
            cfg_block = _cfg_block_for_skill(resolver, primary)
            cfg_block["tiers"] = {
                tier: {
                    "id": s.get("id"),
                    "name_zh_hans": s.get("name"),
                    "grade": s.get("grade"),
                    "tips_zh_hans": s.get("tips"),
                }
                for tier, s in tiers.items()
            }
            confidence["high"] += 1
            via_counter["ja_hans"] += 1
            match_info = {
                "confidence": "high",
                "matched_via": "ja_hans",
                "cfg_id": primary.get("id"),
                "multi_lang_id": ml.get("id") if ml else None,
                "tier_count": len(tiers),
            }
        else:
            confidence["none"] += 1
            via_counter["none"] += 1
            cfg_block = {}
            match_info = {
                "confidence": "none",
                "matched_via": "none",
                "cfg_id": None,
                "multi_lang_id": ml.get("id") if ml else None,
            }

        out[jp_key] = {
            "match": match_info,
            "game8": entry,
            "cfg": cfg_block,
        }

    stats.by_kind["assembly"] = {
        "total": len(assembly_crawled),
        "matched": confidence["high"] + confidence["low"],
        **{f"confidence_{k}": v for k, v in confidence.items()},
        **{f"via_{k}": v for k, v in via_counter.items()},
    }
    return out


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def _yaml_dump(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            data, f, allow_unicode=True, sort_keys=False, default_flow_style=False,
        )


def write_prototype(name: str, data: dict) -> None:
    path = PROTOTYPE_DIR / f"{name}_proto.yaml"
    _yaml_dump(path, data)
    print(f"[merge_sources] wrote {path} ({len(data)} entries)")


def write_correction_candidates(stats: MergeStats) -> None:
    path = BUILD_DIR / "source_correction_candidates.yaml"
    if not stats.correction_candidates:
        if path.exists():
            path.unlink()
        return
    payload = {
        "candidates": [
            {
                "kind": c.kind,
                "jp_key": c.jp_key,
                "issue": c.issue,
                "suggested_action": c.suggested_action,
                "evidence": c.evidence,
            }
            for c in stats.correction_candidates
        ],
    }
    _yaml_dump(path, payload)
    print(
        f"[merge_sources] wrote {path} "
        f"({len(stats.correction_candidates)} candidates)"
    )


def write_normalization_candidates(stats: MergeStats) -> None:
    path = BUILD_DIR / "key_normalization_candidates.yaml"
    if not stats.normalization_candidates:
        if path.exists():
            path.unlink()
        return
    payload = {
        "candidates": [
            {
                "kind": c.kind,
                "user_key": c.user_key,
                "suggested_key": c.suggested_key,
                "cfg_id": c.cfg_id,
                "reason": c.reason,
            }
            for c in stats.normalization_candidates
        ],
    }
    _yaml_dump(path, payload)
    print(
        f"[merge_sources] wrote {path} "
        f"({len(stats.normalization_candidates)} candidates)"
    )


def print_stats(stats: MergeStats) -> None:
    print("\n[merge_sources] match statistics:")
    for kind, s in stats.by_kind.items():
        total = s.get("total", 0)
        matched = s.get("matched", 0)
        pct = (matched / total * 100.0) if total else 0.0
        print(f"  {kind:8s}  matched {matched:4d}/{total:4d}  ({pct:5.1f}%)")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    inputs = load_inputs()
    resolver = Resolver(inputs["cfg"], inputs["corrections"])
    stats = MergeStats()

    skills = merge_skills(
        resolver, inputs["skills_crawled"], inputs["corrections"], stats,
    )
    heroes = merge_heroes(
        resolver, inputs["heroes_crawled"], inputs["corrections"], stats,
    )
    traits = merge_traits(
        resolver, inputs["traits_crawled"], inputs["corrections"], stats,
    )
    bingxue = merge_bingxue(resolver, inputs["bingxue_crawled"], stats)
    assembly = merge_assembly(resolver, inputs["assembly_crawled"], stats)

    write_prototype("skills", skills)
    write_prototype("heroes", heroes)
    write_prototype("traits", traits)
    write_prototype("bingxue", bingxue)
    write_prototype("assembly", assembly)

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    write_correction_candidates(stats)
    write_normalization_candidates(stats)

    print_stats(stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
