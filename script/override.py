"""
Interactive CLI for managing data overrides.

Supports:
  - Modify existing skills via natural language instructions
  - Add new skills (regular or event skills)
  - Add new heroes

Uses Gemini LLM to validate modifications and format new entries.

Usage:
    python script/override.py --modify-skill
    python script/override.py --add-skill
    python script/override.py --add-hero
    python script/override.py --model gemini-3.1-pro-preview
"""

import argparse
import json
import sys
import yaml
from pathlib import Path

from claude_test import call_claude
from llm_core import (
    CANONICAL_STATUSES, COMMON_RULES, SKILL_TAGS, DEFAULT_MODEL,
    call_gemini, parse_llm_output, autofix_frontend, load_overrides,
)
from paths import (
    OVERRIDES_YAML, SKILLS_CRAWLED,
    SKILLS_TRANSLATED, TRAITS_TRANSLATED,
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
    """Load translated skills for reference during modifications."""
    if SKILLS_TRANSLATED.exists():
        data = yaml.safe_load(SKILLS_TRANSLATED.read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    return {}


def load_existing_traits() -> dict:
    """Load translated traits for lookup during hero creation."""
    if TRAITS_TRANSLATED.exists():
        data = yaml.safe_load(TRAITS_TRANSLATED.read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    return {}


def _check_back(val: str):
    if val == BACK_CMD:
        raise GoBack()


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
        raw = call_gemini(prompt, model=model)
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

ADD_SKILL_TASK_RULES = """\
Rules:
1. Output a single YAML dict (no top-level key) with these fields:
   name, type, rarity, target, activation_rate, description, vars, brief_description, tags
2. All text in Traditional Chinese.
3. If the description mentions 大將技, split it: put the main part in `description` and the commander part in `commander_description`.
4. `brief_description`: 15-25 chars, summarize the core mechanic without numbers.
5. `tags`: list from ONLY these allowed tags: """ + SKILL_TAGS + """
   Pick all that apply."""


def _build_add_skill_prompt(info: dict) -> str:
    name = info["name"]
    is_event = "true" if info["is_event"] else "false"
    source_hero = info["source_hero"] or "none"
    unique_hero = info["unique_hero"] or "none"
    description = info["description"]
    return f"""\
You are a game data formatter for 信長之野望：真戰 (Nobunaga's Ambition: Shinsei).

{COMMON_RULES}

Convert the following skill information into the standard frontend format.

Skill info:
  name: {name}
  type: {info["type"]}
  rarity: {info["rarity"]}
  target: {info["target"]}
  is_event_skill: {is_event}
  source_hero: {source_hero}
  unique_hero: {unique_hero}
  raw_description: |
    {description}

{ADD_SKILL_TASK_RULES}"""


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
        raw = call_gemini(prompt, model=model)
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
    for name, result in results:
        overrides["skills"][name] = result
    save_overrides(overrides)
    print(f"[done] {len(results)} skill(s) added to {OVERRIDES_YAML}")


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
# Quick Add Skill (natural language)
# ---------------------------------------------------------------------------


def _collect_one_quick_skill() -> dict | None:
    """Collect one skill's raw text + metadata. Returns dict or None."""
    print("  Paste skill info (blank line to finish, '<' to cancel):")
    lines = []
    while True:
        try:
            line = input("  > ")
        except EOFError:
            break
        if line.strip() == BACK_CMD:
            return None
        if not line.strip() and lines:
            break
        lines.append(line)

    if not lines:
        return None

    raw_input = "\n".join(lines)

    is_event = prompt_confirm("Is this an event skill (事件戰法)?", default=False)
    unique_hero = ""
    source_hero = ""
    if not is_event:
        unique_hero = prompt_input("Unique hero (固有武將, empty if teachable)", required=False)
        if not unique_hero:
            source_hero = prompt_input("Source hero (傳承者)", required=False)

    return {
        "raw_input": raw_input,
        "is_event": is_event,
        "unique_hero": unique_hero,
        "source_hero": source_hero,
    }


QUICK_BATCH_TASK_RULES = """\
Rules:
1. Output YAML with each skill name as a top-level key, containing:
   name, type, rarity, target, activation_rate, description, vars, brief_description, tags
2. If the text mentions 大將技, split into `description` and `commander_description`.
3. Map type keywords: "謀略群體" → target=敵軍群體; "兵刃單體" → target=敵軍單體; etc.
4. All text in Traditional Chinese.
5. `brief_description`: 15-25 chars, summarize the core mechanic without numbers.
6. `tags`: list from ONLY these allowed tags: """ + SKILL_TAGS + """
   Pick all that apply."""


def _build_quick_batch_prompt(queue: list[dict]) -> str:
    blocks = []
    for i, info in enumerate(queue, 1):
        context_parts = []
        if info["is_event"]:
            context_parts.append("Event skill (事件戰法).")
        if info["unique_hero"]:
            context_parts.append(f"Unique skill of {info['unique_hero']}.")
        if info["source_hero"]:
            context_parts.append(f"Teachable from {info['source_hero']}.")
        ctx = " ".join(context_parts) or "none"
        blocks.append(f"Skill {i}:\n{info['raw_input']}\nContext: {ctx}")

    count = len(queue)
    skill_blocks = "\n\n".join(blocks)
    return f"""\
You are a game data formatter for 信長之野望：真戰 (Nobunaga's Ambition: Shinsei).

{COMMON_RULES}

The user provided {count} skills in free-form text. Parse each and output structured YAML.

{skill_blocks}

{QUICK_BATCH_TASK_RULES}
Process ALL {count} skills."""


def _apply_metadata(result: dict, info: dict) -> dict:
    """Apply _action and ownership metadata to a parsed skill result."""
    fixes = autofix_frontend(result)
    if fixes:
        print(f"    [autofix] {'; '.join(fixes)}")
    result["_action"] = "add"
    if info["is_event"]:
        result["is_event_skill"] = True
    if info["unique_hero"]:
        result["unique_hero"] = info["unique_hero"]
        result["is_unique"] = True
    if info["source_hero"]:
        result["source_hero"] = info["source_hero"]
    return result


def do_quick_add_skill(model: str):
    print("\n=== Quick Add Skill (natural language, batch) ===")
    print("  Collect skills first, then run ONE LLM call for all.\n")

    queue = []
    while True:
        print(f"\n--- Skill #{len(queue) + 1} ---")
        info = _collect_one_quick_skill()
        if info is None:
            if not queue:
                print("[cancelled]")
                return
            print("  (skipped)")
        else:
            queue.append(info)
            label = info["raw_input"].split("\n")[0][:40]
            print(f"  [queued] {label}")

        if queue:
            print(f"\n  Queue: {len(queue)} skill(s)")
            choice = prompt_choice("Action", ["add", "run"], default="add")
            if choice == "run":
                break

    # Single LLM call for entire batch
    prompt = _build_quick_batch_prompt(queue)
    print(f"\n[llm] Processing {len(queue)} skill(s) in one call...")
    try:
        timeout = 60 + 40 * len(queue)
        raw = call_gemini(prompt, model=model, timeout=timeout)
        parsed = parse_llm_output(raw)
    except Exception as e:
        print(f"[error] LLM call failed: {e}")
        return

    if parsed is None:
        print("[error] Failed to parse LLM response.")
        print(f"  Raw output:\n{raw[:500]}")
        return

    # Match results to queue by position (LLM preserves input order)
    parsed_keys = list(parsed.keys())
    parsed_values = list(parsed.values())

    # Approve one-by-one
    overrides = load_overrides()
    overrides.setdefault("skills", {})
    added = 0

    for i, info in enumerate(queue):
        if i < len(parsed_values):
            result = parsed_values[i]
            skill_name = result.get("name", parsed_keys[i] if i < len(parsed_keys) else f"skill_{i}")
        else:
            print(f"\n  [missing] Skill #{i+1} not in LLM output, skipped.")
            continue

        _apply_metadata(result, info)

        print(f"\n--- [{i+1}/{len(queue)}] {skill_name} ---")
        print(yaml.dump({skill_name: result}, allow_unicode=True, default_flow_style=False, sort_keys=False))

        if prompt_confirm(f"Add '{skill_name}'?"):
            overrides["skills"][skill_name] = result
            added += 1
            print(f"  [added]")
        else:
            print(f"  [skipped]")

    if added:
        save_overrides(overrides)
        print(f"\n[done] {added}/{len(queue)} skill(s) added to {OVERRIDES_YAML}")
    else:
        print("\n[done] No skills added.")


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

    if not prompt_confirm("Add this skill?"):
        print(f"[skipped] {name}")
        return

    overrides = load_overrides()
    overrides.setdefault("skills", {})
    overrides["skills"][name] = result
    save_overrides(overrides)
    print(f"[done] Skill '{name}' added to {OVERRIDES_YAML}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def claude_test(num: int = 10, model: str = "haiku"):
    """Run sample prompts through Claude CLI for testing. No files saved."""
    import random
    skills = load_existing_skills()
    if not skills:
        print("[error] No translated skills found.")
        return

    items = list(skills.items())
    samples = random.sample(items, min(num, len(items)))

    # Test 1: modify-skill
    target_key, target_data = samples[0]
    skill_yaml = yaml.dump(
        {target_key: target_data},
        allow_unicode=True, default_flow_style=False, sort_keys=False,
    )
    prompt = _build_modify_prompt(skill_yaml, "倍率從20變成35")
    print(f"\n{'='*60}")
    print(f"TEST 1: modify-skill ({target_key})")
    print(f"{'='*60}")
    try:
        raw = call_claude(prompt, model=model)
        parsed = parse_llm_output(raw)
        if parsed and not parsed.get("_rejected"):
            print(f"  Changes: {list(parsed.keys())}")
            print(yaml.dump(parsed, allow_unicode=True, default_flow_style=False, sort_keys=False))
        elif parsed and parsed.get("_rejected"):
            print(f"  [rejected] {parsed.get('reason', '?')}")
        else:
            print(f"  [PARSE FAIL] {raw[:300]}")
    except Exception as e:
        print(f"  [ERROR] {e}")

    # Test 2: add-skill
    info = {
        "name": "測試技能", "type": "主動", "rarity": "S",
        "target": "敵軍單體", "is_event": False,
        "source_hero": "測試武將", "unique_hero": "",
        "description": "對敵軍單體造成58%→116%兵刃傷害（受武勇影響），並有30%機率施加麻痺狀態，持續2回合",
    }
    prompt2 = _build_add_skill_prompt(info)
    print(f"\n{'='*60}")
    print(f"TEST 2: add-skill")
    print(f"{'='*60}")
    try:
        raw = call_claude(prompt2, model=model)
        parsed = parse_llm_output(raw)
        if parsed:
            print(f"  name: {parsed.get('name', '?')}")
            print(f"  desc: {parsed.get('description', '?')[:80]}")
            print(f"  vars: {list(parsed.get('vars', {}).keys())}")
        else:
            print(f"  [PARSE FAIL] {raw[:300]}")
    except Exception as e:
        print(f"  [ERROR] {e}")

    # Test 3: quick-batch with crawled data
    crawled_path = SKILLS_CRAWLED
    if crawled_path.exists():
        crawled = yaml.safe_load(crawled_path.read_text("utf-8"))
        crawled_items = list(crawled.items())
        quick_samples = random.sample(crawled_items, min(num, len(crawled_items)))
        queue = []
        for name, sk in quick_samples:
            raw_text = f"{name} ({sk.get('rarity', '?')})\n種類：{sk.get('type', '?')}\n發動機率：{sk.get('activation_rate', '?')}\n效果：{sk.get('description', '')}"
            queue.append({
                "raw_input": raw_text, "is_event": False,
                "unique_hero": sk.get("source_hero", "") if sk.get("is_unique") else "",
                "source_hero": sk.get("source_hero", "") if not sk.get("is_unique") else "",
            })
        prompt3 = _build_quick_batch_prompt(queue)
        print(f"\n{'='*60}")
        print(f"TEST 3: quick-batch ({len(queue)} skills)")
        print(f"Skills: {', '.join(n for n, _ in quick_samples)}")
        print(f"{'='*60}")
        try:
            raw = call_claude(prompt3, model=model)
            parsed = parse_llm_output(raw)
            if parsed:
                for key, val in parsed.items():
                    name = val.get("name", key) if isinstance(val, dict) else key
                    print(f"  {key} → {name}")
            else:
                print(f"  [PARSE FAIL] {raw[:300]}")
        except Exception as e:
            print(f"  [ERROR] {e}")

    print(f"\n[claude-test] Done. No files were modified.")


def main():
    p = argparse.ArgumentParser(description="Interactive override manager for game data")
    p.add_argument("--modify-skill", action="store_true", help="Modify an existing skill")
    p.add_argument("--add-skill", action="store_true", help="Add a new skill (guided)")
    p.add_argument("--quick-add", action="store_true", help="Add a skill from natural language")
    p.add_argument("--add-hero", action="store_true", help="Add a new hero")
    p.add_argument("--model", default=DEFAULT_MODEL, help="Gemini model to use")
    p.add_argument("--claude-test", action="store_true", help="Print sample prompts for Claude Code testing (no LLM call, no file writes)")
    p.add_argument("--test-num", type=int, default=10, help="Number of random samples for --claude-test")
    args = p.parse_args()

    if args.claude_test:
        claude_test(num=args.test_num, model=args.model)
        return

    if not any([args.modify_skill, args.add_skill, args.quick_add, args.add_hero]):
        print("Choose an action:")
        print("  1. Modify existing skill")
        print("  2. Add new skill (guided, batch)")
        print("  3. Add new skill (natural language)")
        print("  4. Add new hero")
        choice = prompt_input("Action", default="3")
        if choice == "1":
            args.modify_skill = True
        elif choice == "2":
            args.add_skill = True
        elif choice == "3":
            args.quick_add = True
        elif choice == "4":
            args.add_hero = True
        else:
            print("[error] Invalid choice")
            return

    if args.modify_skill:
        do_modify_skill(args.model)
    elif args.add_skill:
        do_add_skill(args.model)
    elif args.quick_add:
        do_quick_add_skill(args.model)
    elif args.add_hero:
        do_add_hero(args.model)


if __name__ == "__main__":
    main()
