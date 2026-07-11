"""
Apply reviewed crawl-diff decisions to the live data files.

Consumes a decisions payload (from review_server.py or a JSON file):

    {
      "changes": {
        "skills":  {"added": [...], "removed": [...], "changed": [...]},
        "heroes":  {...}, "traits": {...}, "assembly": {...}, "bingxue": {...}
      },
      "overrides": [
        {"section": "skills", "key": "越後二天",
         "entry_action": "keep" | "delete",
         "fields": {"description": {"choice": "keep"|"adopt_new"|"custom",
                                     "value": "<custom text>"}}}
      ],
      "clear_staging": true
    }

Effects:
  - approved entries merged into data/*_crawled.yaml
  - canonical raw sections updated (same semantics as crawl sync_canonical)
  - llm cache invalidated for changed skills/traits/bingxue so the next
    llm_translate run re-translates them (cache is keyed by name, not content)
  - override decisions rewrite data/overrides.yaml (custom values validated
    against template rules before ANY file is written)
  - staging dir + staging cache cleared on success (opt-out via clear_staging)

Usage:
    uv run script/merge_crawl.py decisions.json      # headless apply
    uv run script/merge_crawl.py backfill --dry-run  # list cfg_and_g8 reconcile
                                                     # candidates (no writes)
    uv run script/merge_crawl.py backfill            # reconcile them via apply
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

import yaml

from paths import (
    HEROES_CRAWLED, SKILLS_CRAWLED, ASSEMBLY_CRAWLED, BINGXUE_CRAWLED,
    STAGING_DIR, STAGING_CACHE_DIR,
    STAGING_HEROES, STAGING_SKILLS, STAGING_ASSEMBLY, STAGING_BINGXUE,
    SKILLS_CANONICAL, TRAITS_CANONICAL, BINGXUE_CANONICAL,
    OVERRIDES_YAML, STATUSES_YAML, LLM_CACHE_DIR, CRAWL_DIFF_JSON,
    HEROES_TRANSLATED,
)
from build_frontend_data import SCALE_ALIASES, _normalize_replaces
from diff_crawl import (
    _load_yaml, derive_traits, _heroes_by_name, _cht_to_jp_maps,
    TRANSLATION_OWNED_SKILL_FIELDS, NEEDS_CHOICE_SKILL_FIELDS,
    TRANSLATION_OWNED_HERO_FIELDS,
)
from llm_core import save_llm_cache

# Allowed inside {scale:}: canonical CHT stat names, the frontend's _stats
# short keys (statuses.yaml _stats — e.g. spd → 速度), and build-time
# SCALE_ALIASES keys (normalized by postprocess).
SCALE_NAMES = {"武勇", "智略", "統率", "速度", "政務", "魅力"}


def _allowed_scale_names(statuses_yaml: dict) -> set[str]:
    names = set(SCALE_NAMES) | set(SCALE_ALIASES)
    names |= set((statuses_yaml.get("_stats") or {}).keys())
    return names

# Override fields whose custom value is structured YAML, not plain text.
STRUCTURED_FIELDS = {"vars", "stats", "traits", "bingxue"}

# Description-like fields that carry {var:}/{status:}/{scale:} templates.
TEMPLATE_FIELDS = {"description", "commander_description", "commander_bonus"}

_VAR_RE = re.compile(r"\{var:([^}:]+)(?::[^}]*)?\}")
_STATUS_RE = re.compile(r"\{status:([^}]+)\}")
_SCALE_RE = re.compile(r"\{scale:([^}]+)\}")


def _save_yaml(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


# ---------------------------------------------------------------------------
# Custom-value validation
# ---------------------------------------------------------------------------

def _effective_var_keys(section: str, key: str, override_entry: dict) -> set[str]:
    """Var names visible to a template on this entry: override vars merged
    over the canonical translated entry's vars (override key may be CHT)."""
    keys = set((override_entry.get("vars") or {}).keys())
    if section != "skills":
        return keys
    canonical = _load_yaml(SKILLS_CANONICAL, {})
    entry = canonical.get(key)
    if entry is None:
        cht2jp, _ = _cht_to_jp_maps()
        entry = canonical.get(cht2jp.get(key, ""), None)
    if entry:
        keys |= set((entry.get("vars") or {}).keys())
    return keys


def validate_custom_value(
    section: str, key: str, field: str, value,
    override_entry: dict, statuses: set[str], scale_names: set[str],
) -> list[str]:
    errors = []
    prefix = f"[{section}] {key}.{field}"

    if field in STRUCTURED_FIELDS:
        if not isinstance(value, (dict, list)):
            errors.append(f"{prefix}: expected YAML mapping/list, got {type(value).__name__}")
        return errors

    if not isinstance(value, str) or not value.strip():
        errors.append(f"{prefix}: empty value")
        return errors

    if field in TEMPLATE_FIELDS:
        var_keys = _effective_var_keys(section, key, override_entry)
        for m in _VAR_RE.finditer(value):
            if m.group(1) not in var_keys:
                errors.append(f"{prefix}: {{var:{m.group(1)}}} not defined in vars")
        for m in _STATUS_RE.finditer(value):
            if m.group(1) not in statuses:
                errors.append(f"{prefix}: {{status:{m.group(1)}}} not a canonical status")
        for m in _SCALE_RE.finditer(value):
            # {scale:name} or {scale:name:value} — validate the name part
            name = m.group(1).split(":")[0]
            if name not in scale_names:
                errors.append(
                    f"{prefix}: {{scale:{name}}} not a known stat "
                    f"(canonical: {sorted(SCALE_NAMES)})"
                )
    return errors


def _validate_reconcile_skill_fields(
    jp_key: str, entry: dict, statuses: set[str], scale_names: set[str],
) -> list[str]:
    """Validate the translation-owned template/structured fields an
    `_action: add` override will seed onto `jp_key` once reconciled
    (Phase 3c). Reuses the same rules as override custom-value edits."""
    errors = []
    for field in ("description", "commander_description"):
        if field in entry:
            errors.extend(validate_custom_value(
                "skills", jp_key, field, entry[field], entry, statuses, scale_names,
            ))
    if "vars" in entry:
        errors.extend(validate_custom_value(
            "skills", jp_key, "vars", entry["vars"], entry, statuses, scale_names,
        ))
    return errors


def _check_reconcile_link(
    section: str, ov_key: str, jp_key: str, entry: dict, overrides: dict,
    added_keys: dict, crawl_base_keys: dict, statuses: set, scale_names: set,
    batch_rekey_keys: set | None = None,
) -> list[str]:
    """Phase-1 guards for a reconcile link (override is `_action: add`).

    All-or-nothing: any error here aborts the whole apply before writes.
    """
    batch_rekey_keys = batch_rekey_keys or set()
    errors: list[str] = []
    # Crawl base for jp_key must exist — either approved-added in this batch,
    # or already live (P3 backfill of an already-crawled entry). Otherwise a
    # skill would ship a phantom canonical-only entry / a hero would vanish.
    if jp_key not in added_keys[section] and jp_key not in crawl_base_keys[section]:
        errors.append(
            f"[link] {section}: jp_key {jp_key!r} is neither approved-added nor "
            f"present in the live crawl base — cannot reconcile"
        )
    # Destination JP key must not already hold a DISTINCT override, else the
    # re-key write would silently clobber curated data.
    if jp_key != ov_key and (overrides.get(section) or {}).get(jp_key) is not None:
        msg = (f"[link] {section}: destination jp_key {jp_key!r} already exists as a "
               f"distinct override — reconcile would clobber it")
        if (section, jp_key) in batch_rekey_keys:
            # A sibling link in this batch re-keys the override sitting at
            # jp_key. Chained re-keys aren't ordered here → fails safe.
            msg += (f" (a sibling link also re-keys override {jp_key!r}; chained "
                    f"re-keys aren't supported — apply them in separate batches)")
        errors.append(msg)
    if section == "skills":
        errors.extend(_validate_reconcile_skill_fields(jp_key, entry, statuses, scale_names))
    return errors


def _parse_custom(field: str, raw_value):
    """GUI sends textarea strings; structured fields are YAML-parsed here."""
    if field in STRUCTURED_FIELDS and isinstance(raw_value, str):
        return yaml.safe_load(raw_value)
    if isinstance(raw_value, str):
        return raw_value.strip()
    return raw_value


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

def _merge_dict_kind(
    current: dict, staging: dict, dec: dict,
) -> tuple[dict, list[str]]:
    """Apply added/removed/changed name lists to a name-keyed dict kind.
    Returns (merged, changed_or_added_names)."""
    merged = dict(current)
    touched = []
    for name in dec.get("added", []):
        if name in staging:
            merged[name] = staging[name]
            touched.append(name)
    for name in dec.get("changed", []):
        if name in staging:
            merged[name] = staging[name]
            touched.append(name)
    for name in dec.get("removed", []):
        merged.pop(name, None)
    return merged, touched


def _sync_canonical_raw(path: Path, names: list[str], source: dict) -> None:
    """Overwrite `raw` for the given entries, preserving text/vars/battle.
    New entries get a raw-only stub (same semantics as crawl sync_canonical)."""
    if not names:
        return
    canonical = _load_yaml(path, {})
    for name in names:
        if name not in source:
            continue
        canonical.setdefault(name, {})["raw"] = source[name]
    _save_yaml(path, canonical)


def _invalidate_llm_cache(prefix: str, names: list[str]) -> int:
    n = 0
    for name in names:
        p = LLM_CACHE_DIR / f"{prefix}_{name}.yaml"
        if p.exists():
            p.unlink()
            n += 1
    return n


# ---------------------------------------------------------------------------
# Phase 3c: reconcile `_action: add` overrides onto a linked crawl JP key.
# ---------------------------------------------------------------------------

def _trim_override_entry(entry: dict, owned_fields: set[str], extra_meta: set[str],
                         keep_fields: set[str]) -> dict:
    """Keep only translation-owned/human-choice fields + residual meta
    (`is_event_skill`, any `_`-prefixed field except `_name_jp`/`_action`,
    which are always dropped/reset by the caller) + `keep_fields` (crawl-owned
    fields the reviewer explicitly chose to keep/custom in the review UI).
    Crawl-owned fields NOT explicitly kept are dropped so the crawl-built base
    passes through unmodified."""
    # `_replaces` is materialized into a real `aliases` field by the caller
    # (build_frontend_data's modify path strips ALL `_`-fields, so it would
    # never regenerate `aliases` from a surviving `_replaces` meta key).
    kept = {}
    for k, v in entry.items():
        if k in owned_fields or k in extra_meta or k in keep_fields:
            kept[k] = v
        elif k.startswith("_") and k not in ("_name_jp", "_action", "_replaces"):
            kept[k] = v
    return kept


def _materialize_aliases(entry: dict, trimmed: dict) -> None:
    """Fold `_replaces` (+ any existing `aliases`) into a plain `aliases` field
    on the reconciled `modify` entry, preserving the old CHT names as frontend
    aliases for lineup-key stability. The modify path (`deep_merge`) strips all
    `_`-prefixed fields, so a surviving `_replaces` meta key would be lost —
    hence the conversion to a normal `aliases` field here."""
    aliases = _normalize_replaces(entry.get("aliases")) + _normalize_replaces(entry.get("_replaces"))
    if aliases:
        trimmed["aliases"] = list(dict.fromkeys(aliases))


def _reconcile_add_override(overrides: dict, section: str, ov_key: str, jp_key: str,
                            keep_fields: set[str] | None = None) -> dict:
    """Re-key an `_action: add` override from its curated CHT key to the
    crawl's JP key, flip it to `modify`, and trim it to translation-owned
    fields (+ `keep_fields`: crawl-owned fields the reviewer chose to retain).
    Returns the trimmed entry written under `jp_key` ({} if the override was an
    empty husk and got dropped entirely)."""
    keep_fields = keep_fields or set()
    sec = overrides[section]
    entry = sec.pop(ov_key)
    if section == "heroes":
        entry.setdefault("name", ov_key)  # materialize before losing the CHT key
        owned, extra_meta = TRANSLATION_OWNED_HERO_FIELDS, set()
    else:
        owned = TRANSLATION_OWNED_SKILL_FIELDS | NEEDS_CHOICE_SKILL_FIELDS
        extra_meta = {"is_event_skill"}
    trimmed = _trim_override_entry(entry, owned, extra_meta, keep_fields)
    _materialize_aliases(entry, trimmed)
    if not any(not f.startswith("_") for f in trimmed):
        return {}  # nothing project-specific survives — husk-drop
    trimmed["_action"] = "modify"
    sec[jp_key] = trimmed
    return trimmed


# Skill fields that live under skills.yaml[jp].text (vars/battle are siblings).
_SKILL_TEXT_FIELDS = ("name", "description", "commander_description",
                      "brief_description", "tags")


def _seed_canonical_skill(jp_key: str, entry: dict) -> None:
    """Write the curated CHT into skills.yaml[jp].text/vars/battle so
    build_frontend_data has a translation immediately, without waiting on
    the next llm_translate run."""
    canonical = _load_yaml(SKILLS_CANONICAL, {})
    node = canonical.setdefault(jp_key, {})
    text = node.setdefault("text", {})
    for f in _SKILL_TEXT_FIELDS:
        if f in entry:
            text[f] = entry[f]
    for f in ("vars", "battle"):
        if f in entry:
            node[f] = entry[f]
    _save_yaml(SKILLS_CANONICAL, canonical)


def _seed_skill_llm_cache(jp_key: str, entry: dict) -> None:
    """Write a cache-file hit so llm_translate's cache-only skip fires for
    this JP name (canonical `text` alone is NOT enough — see module docs)."""
    cache_entry: dict = {}
    text = {f: entry[f] for f in _SKILL_TEXT_FIELDS if f in entry}
    if text:
        cache_entry["text"] = text
    for f in ("vars", "battle"):
        if f in entry:
            cache_entry[f] = entry[f]
    save_llm_cache(f"skill_{jp_key}", cache_entry, cache_dir=LLM_CACHE_DIR)


def _seed_hero_translation(jp_key: str, name: str) -> None:
    """Write heroes_translated.yaml[jp].name + a hero_{jp} llm cache hit."""
    translated = _load_yaml(HEROES_TRANSLATED, {})
    translated.setdefault(jp_key, {})["name"] = name
    _save_yaml(HEROES_TRANSLATED, translated)
    save_llm_cache(f"hero_{jp_key}", {"name": name}, cache_dir=LLM_CACHE_DIR)


def apply_decisions(decisions: dict) -> dict:
    """Validate + apply. Returns {ok, errors, applied, followup}.
    Nothing is written if any custom-value validation fails."""
    changes = decisions.get("changes") or {}
    links = decisions.get("links") or []

    # Dedup override decisions by (section, key), last wins. A key that gets
    # dual-surfaced (collision card + reconcile-override) must collapse to ONE
    # decision, else Phase 3 would process it twice (delete-then-index KeyError).
    deduped: dict[tuple, dict] = {}
    for od in (decisions.get("overrides") or []):
        deduped[(od.get("section"), od.get("key"))] = od
    override_decisions = list(deduped.values())

    overrides = _load_yaml(OVERRIDES_YAML, {})
    statuses_yaml = _load_yaml(STATUSES_YAML, {})
    statuses = {k for k in statuses_yaml if not k.startswith("_")}
    scale_names = _allowed_scale_names(statuses_yaml)

    # ---- Phase 1: validate everything, write nothing --------------------
    errors: list[str] = []
    for od in override_decisions:
        section, key = od.get("section"), od.get("key")
        entry = (overrides.get(section) or {}).get(key)
        if entry is None:
            errors.append(f"[{section}] {key}: not found in overrides.yaml")
            continue
        if od.get("entry_action") == "delete":
            continue
        for field, fd in (od.get("fields") or {}).items():
            if fd.get("choice") != "custom":
                continue
            try:
                value = _parse_custom(field, fd.get("value"))
            except yaml.YAMLError as e:
                errors.append(f"[{section}] {key}.{field}: invalid YAML — {e}")
                continue
            fd["_parsed"] = value
            errors.extend(
                validate_custom_value(section, key, field, value, entry,
                                      statuses, scale_names)
            )
    # Live crawl-base keys + approved-added keys, for reconcile guards below.
    crawl_base_keys = {
        "skills": set(_load_yaml(SKILLS_CRAWLED, {})),
        "heroes": set(_heroes_by_name(_load_yaml(HEROES_CRAWLED, []))),
    }
    added_keys = {
        s: set((changes.get(s) or {}).get("added", [])) for s in ("skills", "heroes")
    }
    # Map reconcile links (override is `_action: add`) by their target
    # (section, jp_key). Two links onto the same target would clobber each
    # other on re-key; the set of re-keyed override keys lets the destination
    # guard name a chained sibling.
    reconcile_targets: dict[tuple, list[str]] = {}
    batch_rekey_keys: set[tuple] = set()
    for lk in links:
        section, ov_key, jp = lk.get("section"), lk.get("override_key"), lk.get("jp_key")
        if section not in ("skills", "heroes") or not jp:
            continue
        e = (overrides.get(section) or {}).get(ov_key)
        if isinstance(e, dict) and e.get("_action") == "add":
            reconcile_targets.setdefault((section, jp), []).append(ov_key)
            batch_rekey_keys.add((section, ov_key))
    for (section, jp), ov_keys in reconcile_targets.items():
        if len(ov_keys) > 1:
            errors.append(
                f"[link] {section}: {len(ov_keys)} reconcile links target the same "
                f"jp_key {jp!r} ({', '.join(map(repr, ov_keys))}) — would clobber"
            )
    for lk in links:
        section, ov_key, jp = lk.get("section"), lk.get("override_key"), lk.get("jp_key")
        if section not in ("skills", "heroes"):
            errors.append(f"[link] bad section: {section!r}")
            continue
        if not jp:
            errors.append(f"[link] {section} {ov_key}: empty jp_key")
            continue
        entry = (overrides.get(section) or {}).get(ov_key)
        if entry is None:
            errors.append(f"[link] {section}: override {ov_key!r} not found")
            continue
        # A link onto an `_action: add` override means Phase 3c will reconcile
        # it (re-key + seed canonical/cache) — guard destination + validate the
        # template/structured fields it will seed.
        if isinstance(entry, dict) and entry.get("_action") == "add":
            errors.extend(_check_reconcile_link(
                section, ov_key, jp, entry, overrides,
                added_keys, crawl_base_keys, statuses, scale_names,
                batch_rekey_keys,
            ))
    if errors:
        return {"ok": False, "errors": errors, "applied": {}, "followup": []}

    applied: dict[str, dict] = {}
    retranslate: dict[str, list[str]] = {}

    # =====================================================================
    # PLAN — mutate the in-memory `overrides` dict only. NOTHING is written
    # to disk here, so any (guarded-but-defensive) raise happens before the
    # first file write → genuine all-or-nothing atomicity.
    # =====================================================================

    # Crawl-owned fields the reviewer explicitly chose to keep/custom in the
    # reconcile field-block survive Phase 3c's trim (SPEC: reconcile accepts
    # optional field overrides). adopt_new fields are dropped as usual.
    reconcile_keep_fields: dict[tuple, set[str]] = {}
    for od in override_decisions:
        kept = {f for f, fd in (od.get("fields") or {}).items()
                if fd.get("choice") in ("keep", "custom")}
        if kept:
            reconcile_keep_fields[(od["section"], od["key"])] = kept

    # Override keys a Phase-3c link will reconcile. Their crawl-owned fields may
    # be adopt_new'd in Phase 3, which can empty the entry — but the husk-drop
    # must NOT fire for them, or Phase 3c would find no override to re-key and
    # the curated CHT (name/description) would be lost. Phase 3c trims
    # crawl-owned fields anyway, so pre-deleting them is harmless.
    reconcile_ov_keys = {
        (lk["section"], lk["override_key"])
        for lk in links
        if isinstance((overrides.get(lk["section"]) or {}).get(lk["override_key"]), dict)
        and (overrides[lk["section"]][lk["override_key"]]).get("_action") == "add"
    }

    # ---- Phase 3: override field decisions (in-memory) -------------------
    ov_changed = False
    for od in override_decisions:
        section, key = od["section"], od["key"]
        sec = overrides.setdefault(section, {})
        if od.get("entry_action") == "delete":
            if key in sec:
                del sec[key]
                ov_changed = True
            continue
        entry = sec.get(key)  # guard: a dedup/delete race must not KeyError
        if entry is None:
            continue
        for field, fd in (od.get("fields") or {}).items():
            choice = fd.get("choice")
            if choice == "adopt_new":
                if field in entry:
                    del entry[field]
                    ov_changed = True
            elif choice == "custom":
                entry[field] = fd["_parsed"]
                ov_changed = True
        # adopt_new may have emptied the entry — drop the husk, UNLESS a link
        # will reconcile it in Phase 3c (which needs the entry to survive).
        if (section, key) not in reconcile_ov_keys \
                and not any(not f.startswith("_") for f in entry):
            del sec[key]
            ov_changed = True

    # ---- Phase 3c: reconcile `_action: add` overrides onto their JP key ----
    # Re-key CHT→JP, flip add→modify, trim to translation-owned (+ reviewer-kept)
    # fields. Seeds are RECORDED here and written in the commit stage so the
    # in-memory re-key can't leave a partial disk state.
    reconciled_skill_keys: set[str] = set()
    husk_skill_keys: set[str] = set()  # reconciled-away but nothing seeded
    seed_plan: list[tuple] = []  # (section, jp_key, trimmed)
    n_reconciled = 0
    for lk in links:
        section, ov_key, jp_key = lk["section"], lk["override_key"], lk["jp_key"]
        entry = (overrides.get(section) or {}).get(ov_key)
        if not isinstance(entry, dict) or entry.get("_action") != "add":
            continue
        keep_fields = reconcile_keep_fields.get((section, ov_key), set())
        trimmed = _reconcile_add_override(overrides, section, ov_key, jp_key, keep_fields)
        ov_changed = True  # the pop mutated overrides even on a husk-drop
        if section == "skills" and not trimmed:
            husk_skill_keys.add(jp_key)  # crawl key now has no curated translation
            continue  # husk-drop: nothing to seed/count
        seed_plan.append((section, jp_key, trimmed))
        n_reconciled += 1
        if section == "skills":
            reconciled_skill_keys.add(jp_key)

    # ---- Phase 3b: soft `_name_jp` stamp — only for modify/replace targets ----
    # DEPRECATED (P3): reconcile (Phase 3c) re-keys `_action: add` overrides onto
    # their JP key, so the `_name_jp` join is no longer written for them. It is
    # still stamped for links onto an already-`modify`/`replace` override — the
    # soft pre-reconcile state where the override key is NOT the JP name and
    # re-keying isn't wanted. `_name_jp` is a `_`-meta field (stripped by
    # build_frontend_data, never reaches the frontend `name_jp`). diff_crawl
    # keeps READING it for one release for back-compat; drop the read next release.
    linked = 0
    for lk in links:
        entry = (overrides.get(lk["section"]) or {}).get(lk["override_key"])
        if not isinstance(entry, dict):
            continue  # reconciled above, or override was deleted in this apply
        if entry.get("_action", "modify") == "add":
            continue  # reconcile owns add-overrides now — no soft stamp
        if entry.get("_name_jp") != lk["jp_key"]:
            entry["_name_jp"] = lk["jp_key"]
            ov_changed = True
            linked += 1

    # =====================================================================
    # COMMIT — all disk writes. Plan is validated + fully computed, so no
    # step below raises on logic (only on I/O, which no design can guard).
    # =====================================================================

    # ---- Phase 2: crawled files + canonical raw --------------------------
    staging_heroes = _heroes_by_name(_load_yaml(STAGING_HEROES, []))
    staging_kinds = {
        "heroes": staging_heroes,
        "skills": _load_yaml(STAGING_SKILLS, {}),
        "traits": derive_traits(list(staging_heroes.values())),
        "assembly": _load_yaml(STAGING_ASSEMBLY, {}),
        "bingxue": _load_yaml(STAGING_BINGXUE, {}),
    }

    # Heroes: list file, order-preserving merge
    hero_dec = changes.get("heroes") or {}
    if any(hero_dec.get(t) for t in ("added", "removed", "changed")):
        cur_list = _load_yaml(HEROES_CRAWLED, [])
        removed = set(hero_dec.get("removed", []))
        replace = {
            n: staging_kinds["heroes"][n]
            for n in hero_dec.get("changed", []) if n in staging_kinds["heroes"]
        }
        merged_list = [
            replace.get(h["name"], h) for h in cur_list if h["name"] not in removed
        ]
        for n in hero_dec.get("added", []):
            if n in staging_kinds["heroes"]:
                merged_list.append(staging_kinds["heroes"][n])
        _save_yaml(HEROES_CRAWLED, merged_list)
        applied["heroes"] = {t: len(hero_dec.get(t, [])) for t in ("added", "removed", "changed")}

    # Dict kinds: crawled file + optional canonical raw + llm cache prefix
    kind_files = {
        "skills":   (SKILLS_CRAWLED,   SKILLS_CANONICAL,  "skill"),
        "traits":   (None,             TRAITS_CANONICAL,  "trait"),
        "assembly": (ASSEMBLY_CRAWLED, None,              None),
        "bingxue":  (BINGXUE_CRAWLED,  BINGXUE_CANONICAL, "bingxue"),
    }
    for kind, (crawled_path, canonical_path, cache_prefix) in kind_files.items():
        dec = changes.get(kind) or {}
        if not any(dec.get(t) for t in ("added", "removed", "changed")):
            continue
        touched: list[str]
        if crawled_path is not None:
            current = _load_yaml(crawled_path, {})
            merged, touched = _merge_dict_kind(current, staging_kinds[kind], dec)
            _save_yaml(crawled_path, merged)
        else:
            touched = [
                n for t in ("added", "changed") for n in dec.get(t, [])
                if n in staging_kinds[kind]
            ]
        if canonical_path is not None:
            _sync_canonical_raw(canonical_path, touched, staging_kinds[kind])
        if cache_prefix:
            changed_names = [n for n in dec.get("changed", []) if n in staging_kinds[kind]]
            n_inv = _invalidate_llm_cache(cache_prefix, changed_names)
            if changed_names:
                retranslate[kind] = changed_names
                applied.setdefault(kind, {})["llm_cache_invalidated"] = n_inv
        applied.setdefault(kind, {}).update(
            {t: len(dec.get(t, [])) for t in ("added", "removed", "changed")}
        )

    # Save overrides.yaml FIRST, then the reconcile seeds. The overrides re-key
    # (add→modify) is what removes the duplicate; the seeds only add a curated
    # translation. A crash between them then fails toward a loud "missing
    # translation" (safe, caught by check_coverage) rather than a silent
    # duplicate (re-key lost but seed written).
    if ov_changed:
        _save_yaml(OVERRIDES_YAML, overrides)
        applied["overrides"] = {"decisions": len(override_decisions)}
        if linked:
            applied["overrides"]["links"] = linked
        if n_reconciled:
            applied["overrides"]["reconciled"] = n_reconciled

    # ---- Reconcile seeds (recorded in Phase 3c) --------------------------
    for section, jp_key, trimmed in seed_plan:
        if section == "skills":
            _seed_canonical_skill(jp_key, trimmed)
            _seed_skill_llm_cache(jp_key, trimmed)
        else:
            _seed_hero_translation(jp_key, trimmed.get("name", jp_key))

    # ---- Phase 4: clear staging -------------------------------------------
    if decisions.get("clear_staging", True):
        for p in (STAGING_DIR, STAGING_CACHE_DIR):
            if Path(p).exists():
                shutil.rmtree(p)
        if CRAWL_DIFF_JSON.exists():
            CRAWL_DIFF_JSON.unlink()
        applied["staging_cleared"] = True

    # Reconciled skill keys were seeded with a curated translation + cache hit
    # in Phase 3c — they don't need (and must be excluded from) a retranslate.
    # Husk-dropped keys, by contrast, were reconciled AWAY with nothing seeded,
    # so their crawl entry now needs a fresh translation.
    needs_translate = retranslate or husk_skill_keys or any(
        n for n in (changes.get("skills") or {}).get("added", [])
        if n not in reconciled_skill_keys
    ) or any((changes.get(k) or {}).get("added") for k in ("traits", "bingxue"))

    followup = []
    if needs_translate:
        followup.append("uv run script/llm_translate.py --batch-size 10 --parallel 3")
    followup.append("npm run data")
    if husk_skill_keys:
        applied.setdefault("overrides", {})["husk_dropped"] = sorted(husk_skill_keys)

    return {"ok": True, "errors": [], "applied": applied,
            "retranslate": retranslate, "followup": followup}


# ---------------------------------------------------------------------------
# Backfill: reconcile already-crawled `_action: add` overrides (P3)
# ---------------------------------------------------------------------------

def _backfill_links() -> tuple[list[dict], bool, list[dict]]:
    """Synthesize reconcile links for the `cfg_and_g8` bucket: `_action: add`
    overrides where cfg supplies a JP name (`name_ja`) that is ALREADY in the
    crawled file. Returns (links, crawl_present, dropped) — `dropped` names
    overrides skipped because a sibling already claimed the same resolved jp.

    Reuses build_frontend_data._classify_add_overrides — no new matching logic.
    The links feed the SAME reconcile path as the review UI (apply_decisions).
    """
    from build_frontend_data import _load_cfg_lookups, _classify_add_overrides

    crawl_present = SKILLS_CRAWLED.exists() or HEROES_CRAWLED.exists()
    if not crawl_present:
        return [], False, []

    overrides = _load_yaml(OVERRIDES_YAML, {})
    cfg_skills, cfg_heroes = _load_cfg_lookups()
    g8 = {
        "skills": set(_load_yaml(SKILLS_CRAWLED, {})),
        "heroes": set(_heroes_by_name(_load_yaml(HEROES_CRAWLED, []))),
    }
    cfg = {"skills": cfg_skills, "heroes": cfg_heroes}

    links: list[dict] = []
    dropped: list[dict] = []
    seen: dict[tuple, str] = {}  # (section, jp) → kept override_key
    for section in ("skills", "heroes"):
        cls = _classify_add_overrides(overrides.get(section, {}), cfg[section], g8[section])
        for ov_key in cls["cfg_and_g8"]:
            jp = (cfg[section].get(ov_key) or {}).get("name_ja")
            # Guard: never fabricate a link whose jp_key isn't in the crawl base
            # (cfg_and_g8 already implies this, but stay defensive).
            if not (jp and jp in g8[section]):
                continue
            # Dedup on the RESOLVED jp: two CHT overrides mapping to the same JP
            # would collide on re-key (apply's Phase-1 guard would reject the
            # whole batch), so keep the first and report the rest.
            if (section, jp) in seen:
                dropped.append({"section": section, "jp_key": jp,
                                "kept": seen[(section, jp)], "dropped": ov_key})
                continue
            seen[(section, jp)] = ov_key
            links.append({"section": section, "override_key": ov_key, "jp_key": jp})
    return links, True, dropped


def run_backfill(dry_run: bool) -> int:
    links, crawl_present, dropped = _backfill_links()
    if not crawl_present:
        print("[backfill] crawl base not found — run the crawler first "
              "(need data/skills_crawled.yaml / data/heroes_crawled.yaml).")
        return 2
    for d in dropped:
        print(f"[backfill] WARN [{d['section']}] {d['dropped']!r} dropped — "
              f"same JP {d['jp_key']!r} already claimed by {d['kept']!r}")
    if not links:
        print("[backfill] no cfg_and_g8 candidates — every `_action: add` "
              "override is pre-launch / cfg-only (not yet crawled), already "
              "reconciled, or cfg.json is absent.")
        return 0

    print(f"[backfill] {len(links)} reconcile candidate(s):")
    for lk in links:
        print(f"  [{lk['section']}] {lk['override_key']} → {lk['jp_key']}")
    if dry_run:
        print("[backfill] --dry-run: nothing written.")
        return 0

    result = apply_decisions({"changes": {}, "overrides": [], "links": links,
                              "clear_staging": False})
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] == "backfill":
        return run_backfill(dry_run="--dry-run" in args[1:])
    if len(args) != 1:
        print(__doc__)
        return 2
    decisions = json.loads(Path(args[0]).read_text("utf-8"))
    result = apply_decisions(decisions)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
