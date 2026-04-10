"""
Interactive CLI for managing data overrides.

Supports:
  - Modify existing skills via natural language instructions
  - Add new skills (regular or event skills)
  - Add new heroes

Uses OpenRouter LLM to validate modifications and format new entries.

Usage:
    python script/override.py --modify-skill
    python script/override.py --add-skill
    python script/override.py --add-hero
"""

import argparse
import json
import sys
import yaml
from pathlib import Path

from llm_core import (
    CANONICAL_STATUSES, COMMON_RULES, SKILL_TAGS, SKILL_OUTPUT_FORMAT,
    DEFAULT_MODEL,
    call_llm, parse_llm_output, autofix_frontend, has_kana, load_overrides,
    validate_skill_entry, validate_entry_quality,
)
from llm_translate import (
    build_batch_prompt as build_skill_batch_prompt,
    build_single_prompt as build_skill_single_prompt,
)
from paths import (
    OVERRIDES_YAML, SKILLS_CRAWLED,
    SKILLS_CANONICAL, TRAITS_CANONICAL,
    HEROES_JSON, SKILLS_JSON,
)

BACK_CMD = "<"


def save_overrides(data: dict):
    OVERRIDES_YAML.parent.mkdir(parents=True, exist_ok=True)
    with open(OVERRIDES_YAML, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


class GoBack(Exception):
    """Raised when user types '<' to go back to previous step."""


def load_existing_skills() -> dict:
    """Load canonical skills for reference during modifications."""
    if SKILLS_CANONICAL.exists():
        data = yaml.safe_load(SKILLS_CANONICAL.read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    return {}


def load_existing_traits() -> dict:
    """Load canonical traits for lookup during hero creation."""
    if TRAITS_CANONICAL.exists():
        data = yaml.safe_load(TRAITS_CANONICAL.read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    return {}


def _check_back(val: str):
    if val == BACK_CMD:
        raise GoBack()


def _confirm_overwrite(name: str, overrides: dict) -> bool:
    """If skill already exists in overrides, ask user whether to overwrite. Returns True to proceed."""
    existing = overrides.get("skills", {}).get(name)
    if not existing:
        return True
    print(f"\n  [warn] '{name}' already exists in overrides:")
    print(f"    type: {existing.get('type', '?')}  rarity: {existing.get('rarity', '?')}")
    desc = existing.get("description", "")
    if desc:
        print(f"    description: {desc[:80]}{'...' if len(desc) > 80 else ''}")
    return prompt_confirm(f"  Overwrite '{name}'?", default=False)


def prompt_input(label: str, required: bool = True, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        val = input(f"  {label}{suffix}: ").strip()
        _check_back(val)
        if not val and default:
            return default
        if val or not required:
            return val
        print(f"  (required, type '<' to go back)")


def prompt_choice(label: str, choices: list[str], default: str = "") -> str:
    choices_str = "/".join(choices)
    suffix = f" [{default}]" if default else ""
    while True:
        val = input(f"  {label} ({choices_str}){suffix}: ").strip()
        _check_back(val)
        if not val and default:
            return default
        if val in choices:
            return val
        print(f"  please choose: {choices_str} (type '<' to go back)")


def prompt_confirm(label: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    val = input(f"  {label} {suffix}: ").strip().lower()
    if val == BACK_CMD:
        raise GoBack()
    if not val:
        return default
    return val in ("y", "yes")


def find_skill(name: str) -> dict | None:
    """Check if a skill exists in translated data or overrides."""
    skills = load_existing_skills()
    for key, data in skills.items():
        if key == name or data.get("name") == name:
            return data
    overrides = load_overrides()
    for key, data in overrides.get("skills", {}).items():
        if key == name or data.get("name") == name:
            return data
    return None


def find_trait(name: str) -> dict | None:
    """Check if a trait exists in translated data. Try both CHT name and JP key."""
    traits = load_existing_traits()
    # Try as JP key
    if name in traits:
        return traits[name]
    # Try as CHT name
    for key, data in traits.items():
        if data.get("name") == name:
            return data
    return None


# ---------------------------------------------------------------------------
# Modify Skill
# ---------------------------------------------------------------------------

MODIFY_TASK_RULES = """\
Rules:
1. If the instruction is ambiguous or unclear (e.g., which field to change, base or max, etc.), output ONLY:
   ```yaml
   _rejected: true
   reason: "<explanation of what's unclear, in Traditional Chinese>"
   ```
2. If the instruction is clear, output ONLY the fields that need to change as a YAML dict.
   - Use the same field names and structure as the original skill.
   - For nested fields like vars, only include the changed sub-fields.
   - All text must be in Traditional Chinese."""


def _build_modify_prompt(skill_yaml: str, instruction: str) -> str:
    return f"""\
You are a game data editor for 信長之野望：真戰 (Nobunaga's Ambition: Shinsei).

{COMMON_RULES}

Below is the current skill data in YAML format:

```yaml
{skill_yaml}
```

The user wants to modify this skill with the following instruction:
"{instruction}"

{MODIFY_TASK_RULES}"""


def do_modify_skill(model: str):
    skills = load_existing_skills()
    if not skills:
        print("[error] No translated skills found. Run llm_translate.py first.")
        return

    print("\n=== Modify Existing Skill ===")
    skill_name = prompt_input("Skill name (CHT or JP)")

    # Find the skill
    target_key = None
    target_data = None
    for key, data in skills.items():
        if key == skill_name or data.get("name") == skill_name:
            target_key = key
            target_data = data
            break

    # Also check overrides
    overrides = load_overrides()
    if target_key is None:
        for key, data in overrides.get("skills", {}).items():
            if key == skill_name or data.get("name") == skill_name:
                target_key = key
                target_data = data
                break

    if target_key is None:
        print(f"[error] Skill '{skill_name}' not found.")
        return

    print(f"\n  Found: {target_key}")
    print(f"  Name: {target_data.get('name', target_key)}")
    print(f"  Type: {target_data.get('type', '?')}")
    desc = target_data.get('description', '')
    print(f"  Description: {desc[:80]}{'...' if len(desc) > 80 else ''}")

    instruction = prompt_input("\nModification instruction (natural language)")

    skill_yaml = yaml.dump(
        {target_key: target_data},
        allow_unicode=True, default_flow_style=False, sort_keys=False,
    )
    prompt = _build_modify_prompt(skill_yaml, instruction)

    print("\n[llm] Processing modification...")
    try:
        raw = call_llm(prompt, model=model)
        result = parse_llm_output(raw)
    except Exception as e:
        print(f"[error] LLM call failed: {e}")
        return

    if result is None:
        print("[error] Failed to parse LLM response.")
        print(f"  Raw output:\n{raw[:500]}")
        return

    if result.get("_rejected"):
        print(f"\n[rejected] {result.get('reason', 'unknown reason')}")
        return

    print("\n[preview] Changes to apply:")
    print(yaml.dump(result, allow_unicode=True, default_flow_style=False, sort_keys=False))

    if not prompt_confirm("Apply these changes?"):
        print("[cancelled]")
        return

    overrides = load_overrides()
    overrides.setdefault("skills", {})
    existing = overrides["skills"].get(target_key, {})
    # Deep merge new changes into existing overrides for this skill
    for k, v in result.items():
        if isinstance(v, dict) and isinstance(existing.get(k), dict):
            existing[k].update(v)
        else:
            existing[k] = v
    overrides["skills"][target_key] = existing
    save_overrides(overrides)
    print(f"[done] Override saved for '{target_key}' in {OVERRIDES_YAML}")


# ---------------------------------------------------------------------------
# Add Skill
# ---------------------------------------------------------------------------

def _build_add_skill_prompt(info: dict) -> str:
    """Build prompt for guided add-skill. Uses OVERRIDE_SYSTEM_PROMPT as system."""
    skill_dict = {
        "raw": {
            "name": info["name"],
            "type": info["type"],
            "rarity": info["rarity"],
            "target": info["target"],
            "activation_rate": "",
            "source_hero": info.get("source_hero", ""),
            "description": info["description"],
            "commander_bonus": "",
        }
    }
    _, user = build_skill_single_prompt(skill_dict)
    return user


def _collect_one_skill() -> dict | None:
    """Collect one skill's raw info from user. Returns dict or None if cancelled."""
    try:
        is_event = prompt_confirm("Is this an event skill (事件戰法)?", default=False)
        name = prompt_input("Skill name (CHT)")
        skill_type = prompt_choice("Type", ["被動", "主動", "指揮", "突擊", "兵種"])
        rarity = prompt_choice("Rarity", ["S", "A", "B"])
        target = prompt_input("Target (e.g., 敵軍單體, 自身, 我方全體)")
        description = prompt_input("Skill description (natural language, can include numbers)")

        source_hero = ""
        unique_hero = ""
        if not is_event:
            unique_hero = prompt_input("Unique hero (固有武將, leave empty if teachable)", required=False)
            if not unique_hero:
                source_hero = prompt_input("Source hero (傳承者)", required=False)

        return {
            "name": name, "type": skill_type, "rarity": rarity,
            "target": target, "description": description,
            "is_event": is_event, "source_hero": source_hero, "unique_hero": unique_hero,
        }
    except GoBack:
        return None


def _process_skill_with_llm(info: dict, model: str) -> tuple[str, dict] | None:
    """Send one skill to LLM, return (name, result) or None on failure."""
    name = info["name"]
    prompt = _build_add_skill_prompt(info)

    try:
        raw = call_llm(prompt, system_prompt=OVERRIDE_SYSTEM_PROMPT, model=model)
        result = parse_llm_output(raw)
    except Exception as e:
        print(f"  [error] LLM failed for '{name}': {e}")
        return None

    if result is None:
        print(f"  [error] Failed to parse LLM response for '{name}'")
        return None

    # Auto-fix known LLM issues (override results are flat, not nested under frontend)
    fixes = autofix_frontend(result)
    if fixes:
        print(f"    [autofix] {'; '.join(fixes)}")

    result["_action"] = "add"
    result["raw_text"] = info["description"]
    result["name"] = name
    if info["is_event"]:
        result["is_event_skill"] = True
    if info["source_hero"]:
        result["source_hero"] = info["source_hero"]
    if info["unique_hero"]:
        result["unique_hero"] = info["unique_hero"]
        result["is_unique"] = True

    return name, result


def do_add_skill(model: str):
    print("\n=== Add New Skill (batch mode) ===")
    print("  Collect skills first, then run LLM for all at once.")
    print("  Type '<' to go back.\n")

    queue = []
    while True:
        print(f"\n--- Skill #{len(queue) + 1} ---")
        info = _collect_one_skill()
        if info is None:
            if not queue:
                print("[cancelled]")
                return
            print("  (skipped)")
        else:
            queue.append(info)
            print(f"  [queued] {info['name']} ({info['type']}, {info['rarity']})")

        if queue:
            print(f"\n  Queue: {len(queue)} skill(s) — {', '.join(s['name'] for s in queue)}")
            choice = prompt_choice("Action", ["add", "run"], default="add")
            if choice == "run":
                break

    print(f"\n[llm] Processing {len(queue)} skill(s)...")
    results = []
    for i, info in enumerate(queue, 1):
        print(f"  [{i}/{len(queue)}] {info['name']}...")
        out = _process_skill_with_llm(info, model)
        if out:
            results.append(out)

    if not results:
        print("[error] All skills failed LLM processing.")
        return

    # Preview all
    print(f"\n[preview] {len(results)} skill(s) to add:")
    for name, result in results:
        print(yaml.dump({name: result}, allow_unicode=True, default_flow_style=False, sort_keys=False))

    if not prompt_confirm(f"Add all {len(results)} skill(s)?"):
        print("[cancelled]")
        return

    overrides = load_overrides()
    overrides.setdefault("skills", {})
    added = 0
    for name, result in results:
        if not _confirm_overwrite(name, overrides):
            print(f"  [skipped] {name}")
            continue
        overrides["skills"][name] = result
        added += 1
    if added:
        save_overrides(overrides)
    print(f"[done] {added}/{len(results)} skill(s) added to {OVERRIDES_YAML}")


# ---------------------------------------------------------------------------
# Add Hero
# ---------------------------------------------------------------------------

HERO_STEPS = [
    "name", "rarity", "cost", "faction", "clan", "gender",
    "stats", "unique_skill", "teachable_skill", "assembly_skill",
    "portrait", "traits",
]

STAT_FIELDS = [("lea", "統率"), ("val", "武勇"), ("int", "智略"), ("pol", "政治"), ("cha", "魅力"), ("spd", "速度")]


def _collect_hero_field(step: str, collected: dict):
    """Collect one hero field. Raises GoBack to go back."""
    if step == "name":
        collected["name"] = prompt_input("Hero name (CHT)")
    elif step == "rarity":
        collected["rarity"] = int(prompt_input("Rarity", default="5"))
    elif step == "cost":
        collected["cost"] = int(prompt_input("Cost", default="7"))
    elif step == "faction":
        collected["faction"] = prompt_input("Faction (勢力)")
    elif step == "clan":
        collected["clan"] = prompt_input("Clan (氏族)", default=collected.get("faction", ""))
    elif step == "gender":
        collected["gender"] = prompt_choice("Gender", ["男", "女"])
    elif step == "stats":
        print("\n  Stats (六維):")
        stats = {}
        stat_idx = 0
        while stat_idx < len(STAT_FIELDS):
            key, label = STAT_FIELDS[stat_idx]
            try:
                stats[key] = int(prompt_input(f"  {label} ({key})"))
                stat_idx += 1
            except GoBack:
                if stat_idx > 0:
                    stat_idx -= 1
                else:
                    raise
        collected["stats"] = stats
    elif step == "unique_skill":
        collected["unique_skill"] = prompt_input("Unique skill name (固有技能, CHT)")
    elif step == "teachable_skill":
        collected["teachable_skill"] = prompt_input("Teachable skill name (傳承技能, CHT)", required=False)
    elif step == "assembly_skill":
        collected["assembly_skill"] = prompt_input("Assembly skill name (評定衆技能)", required=False)
    elif step == "portrait":
        collected["portrait"] = prompt_input("Portrait URL", required=False)
    elif step == "traits":
        _collect_traits(collected)


def _collect_traits(collected: dict):
    """Collect traits with auto-lookup from existing translated data."""
    print("\n  Traits (特性, enter empty name to finish, '<' to go back):")
    print("  (rank is auto-derived from name suffix: III→A, II→B, I→C, else S)")
    traits = []
    trait_idx = 0
    while trait_idx < 4:
        try:
            trait_name = prompt_input(f"  Trait {trait_idx+1} name", required=False)
        except GoBack:
            if trait_idx > 0:
                traits.pop()
                trait_idx -= 1
                print(f"  (back to trait {trait_idx+1})")
                continue
            else:
                raise
        if not trait_name:
            break

        existing = find_trait(trait_name)
        if existing:
            desc = existing.get("description", "")
            print(f"    [found] {existing.get('name', trait_name)}: {desc[:60]}{'...' if len(desc) > 60 else ''}")
            traits.append({
                "name": existing.get("name", trait_name),
                "description": desc,
                "vars": existing.get("vars", {}),
                "active": True,
            })
        else:
            print(f"    [new] Trait not found in existing data, enter description:")
            try:
                trait_desc = prompt_input(f"  Trait {trait_idx+1} description")
            except GoBack:
                continue  # re-ask trait name
            traits.append({
                "name": trait_name,
                "description": trait_desc,
                "active": True,
            })
        trait_idx += 1
    collected["traits"] = traits


def do_add_hero(model: str):
    print("\n=== Add New Hero === (type '<' at any step to go back)")

    collected = {}
    step_idx = 0
    while step_idx < len(HERO_STEPS):
        step = HERO_STEPS[step_idx]
        try:
            _collect_hero_field(step, collected)
            step_idx += 1
        except GoBack:
            if step_idx > 0:
                step_idx -= 1
                print(f"  (back to: {HERO_STEPS[step_idx]})")
            else:
                print("[cancelled]")
                return

    hero = {
        "_action": "add",
        "name": collected["name"],
        "rarity": collected["rarity"],
        "cost": collected["cost"],
        "faction": collected["faction"],
        "clan": collected["clan"],
        "gender": collected["gender"],
        "portrait": collected.get("portrait", ""),
        "detail_url": "",
        "unique_skill": collected["unique_skill"],
        "teachable_skill": collected.get("teachable_skill", ""),
        "assembly_skill": collected.get("assembly_skill", ""),
        "stats": collected["stats"],
        "traits": collected.get("traits", []),
    }

    print("\n[preview] Hero to add:")
    print(yaml.dump({collected["name"]: hero}, allow_unicode=True, default_flow_style=False, sort_keys=False))

    if not prompt_confirm("Add this hero?"):
        print("[cancelled]")
        return

    overrides = load_overrides()
    overrides.setdefault("heroes", {})
    overrides["heroes"][collected["name"]] = hero
    save_overrides(overrides)
    print(f"[done] Hero '{collected['name']}' added to {OVERRIDES_YAML}")

    # Check if referenced skills exist, offer to add them
    missing_skills = []
    for skill_field, label in [("unique_skill", "固有技能"), ("teachable_skill", "傳承技能")]:
        skill_name = collected.get(skill_field, "")
        if skill_name and not find_skill(skill_name):
            missing_skills.append((skill_name, label))

    if missing_skills:
        print(f"\n[info] The following skills were not found:")
        for name, label in missing_skills:
            print(f"  - {name} ({label})")
        if prompt_confirm("Add these skills now?"):
            for name, label in missing_skills:
                print(f"\n--- Adding skill: {name} ({label}) ---")
                _add_skill_for_hero(name, label, collected["name"], model)


# ---------------------------------------------------------------------------
# Quick Add (unified: skills, heroes, or mixed)
# ---------------------------------------------------------------------------


def _collect_raw_input() -> str:
    """Collect raw text from user as a single block.
    Returns the full pasted text. LLM handles splitting into individual items."""
    print("  Paste all items (two blank lines or '.' to finish, '<' to cancel):\n")
    all_lines = []
    blank_count = 0
    while True:
        try:
            line = input("  > ")
        except EOFError:
            break
        if line.strip() == BACK_CMD:
            return ""
        if line.strip() == ".":
            break
        if not line.strip():
            blank_count += 1
            if blank_count >= 2:
                break
            all_lines.append("")
            continue
        blank_count = 0
        all_lines.append(line)

    return "\n".join(all_lines).strip()


def _flatten_skill_entry(entry: dict) -> dict:
    """Flatten LLM output (vars/text/battle) into override format."""
    text = entry.get("text", {})
    result = {}
    if isinstance(text, dict):
        for k, v in text.items():
            result[k] = v
    if entry.get("vars"):
        result["vars"] = entry["vars"]
    if entry.get("battle"):
        result["battle"] = entry["battle"]
    return result


def _ask_skill_metadata(name: str, result: dict) -> bool:
    """Ask user for metadata LLM couldn't determine. Modifies result in place.
    Returns False if user wants to go back (skip this item)."""
    try:
        if not result.get("is_event_skill"):
            if prompt_confirm(f"  Is '{name}' an event skill (事件戰法)?", default=False):
                result["is_event_skill"] = True

        if not result.get("is_event_skill"):
            if not result.get("unique_hero"):
                uh = prompt_input(f"  Unique hero for '{name}' (固有武將, empty if teachable)", required=False)
                if uh:
                    result["unique_hero"] = uh
                    result["is_unique"] = True
            if not result.get("unique_hero") and not result.get("source_hero"):
                sh = prompt_input(f"  Source hero for '{name}' (傳承者, empty if none)", required=False)
                if sh:
                    result["source_hero"] = sh
        return True
    except GoBack:
        return False


def do_quick_add(model: str):
    print("\n=== Quick Add ===")
    print("  1. Skills (default)")
    print("  2. Heroes")
    print("  3. Mixed (skills + heroes)")
    mode = prompt_input("Mode", default="1")

    if mode not in ("1", "2", "3"):
        print("[error] Invalid mode")
        return

    raw_paste = _collect_raw_input()
    if not raw_paste:
        print("[cancelled]")
        return

    # --- Build prompt: send entire paste as one block, let LLM split ---
    if mode in ("1", "3"):
        user = f"""\
The following is raw skill data (already in Traditional Chinese).
Parse ALL skills and output each as a separate top-level YAML key with `vars`, `text`, and `battle` sections.

IMPORTANT: In the `text` section, include a `raw_text` field containing the EXACT original text
from the input that describes this skill (copy verbatim, do not paraphrase or reformat).

---
{raw_paste}
---
Output YAML: each skill name as a top-level key, containing `vars`, `text` (with `raw_text`), and `battle` sections.
Parse ALL skills in the input above."""
        system = OVERRIDE_SYSTEM_PROMPT
    else:
        user = f"""\
Parse all heroes below. Extract: name, rarity (1-5), cost, faction, clan, gender,
stats (lea/val/int/pol/cha/spd), unique_skill, teachable_skill, assembly_skill, and traits.

---
{raw_paste}
---
Output YAML: each hero name as top-level key with all fields."""
        system = OVERRIDE_SYSTEM_PROMPT

    print(f"\n[llm] Processing...")
    try:
        raw_resp = call_llm(user, system_prompt=system, model=model, timeout=300)
        parsed = parse_llm_output(raw_resp)
    except Exception as e:
        print(f"[error] LLM call failed: {e}")
        return

    if parsed is None:
        print("[error] Failed to parse LLM response.")
        print(f"  Raw output:\n{raw_resp[:500]}")
        return

    parsed_keys = list(parsed.keys())
    parsed_values = list(parsed.values())

    # Confirm count — warn but continue if user says no
    count_warning = False
    print(f"\n  LLM parsed {len(parsed_keys)} item(s):")
    for i, k in enumerate(parsed_keys, 1):
        print(f"    {i}. {k}")
    if not prompt_confirm(f"  {len(parsed_keys)} items, correct?", default=True):
        count_warning = True
        print("  [warn] Count mismatch noted — will warn at the end. Continuing...")

    # --- Validate and collect good/bad ---
    good: list[tuple[str, dict, dict]] = []  # (name, entry, result)
    bad: list[tuple[str, dict, str]] = []  # (name, entry, errors)

    for i, (name, entry) in enumerate(zip(parsed_keys, parsed_values)):
        if mode in ("1", "3"):
            errors = validate_skill_entry(entry)
            if errors:
                print(f"  [INVALID] {name}: {'; '.join(errors)}")
                bad.append((name, entry, "; ".join(errors)))
                continue
            quality = validate_entry_quality(entry)
            if quality:
                print(f"  [QUALITY] {name}: {'; '.join(quality)}")
            else:
                print(f"  [VALID] {name}")
            result = _flatten_skill_entry(entry)
        else:
            if not isinstance(entry, dict) or not entry.get("name"):
                print(f"  [INVALID] {name}: missing name")
                bad.append((name, entry, "missing name"))
                continue
            print(f"  [VALID] {name}")
            result = entry

        good.append((name, entry, result))

    # --- Retry bad ones with error feedback ---
    if bad and mode in ("1", "3"):
        print(f"\n[retry] {len(bad)} failed item(s)...")
        error_summary = "\n".join(f"  {name}: {errs}" for name, _, errs in bad)
        bad_descriptions = "\n".join(
            f"Skill: {name}" for name, _, _ in bad
        )
        retry_user = f"""\
Previous attempt had errors:
{error_summary}

Fix these errors. Re-parse these skills from the original input:

---
{raw_paste}
---
Only output the failed skills: {', '.join(name for name, _, _ in bad)}"""

        try:
            raw_resp = call_llm(retry_user, system_prompt=system, model=model, timeout=300)
            retry_parsed = parse_llm_output(raw_resp)
        except Exception as e:
            print(f"  [retry failed] {e}")
            retry_parsed = None

        if retry_parsed:
            for rname, rentry in retry_parsed.items():
                errors = validate_skill_entry(rentry)
                if errors:
                    print(f"  [STILL BAD] {rname}: {'; '.join(errors)}")
                    continue
                quality = validate_entry_quality(rentry)
                if quality:
                    print(f"  [QUALITY] {rname}: {'; '.join(quality)}")
                else:
                    print(f"  [FIXED] {rname}")
                result = _flatten_skill_entry(rentry)
                good.append((rname, rentry, result))

    if not good:
        print("\n[done] No valid items to add.")
        return

    # --- Check hero skill references (issue 2) ---
    if mode in ("2", "3"):
        existing_skills = load_existing_skills()
        ov = load_overrides()
        override_skills = ov.get("skills", {})
        # Collect all known skill names: keys + translated names + names from this batch
        all_skill_names = set(existing_skills.keys()) | set(override_skills.keys())
        for sk in existing_skills.values():
            if isinstance(sk, dict) and sk.get("text", {}).get("name"):
                all_skill_names.add(sk["text"]["name"])
        for sk in override_skills.values():
            if isinstance(sk, dict) and sk.get("name"):
                all_skill_names.add(sk["name"])
        # Also include skills from this batch
        for gname, _, gresult in good:
            all_skill_names.add(gname)
            if isinstance(gresult, dict) and gresult.get("name"):
                all_skill_names.add(gresult["name"])

        for name, entry, result in good:
            is_hero = "stats" in result or mode == "2"
            if not is_hero:
                continue
            for field in ("unique_skill", "teachable_skill"):
                sk = result.get(field, "")
                if sk and sk not in all_skill_names:
                    print(f"  [warn] Hero '{name}' references skill '{sk}' ({field}) — not found")

    # --- Confirm each item ---
    overrides = load_overrides()
    overrides.setdefault("skills", {})
    overrides.setdefault("heroes", {})
    added = 0
    accept_all = False
    overwrite_all = False

    print(f"\n  {len(good)} item(s) ready. Confirm each: y=accept, n=skip, yy=accept all remaining")

    for seq, (name, entry, result) in enumerate(good):
        print(f"\n--- [{seq+1}/{len(good)}] {name} ---")

        # Always ask for metadata (even under yy)
        if mode in ("1", "3") and isinstance(entry, dict) and "battle" in entry:
            if not _ask_skill_metadata(name, result):
                print(f"  [skipped]")
                continue

        if not accept_all:
            # Show preview before asking
            print(yaml.dump({name: result}, allow_unicode=True, default_flow_style=False, sort_keys=False))

            # Check overwrite
            if not overwrite_all:
                existing = overrides.get("skills", {}).get(name) or overrides.get("heroes", {}).get(name)
                if existing:
                    desc = existing.get("description", "")
                    print(f"  [warn] '{name}' already exists (type: {existing.get('type', '?')}, rarity: {existing.get('rarity', '?')})")
                    if desc:
                        print(f"    description: {desc[:80]}{'...' if len(desc) > 80 else ''}")
                    ow = prompt_input("  Overwrite? (y/n/yy=overwrite all)", default="n").strip().lower()
                    if ow == "yy":
                        overwrite_all = True
                    elif ow != "y":
                        print(f"  [skipped]")
                        continue

            answer = prompt_input("  Accept? (y/n/yy)", default="y").strip().lower()
            if answer == "yy":
                accept_all = True
            elif answer != "y":
                print(f"  [skipped]")
                continue
        else:
            # accept_all: still check overwrite
            if not overwrite_all:
                existing = overrides.get("skills", {}).get(name) or overrides.get("heroes", {}).get(name)
                if existing:
                    print(f"  [warn] '{name}' already exists — skipped (use overwrite-all to force)")
                    continue

        # Save
        is_hero = mode == "2" or (mode == "3" and "stats" in result)
        if is_hero:
            result["_action"] = "add"
            overrides["heroes"][name] = result
        else:
            result["_action"] = "add"
            overrides["skills"][name] = result
        added += 1
        print(f"  [added]")

    if added:
        save_overrides(overrides)

    # Final summary
    warnings = []
    if count_warning:
        warnings.append("LLM item count was flagged as incorrect")
    if bad:
        still_bad = [name for name, _, _ in bad if not any(n == name for n, _, _ in good)]
        if still_bad:
            warnings.append(f"{len(still_bad)} item(s) failed validation: {', '.join(still_bad)}")

    print(f"\n[done] {added}/{len(good)} item(s) added to {OVERRIDES_YAML}")
    if warnings:
        for w in warnings:
            print(f"  [warn] {w}")


def _add_skill_for_hero(skill_name: str, label: str, hero_name: str, model: str):
    """Shortcut to add a skill referenced by a hero."""
    is_unique = label == "固有技能"
    skill_type = prompt_choice("Type", ["被動", "主動", "指揮", "突擊", "兵種"])
    rarity = prompt_choice("Rarity", ["S", "A", "B"])
    target = prompt_input("Target (e.g., 敵軍單體, 自身, 我方全體)")
    description = prompt_input("Skill description (natural language, can include numbers)")

    info = {
        "name": skill_name, "type": skill_type, "rarity": rarity,
        "target": target, "description": description, "is_event": False,
        "source_hero": hero_name if not is_unique else "",
        "unique_hero": hero_name if is_unique else "",
    }

    print("\n[llm] Formatting skill data...")
    out = _process_skill_with_llm(info, model)
    if out is None:
        return

    name, result = out
    print("\n[preview] Skill to add:")
    print(yaml.dump({name: result}, allow_unicode=True, default_flow_style=False, sort_keys=False))

    overrides = load_overrides()
    overrides.setdefault("skills", {})

    if not _confirm_overwrite(name, overrides):
        print(f"[skipped] {name}")
        return
    if not prompt_confirm("Add this skill?"):
        print(f"[skipped] {name}")
        return

    overrides["skills"][name] = result
    save_overrides(overrides)
    print(f"[done] Skill '{name}' added to {OVERRIDES_YAML}")


# ---------------------------------------------------------------------------
# Recompile overrides
# ---------------------------------------------------------------------------

OVERRIDE_SYSTEM_PROMPT = f"""\
You are a game data formatter for 信長之野望：真戰 (Nobunaga's Ambition: Shinsei).
The input is already in Traditional Chinese — do NOT translate, just extract and reformat.

{COMMON_RULES}

{SKILL_OUTPUT_FORMAT}"""


def do_recompile(model: str, name_filter: str | None = None, dry_run: bool = False):
    """Recompile override skills from raw_text into current structured format."""
    overrides = load_overrides()
    skills = overrides.get("skills", {})

    # Find skills with raw_text that need recompiling
    targets = {}
    for key, skill in skills.items():
        if skill.get("_action") != "add":
            continue
        raw = skill.get("raw_text")
        if not raw:
            continue
        if name_filter and name_filter not in key:
            continue
        targets[key] = skill

    if not targets:
        print("[recompile] No skills with raw_text found.")
        if not name_filter:
            print("  Add raw_text field to override skills to enable recompiling.")
        return

    print(f"[recompile] {len(targets)} skills to process with {model}")

    # Build batch prompt
    blocks = []
    for i, (key, skill) in enumerate(targets.items(), 1):
        meta_parts = []
        if skill.get("is_event_skill"):
            meta_parts.append("Event skill (事件戰法)")
        if skill.get("unique_hero"):
            meta_parts.append(f"Unique to: {skill['unique_hero']}")
        if skill.get("source_hero"):
            meta_parts.append(f"Teachable from: {skill['source_hero']}")
        meta = "; ".join(meta_parts) or "none"

        blocks.append(f"""\
Skill {i}:
  name: {skill.get('name', key)}
  type: {skill.get('type', 'unknown')}
  rarity: {skill.get('rarity', 'S')}
  target: {skill.get('target', '')}
  activation_rate: {skill.get('activation_rate', '')}
  metadata: {meta}
  raw_text: |
    {skill['raw_text']}""")

    user = f"""\
Reformat these {len(targets)} skills into the current structured format.
Each already has a Chinese description — do NOT translate, just reformat.

{chr(10).join(blocks)}

---
Output YAML: each skill name as a top-level key, containing `vars`, `text`, and `battle` sections."""

    print(f"[llm] Sending {len(targets)} skills...")
    try:
        raw = call_llm(user, system_prompt=OVERRIDE_SYSTEM_PROMPT, model=model, timeout=300)
        parsed = parse_llm_output(raw)
    except Exception as e:
        print(f"[error] LLM call failed: {e}")
        return

    if not parsed:
        print("[error] Failed to parse LLM output")
        return

    parsed_values = list(parsed.values())
    updated = 0

    for i, (key, skill) in enumerate(targets.items()):
        entry = parsed.get(key) or parsed.get(skill.get("name", ""))
        if not entry and i < len(parsed_values):
            entry = parsed_values[i]
        if not entry:
            print(f"  MISSING: {key}")
            continue

        # Auto-fix
        text = entry.get("text", {})
        if isinstance(text, dict):
            fixes = autofix_frontend(text)
            if fixes:
                print(f"  [autofix] {key}: {'; '.join(fixes)}")

        # Preview
        print(f"\n{'='*50}")
        print(f"  {key}:")
        print(yaml.dump(entry, allow_unicode=True, default_flow_style=False, sort_keys=False, indent=2))

        if dry_run:
            updated += 1
            continue

        if not prompt_confirm(f"  Apply recompile for '{key}'?"):
            print(f"  [skip] {key}")
            continue

        # Merge back: keep raw_text + metadata, update structured fields
        new_skill = {"_action": "add", "raw_text": skill["raw_text"]}
        # Preserve metadata
        for meta_key in ("is_event_skill", "unique_hero", "is_unique", "source_hero"):
            if meta_key in skill:
                new_skill[meta_key] = skill[meta_key]

        # Flatten text section into top level (override format is flat)
        if isinstance(text, dict):
            for tk, tv in text.items():
                new_skill[tk] = tv
        # Keep vars and battle at top level
        if entry.get("vars"):
            new_skill["vars"] = entry["vars"]
        if entry.get("battle"):
            new_skill["battle"] = entry["battle"]

        overrides["skills"][key] = new_skill
        updated += 1

    if not dry_run and updated:
        save_overrides(overrides)
    print(f"\n[recompile] {updated}/{len(targets)} skills processed")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    p = argparse.ArgumentParser(description="Interactive override manager for game data")
    p.add_argument("--modify-skill", action="store_true", help="Modify an existing skill")
    p.add_argument("--recompile", action="store_true", help="Recompile override skills from raw_text")
    p.add_argument("--dry-run", action="store_true", help="Preview recompile without saving")
    p.add_argument("--name", help="Filter by name (for --recompile)")
    p.add_argument("--model", default=DEFAULT_MODEL, help="OpenRouter model to use")
    args = p.parse_args()

    if args.recompile:
        do_recompile(args.model, name_filter=args.name, dry_run=args.dry_run)
        return

    if args.modify_skill:
        do_modify_skill(args.model)
    else:
        do_quick_add(args.model)


if __name__ == "__main__":
    main()
