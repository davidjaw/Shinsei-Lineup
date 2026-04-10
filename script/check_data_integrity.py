"""
Post-build data integrity check.

Verifies that the frontend JSON files are consistent:
- All hero skill references resolve to a skill in skills.json
- All skills/heroes have required fields
- No user-visible field still contains untranslated Japanese (kana)
- Every crawled skill/hero/trait has a translated counterpart

Exits non-zero on any failure so `npm run data` aborts loudly.

Usage:
    python script/check_data_integrity.py
"""

import json
import re
import sys

import yaml

from llm_core import has_kana as _has_kana
from paths import (
    HEROES_JSON, SKILLS_JSON,
    HEROES_CRAWLED, HEROES_TRANSLATED,
    SKILLS_CRAWLED, TRAITS_CRAWLED,
    SKILLS_CANONICAL, TRAITS_CANONICAL,
)


def _load_yaml(path):
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text("utf-8"))
    return data if data else {}


def check():
    heroes = json.loads(HEROES_JSON.read_text("utf-8"))
    skills = json.loads(SKILLS_JSON.read_text("utf-8"))

    errors = []

    # ---- Reference / required-field checks ---------------------------------
    skill_by_name = {}
    skill_by_jp = {}
    for s in skills:
        skill_by_name[s["name"]] = s
        if s.get("name_jp"):
            skill_by_jp[s["name_jp"]] = s

    def find_skill(name):
        return skill_by_name.get(name) or skill_by_jp.get(name)

    for h in heroes:
        if not h.get("name"):
            errors.append(f"Hero missing name: {h}")
        if not h.get("stats"):
            errors.append(f"Hero '{h['name']}' missing stats")
        if not h.get("portrait"):
            errors.append(f"Hero '{h['name']}' missing portrait")
        if not h.get("faction"):
            errors.append(f"Hero '{h['name']}' missing faction")

        for ref_field in ["unique_skill", "teachable_skill"]:
            ref = h.get(ref_field)
            if ref and not find_skill(ref):
                errors.append(f"Hero '{h['name']}' {ref_field}='{ref}' not found in skills.json")

    for s in skills:
        if not s.get("name"):
            errors.append(f"Skill missing name: {s}")
        if not s.get("type"):
            errors.append(f"Skill '{s.get('name','')}' missing type")
        if not s.get("description"):
            errors.append(f"Skill '{s.get('name','')}' missing description")

    seen_names = {}
    for s in skills:
        n = s["name"]
        if n in seen_names:
            errors.append(f"Duplicate skill name: '{n}'")
        seen_names[n] = True

    # ---- Untranslated-text detection (kana scan) ---------------------------
    untranslated_skills = []
    for s in skills:
        for field in ("name", "description", "commander_description", "brief_description", "target"):
            v = s.get(field)
            if _has_kana(v):
                untranslated_skills.append((s.get("name", "?"), field, v[:60]))
                break

    untranslated_heroes = []
    for h in heroes:
        if _has_kana(h.get("name")):
            untranslated_heroes.append((h.get("name_jp", "?"), "name", h.get("name", "")[:60]))
        for t in h.get("traits", []) or []:
            for field in ("name", "description"):
                if _has_kana(t.get(field)):
                    untranslated_heroes.append((h.get("name", "?"), f"trait.{field}", (t.get(field) or "")[:60]))
                    break

    for name, field, sample in untranslated_skills:
        errors.append(f"Skill '{name}' {field} contains JP kana: {sample}")
    for name, field, sample in untranslated_heroes:
        errors.append(f"Hero '{name}' {field} contains JP kana: {sample}")

    # ---- Crawled vs canonical key cross-check --------------------------------
    crawled_skills = _load_yaml(SKILLS_CRAWLED)
    canonical_skills = _load_yaml(SKILLS_CANONICAL)
    missing_skills = sorted(set(crawled_skills) - set(canonical_skills))

    crawled_traits = _load_yaml(TRAITS_CRAWLED)
    canonical_traits = _load_yaml(TRAITS_CANONICAL)
    missing_traits = sorted(set(crawled_traits) - set(canonical_traits))

    crawled_heroes_raw = yaml.safe_load(HEROES_CRAWLED.read_text("utf-8")) or []
    translated_heroes = _load_yaml(HEROES_TRANSLATED)
    crawled_hero_names = {h.get("name") for h in crawled_heroes_raw if h.get("name")}
    missing_heroes = sorted(crawled_hero_names - set(translated_heroes))

    for k in missing_skills:
        errors.append(f"Skill '{k}' is in skills_crawled.yaml but missing from skills.yaml")
    for k in missing_traits:
        errors.append(f"Trait '{k}' is in traits_crawled.yaml but missing from traits.yaml")
    for k in missing_heroes:
        errors.append(f"Hero '{k}' is in heroes_crawled.yaml but missing from heroes_translated.yaml")

    # ---- Summary -----------------------------------------------------------
    print(f"Heroes: {len(heroes)}")
    print(f"Skills: {len(skills)}")
    print(f"Skill lookup entries: {len(skill_by_name)} by name, {len(skill_by_jp)} by name_jp")

    if errors:
        print(f"\n{len(errors)} ERROR(S):")
        for e in errors:
            print(f"  {e}")

        # Build a copy-pasteable suggested-action block. We try to bucket the
        # errors by type so the admin can fix the smallest possible scope.
        suggestions = []
        # Don't suggest --force unless we know the cache is poisoned. A plain
        # run will already call the LLM for any item that's missing from the
        # output YAML, and --force on a filtered run is dangerous (see the
        # full-run guard in llm_translate.process_*).
        if missing_skills or untranslated_skills:
            names = sorted({n for n, *_ in untranslated_skills} | set(missing_skills))
            if len(names) == 1:
                suggestions.append(f'uv run script/llm_translate.py --skills --name "{names[0]}"')
            elif names:
                suggestions.append("uv run script/llm_translate.py --skills    # then re-check")
        if missing_traits or any("trait" in field for _, field, _ in untranslated_heroes):
            suggestions.append("uv run script/llm_translate.py --traits")
        if missing_heroes or any(field == "name" for _, field, _ in untranslated_heroes):
            suggestions.append("uv run script/llm_translate.py --heroes")
        if suggestions:
            print("\n[suggested actions — copy/paste to fix]")
            for s in suggestions:
                print(f"  {s}")
            print("  uv run script/build_frontend_data.py && uv run script/check_data_integrity.py")

        sys.exit(1)
    else:
        print("\nAll checks passed.")


if __name__ == "__main__":
    check()
