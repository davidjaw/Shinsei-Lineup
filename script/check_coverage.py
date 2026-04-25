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

    # ---- Sanity: override `_replaces` / replace-key points at something real --
    # Flags typos in overrides so users notice when a JP name doesn't match any crawled key.
    for name, expected_set, scope in (
        ("skill", crawled_skills, "skills"),
        ("hero", crawled_hero_names, "heroes"),
    ):
        for jp_key in _override_handled_keys(overrides.get(scope, {})):
            if jp_key not in expected_set:
                errors.append(
                    f"Override on {name} '{jp_key}' references a JP name not present in {scope}_crawled.yaml "
                    f"(typo? or crawl hasn't picked up this entry yet)"
                )

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
