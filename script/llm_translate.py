"""
LLM-based skill translator and battle engine extractor.

Reads crawled YAML, sends skills to Gemini in batches for:
  1. Translation (JP → CHT) for frontend display
  2. Battle engine structured extraction (vars, triggers, effects)

Usage:
    python script/llm_translate.py [options]

Examples:
    python script/llm_translate.py --limit 3               # test 3 skills
    python script/llm_translate.py --name 武田之赤備         # single skill
    python script/llm_translate.py                          # all skills
    python script/llm_translate.py --force --limit 5        # re-process, overwrite cache + output
    python script/llm_translate.py --batch-size 3           # 3 skills per LLM call
    python script/llm_translate.py --model gemini-3.1-pro-preview
"""

import argparse
import json
import sys
import yaml
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from tqdm import tqdm

from claude_test import call_claude
from llm_core import (
    CANONICAL_STATUSES, COMMON_RULES, SKILL_TAGS, DEFAULT_MODEL,
    call_gemini, parse_llm_output, autofix_frontend,
    load_llm_cache, save_llm_cache, save_raw_cache,
)
from paths import (
    HEROES_CRAWLED, SKILLS_CRAWLED, TRAITS_CRAWLED,
    SKILLS_TRANSLATED, SKILLS_BATTLE,
    TRAITS_TRANSLATED, TRAITS_BATTLE,
    SKILLS_CANONICAL, TRAITS_CANONICAL,
    HEROES_TRANSLATED,
    TRANSLATION_FAILURES_JSON,
)
DEFAULT_BATCH_SIZE = 5

# In-process accumulator for failures across all process_* runs in a single
# invocation. Flushed to TRANSLATION_FAILURES_JSON in main().
_FAILURE_LOG: dict[str, list[dict]] = {"skills": [], "traits": [], "heroes": []}


def _record_failures(kind: str, failed: list[tuple[str, str]]):
    for name, err in failed:
        _FAILURE_LOG[kind].append({"name": name, "error": err})


def _write_failure_manifest():
    """Write a manifest with copy-pasteable suggested fixes for the admin.

    Always overwrites the file: an empty manifest is itself useful (signals
    "last run was clean"). The build is NOT failed here — check_data_integrity
    is the gatekeeper.
    """
    has_any = any(_FAILURE_LOG.values())
    # NOTE: do NOT suggest --force here. --force means "ignore cache and
    # re-call the LLM". For LLM-side failures the cache miss already forces a
    # call, so --force only burns extra quota. The admin can add --force
    # manually if they actually want to re-translate something that succeeded
    # but looks wrong.
    suggestions: list[str] = []
    for kind, items in _FAILURE_LOG.items():
        if not items:
            continue
        names = sorted({item["name"] for item in items})
        if len(names) == 1:
            suggestions.append(
                f'python3 script/llm_translate.py --{kind} --name "{names[0]}"'
            )
        else:
            suggestions.append(f"python3 script/llm_translate.py --{kind}")
    if suggestions:
        suggestions.append(
            "python3 script/build_frontend_data.py && python3 script/check_data_integrity.py"
        )

    manifest = {
        "ok": not has_any,
        "summary": {kind: len(items) for kind, items in _FAILURE_LOG.items()},
        "failures": _FAILURE_LOG,
        "suggested_actions": suggestions,
    }
    TRANSLATION_FAILURES_JSON.parent.mkdir(parents=True, exist_ok=True)
    TRANSLATION_FAILURES_JSON.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8"
    )

    if has_any:
        total = sum(len(v) for v in _FAILURE_LOG.values())
        tqdm.write(f"\n[warn] {total} item(s) failed translation. Manifest: {TRANSLATION_FAILURES_JSON}")
        tqdm.write("[suggested actions — copy/paste to retry]")
        for s in suggestions:
            tqdm.write(f"  {s}")
    else:
        tqdm.write(f"\n[ok] No translation failures. Manifest: {TRANSLATION_FAILURES_JSON}")


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = f"""\
You are a game data translator and structured extractor for 信長之野望：真戰 (Nobunaga's Ambition: Shinsei).

{COMMON_RULES}

For EACH skill, output a YAML document under that skill's name as the top-level key, containing THREE sections:

## `vars` — Shared variables (SINGLE source of numeric truth)
- Extract ALL numeric values referenced in both text and battle into ONE shared `vars` dict.
- Scaling values: use nested {{base, max, scale}} (e.g. {{base: 0.30, max: 0.60, scale: 武勇}}).
- Fixed values: use plain int/float (e.g. duration: 2).
- CRITICAL: `text.description` uses {{var:key}} to reference these vars.
  `battle.do` uses $key to reference these vars. Both reference the SAME vars dict.
  Do NOT duplicate vars between text and battle.

## `text` — Translation for frontend rendering (JP → Traditional Chinese)
- Translate to Traditional Chinese (繁體中文)
- `rarity` must be just: S, A, or B
- `brief_description`: 15-25 chars, summarize the core mechanic without numbers
- `tags`: list from ONLY these allowed tags: """ + SKILL_TAGS + """
- Use {{var:key}} in description to reference the shared vars dict
- Do NOT include a `vars` field here — vars live at the top level

## `battle` — Structured extraction for battle engine
- ALL text (including `bonus.commander.description`) must be in Traditional Chinese (繁體中文)
- Use $key to reference the shared vars dict — do NOT include a `vars` field here
- Map effects to `do` blocks: trigger/when/to/do
- Effect types: damage, heal, buff, debuff, applyStatus, removeStatus, addStack, roll, sequence, conditional
- Trigger types: always, battleStart, turnStart, beforeAction, afterAction, beforeAttack, afterAttack, onDamaged, onHeal
- Target types: self, allySingle, allyMultiple, allyAll, enemySingle, enemyMultiple, enemyAll
- 大将技 → `bonus.commander`"""


def build_single_prompt(skill: dict) -> str:
    raw = skill.get("raw", skill)  # support both canonical (has .raw) and legacy shape
    return f"""\
{SYSTEM_PROMPT}

---
Input skill:
name: {raw.get('name', skill.get('name', ''))}
type: {raw.get('type', 'unknown')}
rarity: {raw.get('rarity', '')}
target: {raw.get('target', '')}
activation_rate: {raw.get('activation_rate', '')}
source_hero: {raw.get('source_hero', '')}
description: |
  {raw.get('description', '')}
commander_bonus: {raw.get('commander_bonus', '') or 'none'}

---
Example output:
軍神:
  vars:
    charge_trigger_rate:
      base: 0.30
      max: 0.60
      scale: 武勇
    damage_per_stack:
      base: 0.05
      max: 0.10
      scale: 武勇
    max_charge: 12
    ally_count: 2
  text:
    name: 軍神
    type: 被動
    rarity: S
    target: 自己
    activation_rate: 100%
    description: >
      戰鬥中，以無法獲得{{status:亂舞}}狀態為代價，
      使友軍群體（{{var:ally_count}}人）有{{var:charge_trigger_rate}}機率（{{scale:武勇}}）使自身蓄力，
      普通攻擊傷害提高{{var:damage_per_stack}}（{{scale:武勇}}），最多疊{{var:max_charge}}次。
    brief_description: 犧牲亂舞，友軍蓄力提升普攻傷害
    tags: [增益, 被動觸發, 武勇系]
  battle:
    type: 被動
    trigger: always
    do:
      - trigger: afterAllyAction
        to: self
        do:
          type: roll
          chance: $charge_trigger_rate
          on_success:
            - type: addStack
              key: god_of_war_charge
              value: 1
              max: $max_charge

---
Output the YAML with skill name as top-level key, containing `vars`, `text`, and `battle`."""


def build_batch_prompt(skills: list[tuple[str, dict]]) -> str:
    skill_blocks = []
    for i, (name, skill) in enumerate(skills, 1):
        raw = skill.get("raw", skill)
        skill_blocks.append(f"""\
Skill {i}:
  name: {raw.get('name', name)}
  type: {raw.get('type', 'unknown')}
  rarity: {raw.get('rarity', '')}
  target: {raw.get('target', '')}
  activation_rate: {raw.get('activation_rate', '')}
  source_hero: {raw.get('source_hero', '')}
  description: |
    {raw.get('description', '')}
  commander_bonus: {raw.get('commander_bonus', '') or 'none'}""")

    joined = "\n\n".join(skill_blocks)

    return f"""\
{SYSTEM_PROMPT}

---
Input ({len(skills)} skills):

{joined}

---
Output YAML: each skill name as a top-level key, each containing `vars`, `text`, and `battle` sections.
`vars` is the SINGLE shared variable dict — do NOT put vars inside text or battle.
Process ALL {len(skills)} skills above."""


# ---------------------------------------------------------------------------
# Trait Prompts
# ---------------------------------------------------------------------------

ALLOWED_TROOP_TYPES_STR = "足輕, 弓兵, 騎兵, 鐵炮, 器械"

TRAIT_SYSTEM_PROMPT = f"""\
You are a game data translator and structured extractor for 信長之野望：真戰 (Nobunaga's Ambition: Shinsei).

{COMMON_RULES}

For EACH trait (特性), first determine its `kind`:

- `kind: passive` — always-on effect with NO engine trigger. Includes:
  - Troop affinity (兵種レベル): buffs a troop type level (output `passive.affinity`)
  - Flat stat/damage buffs: e.g. "造成兵刃傷害增加2.2%" (output `passive.buffs`)
- `kind: triggered` — activates on an engine event (battleStart, turnStart, afterAttack, etc.).
  Has a `battle` section with `trigger` + `do` blocks, same shape as a triggered skill.

Output YAML with the trait name as top-level key, containing these sections:

## `vars` — Shared variables (SINGLE source, same rules as skills)
- Only if the trait has numeric values. Both text and battle/passive reference this.

## `text` — Translation (JP → Traditional Chinese 繁體中文)
- `name`: translated trait name
- `description`: translated description, use {{var:key}} for numeric values

## For `kind: passive` → output `passive` section (NO `battle`):
- `passive.affinity` — for troop_affinity traits:
  - `troop_types`: MUST be a YAML list. Allowed values ONLY: {ALLOWED_TROOP_TYPES_STR}
    IMPORTANT: 兵器→器械, 槍兵→足輕, 鐵砲→鐵炮 (use the correct CHT names)
  - `level`: integer
  - `level_cap_bonus`: integer (0 if not mentioned; detect 等級上限増加N)
- `passive.buffs` — for flat %buff traits:
  - list of {{target, stat, type: pct|flat, value: $var_ref}}

## For `kind: triggered` → output `battle` section (NO `passive`):
- `trigger`: when it activates (battleStart, turnStart, beforeAction, afterAttack, etc.)
- `do`: structured effects
- Effect types: damage, heal, buff, debuff, applyStatus, removeStatus, addStack, roll, sequence, conditional
- Target types: self, allySingle, allyMultiple, allyAll, enemySingle, enemyMultiple, enemyAll

Example passive (troop affinity):
馬術Ⅲ:
  text:
    name: 馬術Ⅲ
    description: 部隊的騎兵等級增加3
  kind: passive
  passive:
    affinity:
      troop_types: [騎兵]
      level: 3
      level_cap_bonus: 0

Example passive (%buff):
攻勢Ⅱ:
  vars:
    dmg_bonus: 0.013
  text:
    name: 攻勢Ⅱ
    description: 自軍全體造成傷害提高{{var:dmg_bonus}}
  kind: passive
  passive:
    buffs:
      - target: armyAll
        stat: damage_dealt
        type: pct
        value: $dmg_bonus

Example triggered:
赤備え:
  vars:
    reduction: 18
  text:
    name: 赤備
    description: 首次普通攻擊後，使攻擊目標的統率降低{{var:reduction}}（可疊加）
  kind: triggered
  battle:
    trigger: afterNormalAttack
    do:
      - when: firstTime
        to: enemySingle
        do: debuff
        stat: 統率
        value: $reduction
        stackable: true"""


def build_trait_single_prompt(trait: dict) -> str:
    raw = trait.get("raw", trait)  # support both canonical (has .raw) and legacy shape
    return f"""\
{TRAIT_SYSTEM_PROMPT}

---
Input trait:
name: {raw.get('name', trait.get('name', ''))}
category: {raw.get('category', 'skill_like')}
description: |
  {raw.get('description', '')}

---
Output YAML with trait name as top-level key.
Include `kind`, `vars` (if any), `text`, and either `passive` or `battle` (not both)."""


def build_trait_batch_prompt(traits: list[tuple[str, dict]]) -> str:
    blocks = []
    for i, (name, trait) in enumerate(traits, 1):
        raw = trait.get("raw", trait)
        blocks.append(f"""\
Trait {i}:
  name: {raw.get('name', name)}
  category: {raw.get('category', 'skill_like')}
  description: |
    {raw.get('description', '')}""")

    joined = "\n\n".join(blocks)
    return f"""\
{TRAIT_SYSTEM_PROMPT}

---
Input ({len(traits)} traits):

{joined}

---
Output YAML: each trait name as top-level key.
Each must include `kind`, `vars` (if any), `text`, and either `passive` or `battle`.
Process ALL {len(traits)} traits above."""


# ---------------------------------------------------------------------------
# Hero Prompts
# ---------------------------------------------------------------------------

HERO_SYSTEM_PROMPT = """\
You are a translator for historical Japanese figure names from the game 信長之野望：真戰 (Nobunaga's Ambition: Shinsei).

Translate hero names, faction (勢力) names, and clan (家門) names from Japanese to Traditional Chinese (繁體中文).

Key rules:
- Many names share the same kanji between JP and CHT, but some JP-specific kanji need conversion:
  黒→黑, 関→關, 豊→豐, 浅→淺, 広→廣, 竜→龍, 辺→邊, 桜→櫻, 沢→澤, 県→縣, 斎→齋, 滝→瀧, 弐→貳, 鉄→鐵, 従→從, 帯→帶, 徳→德, 条→條, 団→團, 覚→覺, 伝→傳, 予→預, 亜→亞, 斉→齊
- Preserve names that are already identical in both languages
- These are real historical figures from Japan's Sengoku period
- CRITICAL: `faction` and `clan` are STRUCTURED VALUES, not free text.
  Translate ONLY the value the user gave you, character by character,
  using the kanji conversion table above. Do NOT infer the clan from
  the hero's surname. Do NOT substitute a different clan even if you
  think it would be more accurate. If the input clan is `豊臣`, the
  output MUST be `豐臣`, regardless of who the hero is. If the input
  clan is `北条`, the output MUST be `北條`. Treat clan/faction as
  opaque strings to transliterate, never to second-guess.

Output ONLY valid YAML. No markdown fences. No explanation.
Each JP name as a top-level key, with `name`, `faction`, and `clan` values."""


def build_hero_batch_prompt(heroes: list[tuple[str, str, str]]) -> str:
    blocks = [f"  {name}: {{faction: {faction}, clan: {clan}}}" for name, faction, clan in heroes]
    joined = "\n".join(blocks)
    return f"""\
{HERO_SYSTEM_PROMPT}

---
Input ({len(heroes)} heroes):
{joined}

---
Output YAML: each JP name as top-level key with `name`, `faction`, and `clan` in Traditional Chinese.
Remember: `faction` and `clan` are transliterated from the input value
character-by-character. Never replace them with the hero's surname.

Example (note that 黒田官兵衛's clan is 豊臣, NOT 黒田):
豊臣秀吉:
  name: 豐臣秀吉
  faction: 豐臣
  clan: 豐臣
黒田官兵衛:
  name: 黑田官兵衛
  faction: 豐臣
  clan: 豐臣
瑞渓院:
  name: 瑞溪院
  faction: 北條
  clan: 北條
Process ALL {len(heroes)} heroes above."""


# ---------------------------------------------------------------------------
# Parse & validate
# ---------------------------------------------------------------------------


def validate_skill_entry(data: dict) -> list[str]:
    """Validate a single skill's LLM output structure (new canonical format)."""
    errors = []
    if not isinstance(data, dict):
        return ["not a dict"]

    text = data.get("text")
    if not text:
        errors.append("missing text")
    elif not isinstance(text, dict):
        errors.append("text not a dict")
    else:
        if not text.get("name"):
            errors.append("text.name missing")
        if not text.get("description"):
            errors.append("text.description missing")

    bt = data.get("battle")
    if not bt:
        errors.append("missing battle")
    elif not isinstance(bt, dict):
        errors.append("battle not a dict")

    return errors


def validate_entry_quality(data: dict) -> list[str]:
    """Post-LLM quality checks on text section. Auto-fixes what it can, returns hard errors only."""
    text = data.get("text", {})
    if not isinstance(text, dict):
        return []

    # Auto-fix known issues first
    fixes = autofix_frontend(text)
    if fixes:
        tqdm.write(f"    [autofix] {'; '.join(fixes)}")

    errors = []
    desc = text.get("description", "")
    cmd_desc = text.get("commander_description", "")
    full_text = f"{desc} {cmd_desc}"
    # Vars are at entry level now, not inside text
    vars_dict = data.get("vars", {})

    import re as _re

    # 1. English words in CHT description (var names leaking through)
    english_words = _re.findall(r'(?<!\{var:)(?<!\{status:)(?<!\{scale:)(?<!\{dmg:)(?<!\{stat:)\b[a-zA-Z_]{3,}\b', full_text)
    ok_words = {'var', 'status', 'scale', 'dmg', 'stat', 'base', 'max', 'flat'}
    bad_words = [w for w in english_words if w.lower() not in ok_words]
    if bad_words:
        errors.append(f"English in description: {bad_words[:3]}")

    # 2. {var:X} references not in vars
    var_refs = _re.findall(r'\{var:(\w+)\}', full_text)
    for ref in var_refs:
        # Strip format spec (e.g. {var:key:%} → key)
        ref_key = ref.split(":")[0] if ":" in ref else ref
        if ref_key not in vars_dict:
            errors.append(f"{{var:{ref}}} not in vars")

    # 3. base without max
    for vk, vv in vars_dict.items():
        if isinstance(vv, dict) and 'base' in vv and 'max' not in vv:
            errors.append(f"vars.{vk} has base but no max")

    return errors


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------

def _load_existing_yaml(path: Path) -> dict:
    if path.exists():
        data = yaml.safe_load(path.read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    return {}


def _save_yaml(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _run_batches_parallel(
    batches: list,
    *,
    desc: str,
    parallel: int,
    process_fn,
) -> tuple[dict, list]:
    """Dispatch batches to a thread pool and collect results.

    parallel=1 still goes through ThreadPoolExecutor — single code path so
    behavior is identical between sequential and parallel modes (easier to
    debug). The progress bar advances as batches *finish* (as_completed),
    which matches user expectations of "X of N done". Order of completion
    is non-deterministic but the callers key results by name in a dict, so
    the final output is order-independent.

    process_fn: callable taking one batch and returning (results, failed).
    """
    all_results: dict = {}
    all_failed: list = []
    if not batches:
        return all_results, all_failed
    with ThreadPoolExecutor(max_workers=max(1, parallel)) as ex:
        futures = [ex.submit(process_fn, batch) for batch in batches]
        for fut in tqdm(as_completed(futures), total=len(futures),
                        desc=desc, unit="batch"):
            try:
                results, failed = fut.result()
            except Exception as e:
                # process_batch swallows its own exceptions, but if something
                # truly unexpected escapes we don't want one bad batch to kill
                # the whole run. Log loudly and continue.
                tqdm.write(f"  EXC in {desc} batch: {e}")
                continue
            all_results.update(results)
            all_failed.extend(failed)
    return all_results, all_failed


def process_batch(
    skills: list[tuple[str, dict]],
    model: str,
    force: bool,
    single_prompt_fn=None,
    batch_prompt_fn=None,
    cache_prefix: str = "skill",
) -> tuple[dict, list]:
    """Process a batch of items. Returns (results_dict, failed_list)."""
    if single_prompt_fn is None:
        single_prompt_fn = build_single_prompt
    if batch_prompt_fn is None:
        batch_prompt_fn = build_batch_prompt
    results = {}
    failed = []

    uncached = []
    for name, data in skills:
        if not force:
            cached = load_llm_cache(f"{cache_prefix}_{name}")
            if cached:
                results[name] = cached
                continue
        uncached.append((name, data))

    if not uncached:
        return results, failed

    if len(uncached) == 1:
        prompt = single_prompt_fn(uncached[0][1])
    else:
        prompt = batch_prompt_fn(uncached)

    try:
        timeout = 180  # 3 minutes per batch — covers Gemini latency spikes when running parallel
        raw = call_gemini(prompt, model=model, timeout=timeout)
        batch_label = "batch_" + "_".join(n for n, _ in uncached)
        save_raw_cache(batch_label, raw)

        parsed = parse_llm_output(raw)
        if parsed is None:
            # Batch parse failed → fallback to single
            if len(uncached) > 1:
                tqdm.write(f"  batch parse failed, falling back to single...")
                for name, data in uncached:
                    r, f = process_batch([(name, data)], model, force=True,
                                         single_prompt_fn=single_prompt_fn,
                                         batch_prompt_fn=batch_prompt_fn,
                                         cache_prefix=cache_prefix)
                    results.update(r)
                    failed.extend(f)
                return results, failed
            else:
                failed.append((uncached[0][0], "YAML parse failed"))
                tqdm.write(f"  PARSE FAIL: {uncached[0][0]}")
                return results, failed

        # For single skill, output might be nested under skill name or directly have text/battle
        if len(uncached) == 1:
            name = uncached[0][0]
            if "text" in parsed or "frontend" in parsed:
                # Direct output — normalize legacy "frontend" key
                entry = parsed
                if "frontend" in entry and "text" not in entry:
                    entry["text"] = entry.pop("frontend")
            elif name in parsed:
                entry = parsed[name]
                if "frontend" in entry and "text" not in entry:
                    entry["text"] = entry.pop("frontend")
            else:
                # Try first key
                first_key = next(iter(parsed), None)
                entry = parsed[first_key] if first_key else parsed
                if isinstance(entry, dict) and "frontend" in entry and "text" not in entry:
                    entry["text"] = entry.pop("frontend")

            errors = validate_skill_entry(entry)
            quality = validate_entry_quality(entry) if not errors else []
            all_issues = errors + quality
            if all_issues:
                failed.append((name, "; ".join(all_issues)))
                tqdm.write(f"  {'INVALID' if errors else 'QUALITY'}: {name} — {'; '.join(all_issues)}")
            else:
                save_llm_cache(f"{cache_prefix}_{name}", entry)
                results[name] = entry
        else:
            # Batch output: keys may be translated (CHT) instead of original JP names.
            # Match by position: LLM preserves input order.
            parsed_values = list(parsed.values())
            seen_names = set()
            for i, (name, _) in enumerate(uncached):
                # Try exact match first, then positional
                if name in parsed:
                    entry = parsed[name]
                elif i < len(parsed_values):
                    entry = parsed_values[i]
                else:
                    failed.append((name, "missing from batch output"))
                    tqdm.write(f"  MISSING: {name} not in batch output")
                    continue

                errors = validate_skill_entry(entry)
                if errors:
                    failed.append((name, "; ".join(errors)))
                    tqdm.write(f"  INVALID: {name} — {'; '.join(errors)}")
                    continue

                quality = validate_entry_quality(entry)
                if quality:
                    failed.append((name, "; ".join(quality)))
                    tqdm.write(f"  QUALITY: {name} — {'; '.join(quality)}")
                    continue

                # Normalize legacy "frontend" → "text"
                if "frontend" in entry and "text" not in entry:
                    entry["text"] = entry.pop("frontend")

                # Check for duplicate translated names within this batch
                fe_name = entry.get("text", {}).get("name", "")
                if fe_name and fe_name in seen_names:
                    failed.append((name, f"duplicate name '{fe_name}' in batch"))
                    tqdm.write(f"  DUPE: {name} → '{fe_name}' conflicts with another skill in batch")
                    continue
                if fe_name:
                    seen_names.add(fe_name)

                save_llm_cache(f"{cache_prefix}_{name}", entry)
                results[name] = entry

    except Exception as e:
        for name, _ in uncached:
            failed.append((name, str(e)))
        tqdm.write(f"  FAILED batch: {e}")

    return results, failed


def process_skills(
    *,
    limit: int | None = None,
    name_filter: str | None = None,
    force: bool = False,
    model: str = DEFAULT_MODEL,
    batch_size: int = DEFAULT_BATCH_SIZE,
    parallel: int = 1,
    preserve_vars: bool = False,
):
    # Read from canonical file; fall back to crawled for bootstrap
    canonical_path = Path(SKILLS_CANONICAL)
    if canonical_path.exists():
        canonical = yaml.safe_load(canonical_path.read_text("utf-8")) or {}
        targets = [(name, entry) for name, entry in canonical.items()]
    else:
        skills = yaml.safe_load(Path(SKILLS_CRAWLED).read_text("utf-8"))
        if not skills:
            print("[error] No skills found")
            sys.exit(1)
        targets = list(skills.items())

    if name_filter:
        targets = [(n, s) for n, s in targets if name_filter in n]
        tqdm.write(f"[filter] Matched {len(targets)} skills for '{name_filter}'")
    if limit:
        targets = targets[:limit]

    tqdm.write(f"[llm] Processing {len(targets)} skills with {model} (batch={batch_size}, parallel={parallel})")

    batches = [targets[i:i + batch_size] for i in range(0, len(targets), batch_size)]
    all_results, all_failed = _run_batches_parallel(
        batches,
        desc="translate",
        parallel=parallel,
        process_fn=lambda b: process_batch(b, model, force),
    )

    # Auto-retry failed items one-by-one (also parallelized)
    if all_failed:
        retry_names = {name for name, _ in all_failed}
        retry_targets = [(n, s) for n, s in targets if n in retry_names]
        tqdm.write(f"\n[retry] {len(retry_targets)} failed skills, retrying one-by-one...")
        retry_batches = [[item] for item in retry_targets]
        retry_results, all_failed = _run_batches_parallel(
            retry_batches,
            desc="retry",
            parallel=parallel,
            process_fn=lambda b: process_batch(b, model, force=True),
        )
        all_results.update(retry_results)

    # Merge results into canonical file
    if canonical_path.exists():
        canonical = yaml.safe_load(canonical_path.read_text("utf-8")) or {}
    else:
        canonical = {}

    updated = 0
    for name, data in all_results.items():
        entry = canonical.setdefault(name, {})
        if data.get("text"):
            entry["text"] = data["text"]
        if data.get("battle"):
            entry["battle"] = data["battle"]
        if data.get("vars") is not None:
            if preserve_vars and entry.get("vars"):
                # Keep existing vars, check for conflicts
                new_keys = set(data["vars"].keys())
                old_keys = set(entry["vars"].keys())
                if new_keys != old_keys:
                    tqdm.write(f"  [preserve-vars] {name}: LLM vars keys differ from existing "
                               f"(added: {new_keys - old_keys}, removed: {old_keys - new_keys}). "
                               f"Use --force-vars to accept LLM vars.")
                    all_failed.append((name, "vars key mismatch under --preserve-vars"))
                    continue
            else:
                entry["vars"] = data["vars"]
        updated += 1

    _save_yaml(canonical_path, canonical)

    # Also write legacy files for backward compat until build_frontend_data is switched
    frontend_skills = _load_existing_yaml(SKILLS_TRANSLATED)
    battle_skills = _load_existing_yaml(SKILLS_BATTLE)
    for name, data in all_results.items():
        if data.get("text"):
            fe = dict(data["text"])
            if data.get("vars"):
                fe["vars"] = data["vars"]
            frontend_skills[name] = fe
        if data.get("battle"):
            battle_skills[name] = data["battle"]
    _save_yaml(SKILLS_TRANSLATED, frontend_skills)
    _save_yaml(SKILLS_BATTLE, battle_skills)

    tqdm.write(f"\n[done] {len(canonical)} skills ({updated} updated) → {canonical_path}")
    if all_failed:
        tqdm.write(f"[warn] {len(all_failed)} failed:")
        for name, err in all_failed:
            tqdm.write(f"  {name}: {err}")
    _record_failures("skills", all_failed)

    return all_results


def process_traits(
    *,
    limit: int | None = None,
    name_filter: str | None = None,
    force: bool = False,
    model: str = DEFAULT_MODEL,
    batch_size: int = DEFAULT_BATCH_SIZE,
    parallel: int = 1,
    preserve_vars: bool = False,
):
    # Read from canonical file; fall back to crawled for bootstrap
    canonical_path = Path(TRAITS_CANONICAL)
    if canonical_path.exists():
        canonical = yaml.safe_load(canonical_path.read_text("utf-8")) or {}
        targets = [(name, entry) for name, entry in canonical.items()]
    else:
        traits = yaml.safe_load(Path(TRAITS_CRAWLED).read_text("utf-8"))
        if not traits:
            print("[error] No traits found")
            sys.exit(1)
        targets = list(traits.items())

    if name_filter:
        targets = [(n, t) for n, t in targets if name_filter in n]
        tqdm.write(f"[filter] Matched {len(targets)} traits for '{name_filter}'")
    if limit:
        targets = targets[:limit]

    tqdm.write(f"[llm] Processing {len(targets)} traits with {model} (batch={batch_size}, parallel={parallel})")

    batches = [targets[i:i + batch_size] for i in range(0, len(targets), batch_size)]
    all_results, all_failed = _run_batches_parallel(
        batches,
        desc="traits",
        parallel=parallel,
        process_fn=lambda b: process_batch(
            b, model, force,
            single_prompt_fn=build_trait_single_prompt,
            batch_prompt_fn=build_trait_batch_prompt,
            cache_prefix="trait",
        ),
    )

    # Auto-retry failed items one-by-one (also parallelized)
    if all_failed:
        retry_names = {name for name, _ in all_failed}
        retry_targets = [(n, t) for n, t in targets if n in retry_names]
        tqdm.write(f"\n[retry] {len(retry_targets)} failed traits, retrying one-by-one...")
        retry_batches = [[item] for item in retry_targets]
        retry_results, all_failed = _run_batches_parallel(
            retry_batches,
            desc="retry",
            parallel=parallel,
            process_fn=lambda b: process_batch(
                b, model, force=True,
                single_prompt_fn=build_trait_single_prompt,
                batch_prompt_fn=build_trait_batch_prompt,
                cache_prefix="trait",
            ),
        )
        all_results.update(retry_results)

    # Merge results into canonical file
    if canonical_path.exists():
        canonical = yaml.safe_load(canonical_path.read_text("utf-8")) or {}
    else:
        canonical = {}

    updated = 0
    for name, data in all_results.items():
        entry = canonical.setdefault(name, {})
        # Normalize legacy "frontend" → "text"
        if "frontend" in data and "text" not in data:
            data["text"] = data.pop("frontend")
        if data.get("text"):
            entry["text"] = data["text"]
        if data.get("kind"):
            entry["kind"] = data["kind"]
        if data.get("battle"):
            entry["battle"] = data["battle"]
        if data.get("passive"):
            entry["passive"] = data["passive"]
        if data.get("vars") is not None:
            if preserve_vars and entry.get("vars"):
                new_keys = set(data["vars"].keys())
                old_keys = set(entry["vars"].keys())
                if new_keys != old_keys:
                    tqdm.write(f"  [preserve-vars] {name}: vars keys differ "
                               f"(added: {new_keys - old_keys}, removed: {old_keys - new_keys}). "
                               f"Use --force-vars to accept.")
                    all_failed.append((name, "vars key mismatch under --preserve-vars"))
                    continue
            else:
                entry["vars"] = data["vars"]
        updated += 1

    _save_yaml(canonical_path, canonical)

    # Also write legacy files for backward compat until build_frontend_data is switched
    frontend_traits = _load_existing_yaml(TRAITS_TRANSLATED)
    battle_traits = _load_existing_yaml(TRAITS_BATTLE)
    for name, data in all_results.items():
        text = data.get("text") or data.get("frontend") or {}
        if text:
            fe = dict(text)
            if data.get("vars"):
                fe["vars"] = data["vars"]
            frontend_traits[name] = fe
        # Legacy battle format: flat troop fields, not nested PassiveBlock
        if data.get("battle"):
            battle_traits[name] = data["battle"]
        elif data.get("passive") and data["passive"].get("affinity"):
            aff = data["passive"]["affinity"]
            battle_traits[name] = {
                "type": "特性",
                "category": "troop_affinity",
                "troop_type": aff.get("troop_types", []),
                "level": aff.get("level", 0),
                "level_cap_bonus": aff.get("level_cap_bonus", 0),
            }

    _save_yaml(TRAITS_TRANSLATED, frontend_traits)
    _save_yaml(TRAITS_BATTLE, battle_traits)

    tqdm.write(f"\n[done] {len(canonical)} traits ({updated} updated) → {canonical_path}")
    if all_failed:
        tqdm.write(f"[warn] {len(all_failed)} failed:")
        for name, err in all_failed:
            tqdm.write(f"  {name}: {err}")
    _record_failures("traits", all_failed)

    return all_results


def process_hero_batch(
    heroes: list[tuple[str, str, str]],
    model: str,
    force: bool,
) -> tuple[dict, list]:
    """Process a batch of heroes. Returns (results_dict, failed_list)."""
    results = {}
    failed = []

    uncached = []
    for name, faction, clan in heroes:
        if not force:
            cached = load_llm_cache(f"hero_{name}")
            if cached:
                results[name] = cached
                continue
        uncached.append((name, faction, clan))

    if not uncached:
        return results, failed

    prompt = build_hero_batch_prompt(uncached)

    try:
        timeout = 180  # 3 minutes per batch — covers Gemini latency spikes when running parallel
        raw = call_gemini(prompt, model=model, timeout=timeout)
        batch_label = "batch_hero_" + "_".join(n for n, _, _ in uncached[:5])
        save_raw_cache(batch_label, raw)

        parsed = parse_llm_output(raw)
        if parsed is None:
            for name, _, _ in uncached:
                failed.append((name, "YAML parse failed"))
            tqdm.write(f"  PARSE FAIL: hero batch")
            return results, failed

        parsed_values = list(parsed.values())
        for i, (name, _, _) in enumerate(uncached):
            if name in parsed:
                entry = parsed[name]
            elif i < len(parsed_values):
                entry = parsed_values[i]
            else:
                failed.append((name, "missing from batch output"))
                tqdm.write(f"  MISSING: {name} not in batch output")
                continue

            if not isinstance(entry, dict) or not entry.get("name"):
                failed.append((name, "invalid: missing name field"))
                tqdm.write(f"  INVALID: {name} — missing name field")
                continue

            save_llm_cache(f"hero_{name}", entry)
            results[name] = entry

    except Exception as e:
        for name, _, _ in uncached:
            failed.append((name, str(e)))
        tqdm.write(f"  FAILED hero batch: {e}")

    return results, failed


def process_heroes(
    *,
    limit: int | None = None,
    name_filter: str | None = None,
    force: bool = False,
    model: str = DEFAULT_MODEL,
    batch_size: int = 25,
    parallel: int = 1,
):
    raw_data = yaml.safe_load(Path(HEROES_CRAWLED).read_text("utf-8"))
    if not raw_data:
        print("[error] No heroes found in", HEROES_CRAWLED)
        sys.exit(1)

    # Input is a list; extract unique (name, faction, clan) tuples
    seen = set()
    targets = []
    for hero in raw_data:
        name = hero.get("name", "")
        if not name or name in seen:
            continue
        seen.add(name)
        targets.append((name, hero.get("faction", ""), hero.get("clan", "")))

    if name_filter:
        targets = [(n, f, c) for n, f, c in targets if name_filter in n]
        tqdm.write(f"[filter] Matched {len(targets)} heroes for '{name_filter}'")
    if limit:
        targets = targets[:limit]

    tqdm.write(f"[llm] Processing {len(targets)} heroes with {model} (batch={batch_size}, parallel={parallel})")

    batches = [targets[i:i + batch_size] for i in range(0, len(targets), batch_size)]
    all_results, all_failed = _run_batches_parallel(
        batches,
        desc="heroes",
        parallel=parallel,
        process_fn=lambda b: process_hero_batch(b, model, force),
    )

    # Merge into output
    full_run = name_filter is None and limit is None
    hero_translated = {} if (force and full_run) else _load_existing_yaml(HEROES_TRANSLATED)

    new_count = 0
    for name, data in all_results.items():
        is_new = name not in hero_translated
        hero_translated[name] = data
        if is_new:
            new_count += 1

    _save_yaml(HEROES_TRANSLATED, hero_translated)

    updated = len(all_results) - new_count
    tqdm.write(f"\n[done] {len(hero_translated)} heroes ({new_count} new, {updated} updated) → {HEROES_TRANSLATED}")
    if all_failed:
        tqdm.write(f"[warn] {len(all_failed)} failed:")
        for name, err in all_failed:
            tqdm.write(f"  {name}: {err}")
    _record_failures("heroes", all_failed)

    return all_results


def claude_test(kind: str = "skills", num: int = 10, batch_size: int = 5, model: str = "haiku"):
    """Run prompts through Claude CLI for testing. No files saved."""
    import random

    if kind == "skills":
        data = yaml.safe_load(Path(SKILLS_CRAWLED).read_text("utf-8"))
        items = list(data.items())
        samples = random.sample(items, min(num, len(items)))
        batches = [samples[i:i + batch_size] for i in range(0, len(samples), batch_size)]
        for i, batch in enumerate(batches):
            prompt = build_batch_prompt(batch) if len(batch) > 1 else build_single_prompt(batch[0][1])
            names = ', '.join(n for n, _ in batch)
            print(f"\n{'='*60}")
            print(f"BATCH {i+1}/{len(batches)}: {names}")
            print(f"{'='*60}")
            try:
                raw = call_claude(prompt, model=model)
                parsed = parse_llm_output(raw)
                if parsed is None:
                    print(f"[PARSE FAIL] Raw:\n{raw[:500]}")
                    continue
                # Validate each skill
                for name, _ in batch:
                    entry = parsed.get(name)
                    if not entry:
                        # Try positional
                        vals = list(parsed.values())
                        idx = [n for n, _ in batch].index(name)
                        entry = vals[idx] if idx < len(vals) else None
                    if not entry:
                        print(f"  {name}: MISSING from output")
                        continue
                    errors = validate_skill_entry(entry)
                    quality = validate_entry_quality(entry) if not errors else []
                    if errors or quality:
                        print(f"  {name}: {'|'.join(errors + quality)}")
                    else:
                        fe = entry.get("frontend", {})
                        print(f"  {name} → {fe.get('name', '?')} | {fe.get('type', '?')} | brief: {fe.get('brief_description', '?')}")
                        print(f"    tags: {fe.get('tags', [])}")
                        desc = fe.get('description', '')
                        print(f"    desc: {desc[:80]}{'...' if len(desc) > 80 else ''}")
            except Exception as e:
                print(f"  [ERROR] {e}")
    elif kind == "traits":
        data = yaml.safe_load(Path(TRAITS_CRAWLED).read_text("utf-8"))
        items = list(data.items())
        samples = random.sample(items, min(num, len(items)))
        batches = [samples[i:i + batch_size] for i in range(0, len(samples), batch_size)]
        for i, batch in enumerate(batches):
            prompt = build_trait_batch_prompt(batch) if len(batch) > 1 else build_trait_single_prompt(batch[0][1])
            names = ', '.join(n for n, _ in batch)
            print(f"\n{'='*60}")
            print(f"BATCH {i+1}/{len(batches)}: {names}")
            print(f"{'='*60}")
            try:
                raw = call_claude(prompt, model=model)
                parsed = parse_llm_output(raw)
                if parsed is None:
                    print(f"[PARSE FAIL] Raw:\n{raw[:500]}")
                else:
                    for name, _ in batch:
                        entry = parsed.get(name)
                        if entry:
                            fe = entry.get("frontend", {})
                            print(f"  {name} → {fe.get('name', '?')}: {fe.get('description', '?')[:60]}")
                        else:
                            print(f"  {name}: MISSING")
            except Exception as e:
                print(f"  [ERROR] {e}")
    elif kind == "heroes":
        data = yaml.safe_load(Path(HEROES_CRAWLED).read_text("utf-8"))
        items = [(h["name"], h.get("faction", ""), h.get("clan", "")) for h in data if h.get("name")]
        samples = random.sample(items, min(num, len(items)))
        prompt = build_hero_batch_prompt(samples)
        print(f"\n{'='*60}")
        print(f"HEROES ({len(samples)} samples)")
        print(f"{'='*60}")
        try:
            raw = call_claude(prompt, model=model)
            parsed = parse_llm_output(raw)
            if parsed is None:
                print(f"[PARSE FAIL] Raw:\n{raw[:500]}")
            else:
                for name, _, _ in samples:
                    entry = parsed.get(name)
                    if entry:
                        print(f"  {name} → {entry.get('name', '?')} | {entry.get('faction', '?')}")
                    else:
                        print(f"  {name}: MISSING")
        except Exception as e:
            print(f"  [ERROR] {e}")

    print(f"\n[claude-test] Done. No files were modified.")


def main():
    p = argparse.ArgumentParser(description="LLM translate + extract skills, traits, and heroes")
    p.add_argument("--skills", action="store_true", help="Process skills only")
    p.add_argument("--traits", action="store_true", help="Process traits only")
    p.add_argument("--heroes", action="store_true", help="Process heroes only")
    p.add_argument("--limit", type=int, help="Max items to process")
    p.add_argument("--name", help="Filter by name (substring)")
    p.add_argument("--force", action="store_true", help="Ignore cache, overwrite output")
    p.add_argument("--model", default=DEFAULT_MODEL, help="Gemini model to use")
    p.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Items per LLM call")
    p.add_argument("--parallel", type=int, default=1, help="Number of batches to dispatch concurrently (default: 1, recommended max: 5)")
    p.add_argument("--preserve-vars", action="store_true", help="Keep existing vars; abort if LLM output has different keys")
    p.add_argument("--force-vars", action="store_true", help="Accept LLM vars even under --preserve-vars (override conflict)")
    p.add_argument("--claude-test", action="store_true", help="Print prompts for Claude Code testing (no LLM call, no file writes)")
    p.add_argument("--test-num", type=int, default=10, help="Number of random samples for --claude-test")
    args = p.parse_args()

    if args.claude_test:
        kind = "skills" if args.skills else "traits" if args.traits else "heroes" if args.heroes else "skills"
        claude_test(kind=kind, num=args.test_num, batch_size=args.batch_size, model=args.model)
        return

    # Default: all if none specified
    none_specified = not args.skills and not args.traits and not args.heroes
    do_skills = args.skills or none_specified
    do_traits = args.traits or none_specified
    do_heroes = args.heroes or none_specified

    pv = args.preserve_vars and not args.force_vars

    if do_skills:
        process_skills(
            limit=args.limit,
            name_filter=args.name,
            force=args.force,
            model=args.model,
            batch_size=args.batch_size,
            parallel=args.parallel,
            preserve_vars=pv,
        )
    if do_traits:
        process_traits(
            limit=args.limit,
            name_filter=args.name,
            force=args.force,
            model=args.model,
            batch_size=args.batch_size,
            parallel=args.parallel,
            preserve_vars=pv,
        )
    if do_heroes:
        process_heroes(
            limit=args.limit,
            name_filter=args.name,
            force=args.force,
            model=args.model,
            batch_size=args.batch_size,
            parallel=args.parallel,
        )

    _write_failure_manifest()


if __name__ == "__main__":
    main()
