"""
Override-aware translation-coverage check.

Cross-references crawled-vs-translated keys per kind (skills, traits, heroes),
subtracting anything that `overrides.yaml` deliberately replaces or deletes.
Fails when a genuinely missing translation is detected — not when an entry
has been intentionally superseded by an override.

Coverage semantics:
  missing = crawled_keys - translated_keys - override_handled_keys

where override_handled_keys covers all three replacement patterns:
  - `_action: delete` — crawled entry removed from build
  - `_action: replace` — crawled entry replaced wholesale (NEW format, JP-keyed)
  - `_action: add` + `_replaces: <jp_name>` — LEGACY format (CHT-keyed)

Usage:
    python script/check_coverage.py
"""

import sys

import yaml

from paths import (
    HEROES_CRAWLED, HEROES_TRANSLATED,
    SKILLS_CRAWLED, SKILLS_CANONICAL,
    TRAITS_CRAWLED, TRAITS_CANONICAL,
    OVERRIDES_YAML,
)


def _load_yaml(path) -> dict:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text("utf-8"))
    return data or {}


def _override_handled_keys(section: dict) -> set[str]:
    """JP keys handled by overrides in this section (skills or heroes).

    Covers both formats:
      NEW: `{jp_key: {_action: replace, ...}}` — the dict key IS the JP name.
      LEGACY: `{cht_key: {_action: add, _replaces: <jp_name>, ...}}`
              — the `_replaces` field names the JP original.
      Also: `{jp_key: {_action: delete}}` — crawled entry explicitly dropped.
    """
    handled: set[str] = set()
    if not isinstance(section, dict):
        return handled
    for key, entry in section.items():
        if not isinstance(entry, dict):
            continue
        action = entry.get("_action", "modify")
        if action == "delete":
            handled.add(key)
        elif action == "replace":
            handled.add(key)
        elif action == "add":
            replaces = entry.get("_replaces")
            if replaces:
                handled.add(replaces)
        # `modify` doesn't handle coverage — the crawled entry still needs translation.
    return handled


def check() -> list[str]:
    errors: list[str] = []
    overrides = _load_yaml(OVERRIDES_YAML)

    skill_handled = _override_handled_keys(overrides.get("skills", {}))
    hero_handled = _override_handled_keys(overrides.get("heroes", {}))

    # ---- Skills: crawled vs canonical -------------------------------------
    crawled_skills = set(_load_yaml(SKILLS_CRAWLED))
    canonical_skills = set(_load_yaml(SKILLS_CANONICAL))
    missing_skills = sorted(crawled_skills - canonical_skills - skill_handled)
    for k in missing_skills:
        errors.append(f"Skill '{k}' is in skills_crawled.yaml but missing from skills.yaml")

    # ---- Traits: crawled vs canonical -------------------------------------
    crawled_traits = set(_load_yaml(TRAITS_CRAWLED))
    canonical_traits = set(_load_yaml(TRAITS_CANONICAL))
    missing_traits = sorted(crawled_traits - canonical_traits)
    for k in missing_traits:
        errors.append(f"Trait '{k}' is in traits_crawled.yaml but missing from traits.yaml")

    # ---- Heroes: crawled vs translated ------------------------------------
    crawled_heroes_raw = yaml.safe_load(HEROES_CRAWLED.read_text("utf-8")) or []
    crawled_hero_names = {h.get("name") for h in crawled_heroes_raw if h.get("name")}
    translated_hero_names = set(_load_yaml(HEROES_TRANSLATED))
    missing_heroes = sorted(crawled_hero_names - translated_hero_names - hero_handled)
    for k in missing_heroes:
        errors.append(f"Hero '{k}' is in heroes_crawled.yaml but missing from heroes_translated.yaml")

    # ---- Sanity: replace/delete keys must point at something real -----------
    # Flags typos so users notice when a JP key doesn't match any crawled entry.
    # `_replaces` on `_action: add` is intentionally NOT checked: it now
    # doubles as a runtime alias (e.g. typo migrations like 立花闇千代→立花誾千代),
    # and the historical name need not exist in any upstream YAML.
    for name, expected_set, scope in (
        ("skill", crawled_skills, "skills"),
        ("hero", crawled_hero_names, "heroes"),
    ):
        section = overrides.get(scope, {}) or {}
        if not isinstance(section, dict):
            continue
        for key, entry in section.items():
            if not isinstance(entry, dict):
                continue
            action = entry.get("_action", "modify")
            if action in ("delete", "replace") and key not in expected_set:
                errors.append(
                    f"Override on {name} '{key}' (_action={action}) references a JP name not present "
                    f"in {scope}_crawled.yaml (typo? or crawl hasn't picked up this entry yet)"
                )

    # ---- Reconcile guards (P3) --------------------------------------------
    errors.extend(_check_reconcile_guards(overrides, crawled_skills, crawled_hero_names))
    return errors


def _check_reconcile_guards(
    overrides: dict, crawled_skills: set, crawled_hero_names: set,
    cfg_lookups: tuple | None = None,
) -> list[str]:
    """Two invariants that keep the override↔crawl reconcile honest.

    (a) No `_action: add` override may resolve to a JP name already in the
        crawled file — an UN-reconciled duplicate that would ship a second
        entry (caught here before the build's duplicate-name check). JP is
        resolved three ways: identical key, `_name_jp`, and — for the
        divergent-name case (CHT≠JP, the raison d'être of this subsystem) —
        cfg's `name_ja`. Such an override should be re-keyed to `modify` (run
        `merge_crawl.py backfill`).
        KNOWN LIMIT: a pure-OCR-typo add whose name is neither identical to the
        crawled JP nor present in cfg stays uncatchable here — nothing links it
        to its crawled twin until a reviewer confirms the link in the UI.
    (b) A `modify` override carrying `aliases` (lineup-key stability: old CHT
        names preserved so existing lineups still resolve) must be internally
        consistent — no alias may equal the entry's own `name` or its key, and
        aliases must be distinct non-empty strings.
    """
    if cfg_lookups is None:
        try:
            from build_frontend_data import _load_cfg_lookups
            cfg_lookups = _load_cfg_lookups()
        except Exception:
            cfg_lookups = ({}, {})
    cfg = {"skills": cfg_lookups[0], "heroes": cfg_lookups[1]}

    errors: list[str] = []
    crawled = {"skills": crawled_skills, "heroes": crawled_hero_names}
    for scope in ("skills", "heroes"):
        section = overrides.get(scope, {}) or {}
        if not isinstance(section, dict):
            continue
        base = crawled[scope]
        for key, entry in section.items():
            if not isinstance(entry, dict):
                continue
            # (a) un-reconciled duplicate
            if entry.get("_action", "modify") == "add":
                jp = entry.get("_name_jp") or key
                cfg_ja = (cfg[scope].get(key) or {}).get("name_ja")
                if jp in base:
                    errors.append(
                        f"Override [{scope}] '{key}' is _action:add but its JP name "
                        f"'{jp}' is already in {scope}_crawled.yaml — un-reconciled "
                        f"duplicate (re-key to modify, e.g. `merge_crawl.py backfill`)."
                    )
                elif cfg_ja and cfg_ja in base:
                    errors.append(
                        f"Override [{scope}] '{key}' is _action:add but cfg maps it to "
                        f"JP '{cfg_ja}' which is already in {scope}_crawled.yaml — "
                        f"un-reconciled duplicate (run `merge_crawl.py backfill`)."
                    )
            # (b) alias internal consistency
            errors.extend(_check_alias_consistency(scope, key, entry))
    return errors


def _check_alias_consistency(scope: str, key: str, entry: dict) -> list[str]:
    aliases = entry.get("aliases")
    if not aliases:
        return []
    if isinstance(aliases, str):
        aliases = [aliases]
    errors: list[str] = []
    name = entry.get("name")
    seen: set[str] = set()
    for a in aliases:
        if not isinstance(a, str) or not a.strip():
            errors.append(f"Override [{scope}] '{key}' has an empty/non-string alias")
        elif a == name or a == key:
            errors.append(
                f"Override [{scope}] '{key}' aliases its own "
                f"{'name' if a == name else 'key'} '{a}' (redundant/inconsistent)"
            )
        elif a in seen:
            errors.append(f"Override [{scope}] '{key}' has duplicate alias '{a}'")
        seen.add(a)
    return errors


def main():
    errors = check()

    if errors:
        print(f"\n{len(errors)} COVERAGE ERROR(S):")
        for e in errors:
            print(f"  {e}")
        print("\n[suggested actions]")
        print("  uv run script/llm_translate.py    # translate missing entries")
        print("  — or add an override with _action: replace / delete for entries intentionally bypassing translation")
        sys.exit(1)
    print("[check-coverage] All translation coverage checks passed.")


if __name__ == "__main__":
    main()
