"""
Diff a staging crawl (crawl_heroes.py --staging) against the current live
crawled data, and detect collisions with data/overrides.yaml.

Outputs .build/crawl_diff.json consumed by review_server.py / merge_crawl.py:

  kinds.<kind>.added    — {key: new_entry}
  kinds.<kind>.removed  — {key: old_entry}
  kinds.<kind>.changed  — {key: {field: {"old": .., "new": ..}}}
  override_collisions   — override entries whose upstream data appeared or
                          changed in this crawl (per-field override vs new)

Kinds: heroes, skills, traits, assembly, bingxue. Traits are derived from
hero detail pages on both sides (same derivation as sync_canonical).

Usage:
    uv run script/diff_crawl.py            # write JSON + print summary
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import yaml

from paths import (
    HEROES_CRAWLED, SKILLS_CRAWLED, ASSEMBLY_CRAWLED, BINGXUE_CRAWLED,
    STAGING_DIR, STAGING_HEROES, STAGING_SKILLS, STAGING_ASSEMBLY, STAGING_BINGXUE,
    SKILLS_CANONICAL, OVERRIDES_YAML, CRAWL_DIFF_JSON,
)

HEROES_TRANSLATED = Path("data/heroes_translated.yaml")


def _load_yaml(path: Path, default):
    if not path.exists():
        return default
    return yaml.safe_load(path.read_text("utf-8")) or default


def _heroes_by_name(hero_list: list[dict]) -> dict[str, dict]:
    return {h["name"]: h for h in hero_list if h.get("name")}


def derive_traits(hero_list: list[dict]) -> dict[str, dict]:
    """Same derivation as crawl_heroes.sync_canonical: trait name → raw entry."""
    traits: dict[str, dict] = {}
    for h in hero_list:
        for t in h.get("traits") or []:
            name = t.get("name")
            if not name:
                continue
            if name not in traits:
                traits[name] = {
                    "name": name,
                    "description": t.get("description", ""),
                    "source_heroes": [],
                }
            if h["name"] not in traits[name]["source_heroes"]:
                traits[name]["source_heroes"].append(h["name"])
    return traits


# ---------------------------------------------------------------------------
# Entry / field diff
# ---------------------------------------------------------------------------

def _values_equal(field: str, old, new) -> bool:
    # source_heroes ordering follows index-page order — compare as sets so a
    # reshuffled hero list doesn't produce noise diffs.
    if field == "source_heroes" and isinstance(old, list) and isinstance(new, list):
        return set(old) == set(new)
    return old == new


def diff_entry(old: dict, new: dict) -> dict[str, dict]:
    """Field-level diff of two entries. Returns {field: {old, new}}."""
    fields = {}
    for f in sorted(set(old) | set(new)):
        ov, nv = old.get(f), new.get(f)
        if not _values_equal(f, ov, nv):
            fields[f] = {"old": ov, "new": nv}
    return fields


def diff_kind(old: dict[str, dict], new: dict[str, dict]) -> dict:
    added = {k: new[k] for k in new.keys() - old.keys()}
    removed = {k: old[k] for k in old.keys() - new.keys()}
    changed = {}
    for k in old.keys() & new.keys():
        fields = diff_entry(old[k], new[k])
        if fields:
            changed[k] = fields
    return {"added": added, "removed": removed, "changed": changed}


# ---------------------------------------------------------------------------
# Override collisions
# ---------------------------------------------------------------------------

def _cht_to_jp_maps() -> tuple[dict[str, str], dict[str, str]]:
    """Build CHT name → JP crawl key maps for skills and heroes.

    Override keys are usually CHT names; crawled data is keyed by JP name.
    Kanji-only names are often identical in both, so identity is the fallback.
    """
    skills_map: dict[str, str] = {}
    canonical = _load_yaml(SKILLS_CANONICAL, {})
    for jp_key, entry in canonical.items():
        cht = ((entry or {}).get("text") or {}).get("name")
        if cht:
            skills_map[cht] = jp_key

    heroes_map: dict[str, str] = {}
    translated = _load_yaml(HEROES_TRANSLATED, {})
    for jp_key, entry in translated.items():
        cht = (entry or {}).get("name")
        if cht:
            heroes_map[cht] = jp_key
    return skills_map, heroes_map


def _cfg_name_ja_maps() -> tuple[dict[str, str], dict[str, str]]:
    """CHT-server cfg.json: override CHT key → JP name (`name_ja`), when present.

    cfg is the official CHT client config. It carries name_ja ahead of game8,
    but lags the season start (overrides are authored at the FB announcement,
    before any cfg refresh) and the crawler may not re-pull it — so this is a
    best-effort suggestion source, never authoritative. Imported lazily to
    avoid a hard dependency / import cycle with build_frontend_data.
    """
    try:
        from build_frontend_data import _load_cfg_lookups
        skill_lookup, hero_lookup = _load_cfg_lookups()
    except Exception:
        return {}, {}
    skills = {k: b["name_ja"] for k, b in skill_lookup.items() if b.get("name_ja")}
    heroes = {k: b["name_ja"] for k, b in hero_lookup.items() if b.get("name_ja")}
    return skills, heroes


def _char_overlap(a: str, b: str) -> float:
    """Jaccard over characters — cheap fuzzy score for manual-confirm hints."""
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


# Match precedence for reconciling a newly-crawled entry against an
# `_action: add` override. Lower rank wins. All ranked matches are
# pre-selected in the review UI but stay user-overridable.
_LINK_VIA_RANK = {"name_jp": 0, "cfg": 1, "identity": 2, "cht_map": 3}


def build_override_links(
    overrides: dict, added: dict[str, dict[str, dict]],
) -> dict:
    """Map each added skill/hero to the override (_action: add) it likely is.

    Without this, an override-covered entry that finally shows up in the crawl
    is rendered as brand-new. Returns per-section:
        {"index": [all add-override keys],           # full manual-search list
         "added": {jp_key: {match, via, suggestions}}}
    `match` (+ `via`) is a high-confidence auto-match to pre-select; when none
    exists, `suggestions` offers fuzzy candidates the reviewer confirms by hand.
    """
    skills_cht2jp, heroes_cht2jp = _cht_to_jp_maps()
    cht2jp = {"skills": skills_cht2jp, "heroes": heroes_cht2jp}
    cfg_skills, cfg_heroes = _cfg_name_ja_maps()
    cfg_ja = {"skills": cfg_skills, "heroes": cfg_heroes}

    out: dict[str, dict] = {}
    for section in ("skills", "heroes"):
        add_ovs = {
            k: ov for k, ov in (overrides.get(section) or {}).items()
            if isinstance(ov, dict) and ov.get("_action") == "add"
        }
        # Build JP-key → (override_key, via), best via wins.
        jp_to_ov: dict[str, tuple[str, str]] = {}

        def offer(jp, ov_key, via):
            if not jp:
                return
            cur = jp_to_ov.get(jp)
            if cur is None or _LINK_VIA_RANK[via] < _LINK_VIA_RANK[cur[1]]:
                jp_to_ov[jp] = (ov_key, via)

        for ov_key, ov in add_ovs.items():
            offer(ov.get("_name_jp"), ov_key, "name_jp")
            offer(cfg_ja[section].get(ov_key), ov_key, "cfg")
            offer(ov_key, ov_key, "identity")
            offer(cht2jp[section].get(ov_key), ov_key, "cht_map")

        # Restrict to added keys, then dedup: an override offered to several
        # added keys is kept only on its best-rank claim; the rest fall back to
        # fuzzy suggestions so one override can't pre-select two cards.
        claims = {jp: jp_to_ov[jp] for jp in added.get(section, {}) if jp in jp_to_ov}
        best_jp_for_ov: dict[str, str] = {}
        for jp, (ov_key, via) in claims.items():
            cur = best_jp_for_ov.get(ov_key)
            if cur is None or _LINK_VIA_RANK[via] < _LINK_VIA_RANK[claims[cur][1]]:
                best_jp_for_ov[ov_key] = jp

        added_links: dict[str, dict] = {}
        for jp_key in added.get(section, {}):
            claim = claims.get(jp_key)
            keep = claim is not None and best_jp_for_ov.get(claim[0]) == jp_key
            suggestions: list[str] = []
            if not keep and add_ovs:
                scored = [(k, _char_overlap(jp_key, k)) for k in add_ovs]
                suggestions = [
                    k for k, s in sorted(scored, key=lambda x: x[1], reverse=True)
                    if s > 0
                ][:5]
            link = {
                "match": claim[0] if keep else None,
                "via": claim[1] if keep else None,
                "suggestions": suggestions,
            }
            # For a confident (non-fuzzy) match, attach the per-field diff so the
            # review UI can render the shared field-block inline under the link
            # bar (same shape collision cards consume). Fuzzy-only entries get
            # none — the reviewer must confirm the link before fields are shown.
            if keep:
                new_entry = added.get(section, {}).get(jp_key) or {}
                link["fields"] = _diff_add_override_fields(
                    section, add_ovs[claim[0]], new_entry,
                )
            added_links[jp_key] = link
        out[section] = {"index": sorted(add_ovs), "added": added_links}
    return out


# Override fields that have a crawled counterpart worth comparing. Fields like
# vars/brief_description/tags only exist post-translation — no upstream value.
_COMPARABLE_FIELDS = {
    "skills": ["name", "type", "rarity", "target", "activation_rate",
               "description", "commander_bonus", "source_hero"],
    "heroes": ["rarity", "cost", "faction", "clan", "gender", "stats",
               "traits", "unique_skill", "teachable_skill", "assembly_skill",
               "bingxue", "portrait"],
}

# ---------------------------------------------------------------------------
# Reconcile field partition (merge_crawl Phase 3c) — when a link binds a
# newly-crawled JP entry to an `_action: add` override, only these fields
# survive the CHT-key → JP-key re-key; everything else falls through to the
# crawl-built base (the override becomes `_action: modify` on the JP key).
# ---------------------------------------------------------------------------

# Curated-CHT fields: keep from the override → seed skills.yaml/llm cache so
# llm_translate treats the JP entry as already translated.
TRANSLATION_OWNED_SKILL_FIELDS = {
    "name", "description", "commander_description", "brief_description",
    "tags", "vars", "battle",
}

# Crawl/cfg-owned fields: drop from the override, the crawl base wins.
CRAWL_OWNED_SKILL_FIELDS = {
    "type", "rarity", "target", "activation_rate", "source_hero",
}

# No auto default — reviewer must pick; P1 (no per-field UI yet) default = keep.
NEEDS_CHOICE_SKILL_FIELDS = {"is_unique", "unique_hero"}

# Hero `add` overrides usually have no explicit `name` (it defaults to the
# override dict key); reconcile must materialize it before re-keying, else
# the raw JP string becomes the display name.
TRANSLATION_OWNED_HERO_FIELDS = {"name"}


def _diff_add_override_fields(section: str, ov: dict, new_entry: dict,
                              old_entry: dict | None = None) -> list[dict]:
    """Per-field comparison of an override against its upstream (crawl) entry.

    Returns [{field, override, new, old}] over the fields of
    `_COMPARABLE_FIELDS[section]` that the override actually defines. Shared by
    `detect_override_collisions` (collision cards) and `build_override_links`
    (matched add-override link bars) so both render the same field-block shape.
    """
    old_entry = old_entry or {}
    fields = []
    for f in _COMPARABLE_FIELDS[section]:
        if f not in ov:
            continue
        fields.append({
            "field": f,
            "override": ov.get(f),
            "new": new_entry.get(f),
            "old": old_entry.get(f),
        })
    return fields


def _confident_link_keys(override_links: dict) -> set[tuple[str, str]]:
    """(section, override_key) pairs that `build_override_links` matched with a
    confident (non-fuzzy) match. The reconcile link bar already surfaces these,
    so `detect_override_collisions` must NOT also emit a collision card for the
    same override — one UI surface, no dual-decision on the same key."""
    keys: set[tuple[str, str]] = set()
    for section, sec in (override_links or {}).items():
        for link in (sec.get("added") or {}).values():
            if link.get("match"):
                keys.add((section, link["match"]))
    return keys


def detect_override_collisions(
    overrides: dict,
    staging: dict[str, dict[str, dict]],
    current: dict[str, dict[str, dict]],
    kind_diffs: dict[str, dict],
    suppress_keys: set[tuple[str, str]] | None = None,
) -> list[dict]:
    """Find overrides whose upstream entry appeared or changed in this crawl.

    reason = "now_upstream"     — `_action: add` override, key now crawled
             "upstream_changed" — override on an entry that changed upstream

    `suppress_keys` — (section, override_key) pairs already covered by a
    confident reconcile link; skipped so the UI shows a single surface.
    """
    suppress_keys = suppress_keys or set()
    skills_cht2jp, heroes_cht2jp = _cht_to_jp_maps()
    key_maps = {"skills": skills_cht2jp, "heroes": heroes_cht2jp}
    collisions = []

    for section in ("skills", "heroes"):
        for ov_key, ov in (overrides.get(section) or {}).items():
            if not isinstance(ov, dict):
                continue
            action = ov.get("_action", "modify")
            if action == "delete":
                continue
            if (section, ov_key) in suppress_keys:
                continue  # a confident reconcile link already covers this key

            staging_key = None
            ov_jp = ov.get("_name_jp")  # durable link written by the review UI
            if ov_jp and ov_jp in staging[section]:
                staging_key = ov_jp
            elif ov_key in staging[section]:
                staging_key = ov_key
            elif key_maps[section].get(ov_key) in staging[section]:
                staging_key = key_maps[section][ov_key]
            if staging_key is None:
                continue

            diff = kind_diffs[section]
            if action == "add" and staging_key in staging[section]:
                # Entry the override introduced now exists upstream — always
                # surface, even if upstream didn't change since last crawl,
                # UNLESS it was already upstream before (steady state, no news).
                is_new_upstream = (
                    staging_key in diff["added"] or staging_key in diff["changed"]
                    or staging_key not in current[section]
                )
                if not is_new_upstream:
                    continue
                reason = "now_upstream"
            else:
                if staging_key not in diff["changed"]:
                    continue
                reason = "upstream_changed"

            new_entry = staging[section].get(staging_key) or {}
            old_entry = current[section].get(staging_key) or {}
            fields = _diff_add_override_fields(section, ov, new_entry, old_entry)
            collisions.append({
                "section": section,
                "key": ov_key,
                "staging_key": staging_key,
                "action": action,
                "reason": reason,
                "fields": fields,
                "override_only_fields": sorted(
                    f for f in ov
                    if f not in _COMPARABLE_FIELDS[section] and not f.startswith("_")
                ),
            })

    return collisions


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def compute_diff() -> dict:
    if not STAGING_HEROES.exists():
        raise FileNotFoundError(
            f"{STAGING_HEROES} not found — run: "
            "uv run script/crawl_heroes.py --detail --staging"
        )

    cur_heroes = _heroes_by_name(_load_yaml(HEROES_CRAWLED, []))
    new_heroes = _heroes_by_name(_load_yaml(STAGING_HEROES, []))

    current = {
        "heroes": cur_heroes,
        "skills": _load_yaml(SKILLS_CRAWLED, {}),
        "traits": derive_traits(list(cur_heroes.values())),
        "assembly": _load_yaml(ASSEMBLY_CRAWLED, {}),
        "bingxue": _load_yaml(BINGXUE_CRAWLED, {}),
    }
    staging = {
        "heroes": new_heroes,
        "skills": _load_yaml(STAGING_SKILLS, {}),
        "traits": derive_traits(list(new_heroes.values())),
        "assembly": _load_yaml(STAGING_ASSEMBLY, {}),
        "bingxue": _load_yaml(STAGING_BINGXUE, {}),
    }

    kinds = {k: diff_kind(current[k], staging[k]) for k in current}

    overrides = _load_yaml(OVERRIDES_YAML, {})
    override_links = build_override_links(
        overrides, {s: kinds[s]["added"] for s in ("skills", "heroes")}
    )
    # Suppress collision cards for keys a confident reconcile link already
    # covers — one UI surface, and it prevents dual override-decisions on the
    # same key (delete-via-collision + reconcile → KeyError / partial write).
    collisions = detect_override_collisions(
        overrides, staging, current, kinds,
        suppress_keys=_confident_link_keys(override_links),
    )

    stats = {
        k: {t: len(v[t]) for t in ("added", "removed", "changed")}
        for k, v in kinds.items()
    }
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "staging_dir": str(STAGING_DIR),
        "kinds": kinds,
        "override_collisions": collisions,
        "override_links": override_links,
        "stats": stats,
    }


def write_diff(diff: dict) -> None:
    CRAWL_DIFF_JSON.parent.mkdir(parents=True, exist_ok=True)
    CRAWL_DIFF_JSON.write_text(
        json.dumps(diff, ensure_ascii=False, indent=2), "utf-8"
    )


def main() -> int:
    try:
        diff = compute_diff()
    except FileNotFoundError as e:
        print(f"[diff] {e}", file=sys.stderr)
        return 2
    write_diff(diff)

    print(f"[diff] → {CRAWL_DIFF_JSON}")
    for kind, s in diff["stats"].items():
        if any(s.values()):
            print(f"  {kind:8s} +{s['added']} -{s['removed']} ~{s['changed']}")
    n_col = len(diff["override_collisions"])
    if n_col:
        print(f"  override collisions: {n_col}")
        for c in diff["override_collisions"]:
            print(f"    [{c['section']}] {c['key']} ({c['reason']})")
    if not any(any(s.values()) for s in diff["stats"].values()) and not n_col:
        print("  no changes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
