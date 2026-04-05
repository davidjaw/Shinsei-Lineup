"""
Post-build data integrity check.

Verifies that the frontend JSON files are consistent:
- All hero skill references resolve to a skill in skills.json
- All skills have required fields
- All heroes have required fields
- No orphaned data

Usage:
    python script/check_data_integrity.py
"""

import json
import sys

from paths import HEROES_JSON, SKILLS_JSON


def check():
    heroes = json.loads(HEROES_JSON.read_text("utf-8"))
    skills = json.loads(SKILLS_JSON.read_text("utf-8"))

    errors = []

    # Build skill lookup (by name AND name_jp)
    skill_by_name = {}
    skill_by_jp = {}
    for s in skills:
        skill_by_name[s["name"]] = s
        if s.get("name_jp"):
            skill_by_jp[s["name_jp"]] = s

    def find_skill(name):
        return skill_by_name.get(name) or skill_by_jp.get(name)

    # Check heroes
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
                errors.append(f"Hero '{h['name']}' {ref_field}='{ref}' not found in skills.json (checked name + name_jp)")

    # Check skills
    for s in skills:
        if not s.get("name"):
            errors.append(f"Skill missing name: {s}")
        if not s.get("type"):
            errors.append(f"Skill '{s.get('name','')}' missing type")
        if not s.get("description"):
            errors.append(f"Skill '{s.get('name','')}' missing description")

    # Check for duplicate skill names
    seen_names = {}
    for s in skills:
        n = s["name"]
        if n in seen_names:
            errors.append(f"Duplicate skill name: '{n}'")
        seen_names[n] = True

    # Summary
    print(f"Heroes: {len(heroes)}")
    print(f"Skills: {len(skills)}")
    print(f"Skill lookup entries: {len(skill_by_name)} by name, {len(skill_by_jp)} by name_jp")

    if errors:
        print(f"\n{len(errors)} ERROR(S):")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)
    else:
        print("\nAll checks passed.")


if __name__ == "__main__":
    check()
