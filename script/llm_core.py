"""
Shared LLM infrastructure for OpenRouter API calls.

Provides: constants, prompt rules, call_llm(), parse_llm_output(), cache functions.
"""

import os
import re
import yaml
from pathlib import Path

import httpx
from dotenv import load_dotenv

from paths import LLM_CACHE_DIR, OVERRIDES_YAML

load_dotenv()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODEL_FREE = "google/gemma-4-31b-it:free"
MODEL_GEMMA = "google/gemma-4-26b-a4b-it"
MODEL_HAIKU = "anthropic/claude-haiku-4.5"
MODEL_SONNET = "anthropic/claude-sonnet-4.6"
DEFAULT_MODEL = MODEL_HAIKU

CANONICAL_STATUSES = (
    "威壓 麻痺 封擊 無策 混亂 疲弊 "
    "閃避 抵禦 必中 先攻 "
    "連擊 破陣 亂舞 "
    "會心 奇謀 "
    "離反 攻心 "
    "休養 禁療 "
    "火傷 水攻 中毒 潰走 消沉 "
    "洞察 免疫 "
    "援護 挑釁 牽制"
)

SKILL_TAGS = (
    "兵刃傷害 謀略傷害 真實傷害 "
    "單體傷害 群體傷害 多段傷害 "
    "治療 增益 減益 控制 "
    "提升屬性 降低屬性 "
    "施加狀態 移除狀態 免疫狀態 "
    "被動觸發 主動發動 指揮效果 突擊觸發 "
    "條件觸發 回合觸發 "
    "武勇系 智略系 統率系 速度系 魅力系 "
    "大將技"
)

COMMON_RULES = """\
Translation style: 翻譯時，以三國志戰略版遊戲的技能描述口吻進行，用語簡潔精準，符合策略遊戲玩家的閱讀習慣。

### JP→CHT Kanji Conversions (apply to ALL output fields):
知略→智略, 撃→擊, 竜→龍, 発→發, 効→效, 覚→覺, 戦→戰, 総→總, 関→關, 豊→豐, 県→縣, 鉄→鐵, 条→條

### Canonical Lists

Status effects — use ONLY these names in {status:name}:
""" + CANONICAL_STATUSES + """
Do NOT use synonyms (挑釁 not 嘲諷, 威壓 not 震懾, 混亂 not 恐慌, 封擊 not 繳械, 奇謀 not 奇策).

Skill type — MUST be exactly one of: 被動, 主動, 指揮, 突擊, 兵種, 陣法 (never append 戰法)

Stat names for {scale:}: 武勇, 智略, 統率, 速度, 魅力, 政務

Damage type terminology: 兵刃傷害, 謀略傷害, 真實傷害 (NEVER use 計略傷害, always use 謀略傷害)

### Template Syntax

#### Naming
- Each skill's CHT `name` MUST be unique — never translate two different skills to the same name.
- If the JP name is already valid CHT (e.g., 火計), keep it as-is.

#### {var:name} — Numeric variables
- Decision rule: create a {var:} ONLY if the JP source shows the value changing across levels (→ notation, two values). Single fixed values = plain number.
- Variable names: snake_case, English only. E.g., damage_rate, ally_count, stat_debuff.
- NEVER put modifiers inside braces: write {var:name}% NOT {var:name:%}
- vars format:
  - Scaling values (differ lv1↔lv10): MUST have BOTH `base` AND `max`.
    - Ratios: raw decimal, no `type`. E.g., damage_rate: {base: 0.58, max: 1.16}
    - Stat points: actual number + `type: flat`. E.g., valor_buff: {base: 60, max: 120, type: flat}
  - Fixed values (same at all levels): plain number, NO base/max. E.g., duration: 2

#### {scale:stat} — Damage/effect scaling indicator
- Frontend renders this as "受stat影響" — NEVER write 受{scale:X}影響 (doubles the wrapper)
- Use ONLY when JP source indicates dependency (影響, 依存). Always wrap in parentheses: （{scale:智略}）
- NEVER use for direct stat references: "統率降低" is plain text, NOT {scale:統率}降低

#### {status:name} — Status effect references
- ONLY for canonical status effects listed above.
- 治療/恢復 are verbs, NOT {status:休養}

#### Plain-text numbers (do NOT varify)
- Status intensity: "30%麻痺" → "30%{status:麻痺}" (the 30% stays as plain text)
- Fixed thresholds: "兵力50%以下" → plain text
- Fixed target counts with no scaling: "敵軍2体" → "敵軍2人" (plain text)

#### activation_rate
- Must be a string: "35%" or "35%→90%". NOT a number.

### COMMON MISTAKES — DO NOT DO THESE:
| Wrong | Right | Why |
| {var:name:%} | {var:name}% | Modifier outside braces |
| {var:rate}% (ratio var) | {var:rate} (no %) | Ratio vars auto-render as %. Adding % doubles it |
| 受{scale:智略}影響 | （{scale:智略}） | Frontend adds 受...影響 |
| {scale:統率}降低6% | 統率降低{var:penalty} | {scale:} is for scaling only |
| {status:休養} for 治療 | 治療 (plain text) | 休養 is a status, not a verb |
| {base: 0.52, max: 0.52} | 0.52 | Same value = fixed |
| {base: 1.34} (no max) | {base: 0.67, max: 1.34} | Scaling vars need both |
| activation_rate: 0.35 | activation_rate: "35%" | Must be string with % |
| type: 被動戰法 | type: 被動 | Never append 戰法 |
| 知略 | 智略 | JP kanji → CHT |
| 計略傷害 | 謀略傷害 | Correct damage type term |

### Target Field JP→CHT Conventions
- 敵軍単体 → 敵軍單體
- 敵軍複数（N体）→ 敵軍複數（N人）
- 敵軍全体 → 敵軍全體
- 自軍単体 → 自軍單體
- 自軍複数（N体）→ 自軍群體（N人）
- 自軍全体 → 自軍全體
- 自身 → 自身

### Duration Conventions
- 「Nターンの間」→ N回合
- 「戦闘中」→ 戰鬥中（entire battle, no duration var needed）
- 「毎ターン」→ 每回合

Output ONLY valid YAML. No markdown fences. No explanation."""


# ---------------------------------------------------------------------------
# OpenRouter client (raw httpx + per-block cache_control)
# ---------------------------------------------------------------------------

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_http_client: httpx.Client | None = None


def _get_client() -> httpx.Client:
    global _http_client
    if _http_client is None:
        api_key = os.getenv("OPENROUTER_API_KEY", "")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY not set in .env")
        _http_client = httpx.Client(
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(180.0, connect=10.0),
        )
    return _http_client


def call_llm(
    prompt: str,
    *,
    system_prompt: str | None = None,
    model: str = DEFAULT_MODEL,
    timeout: int = 180,
    max_tokens: int = 16000,
    provider: str | None = None,
) -> str:
    """Call LLM via OpenRouter with per-block prompt caching for Anthropic models."""
    client = _get_client()
    is_anthropic = "anthropic/" in model

    messages: list[dict] = []
    if system_prompt:
        if is_anthropic:
            # Per-block cache_control in content array — the only method that works
            messages.append({
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
            })
            if not provider:
                provider = "Anthropic"
        else:
            messages.append({"role": "system", "content": system_prompt})

    messages.append({"role": "user", "content": prompt})

    payload: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    if provider:
        payload["provider"] = {"order": [provider], "allow_fallbacks": True}

    resp = client.post(
        _OPENROUTER_URL,
        json=payload,
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()

    # Track token usage
    usage = data.get("usage", {})
    if usage:
        _token_totals["prompt"] += usage.get("prompt_tokens", 0)
        _token_totals["completion"] += usage.get("completion_tokens", 0)
        _token_totals["calls"] += 1
        details = usage.get("prompt_tokens_details", {})
        cached = details.get("cached_tokens", 0)
        if cached:
            _token_totals["cached"] += cached
            from tqdm import tqdm
            tqdm.write(f"    [cache] {cached} tokens read from cache")

    return data["choices"][0]["message"]["content"].strip()


# Token usage accumulator
_token_totals: dict[str, int] = {"prompt": 0, "completion": 0, "cached": 0, "calls": 0}


def reset_token_totals():
    for k in _token_totals:
        _token_totals[k] = 0


def get_token_totals() -> dict[str, int]:
    return dict(_token_totals)


# ---------------------------------------------------------------------------
# YAML parsing
# ---------------------------------------------------------------------------

def clean_strings(obj):
    if isinstance(obj, str):
        lines = [line.rstrip() for line in obj.split("\n")]
        while lines and not lines[-1]:
            lines.pop()
        return "\n".join(lines)
    if isinstance(obj, dict):
        return {k: clean_strings(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_strings(v) for v in obj]
    return obj


def parse_llm_output(raw: str) -> dict | None:
    text = raw.strip()
    # Strip markdown fences
    if text.startswith("```"):
        lines = text.split("\n")
        start = 1
        end = len(lines)
        for i in range(len(lines) - 1, 0, -1):
            if lines[i].strip().startswith("```"):
                end = i
                break
        text = "\n".join(lines[start:end])

    try:
        data = yaml.safe_load(text)
        return clean_strings(data)
    except yaml.YAMLError:
        # Try parsing frontend sections only (battle often has unquoted colons)
        try:
            parts = re.split(r"\nbattle:\s*\n", text, maxsplit=1)
            fe_data = yaml.safe_load(parts[0])
            result = clean_strings(fe_data) if fe_data else {}
            if len(parts) > 1:
                try:
                    bt_data = yaml.safe_load("battle:\n" + parts[1])
                    if bt_data:
                        result.update(clean_strings(bt_data))
                except yaml.YAMLError:
                    pass
            return result if result else None
        except yaml.YAMLError:
            return None


# ---------------------------------------------------------------------------
# Auto-fix known LLM output issues
# ---------------------------------------------------------------------------

def autofix_frontend(fe: dict) -> list[str]:
    """Auto-fix known LLM issues in a frontend dict. Returns list of fixes applied."""
    fixes = []
    vars_dict = fe.get("vars", {})

    # Fix 1: {var:name}% where var is ratio → remove trailing %
    for field in ("description", "commander_description"):
        text = fe.get(field, "")
        if not text:
            continue
        for vk, vv in vars_dict.items():
            if isinstance(vv, dict) and "base" in vv and vv.get("type") != "flat":
                pattern = rf"\{{var:{vk}\}}%"
                if re.search(pattern, text):
                    fe[field] = re.sub(pattern, f"{{var:{vk}}}", text)
                    text = fe[field]
                    fixes.append(f"removed trailing % after {{var:{vk}}}")

    # Fix 2: {var:name:%} → {var:name}%
    for field in ("description", "commander_description"):
        text = fe.get(field, "")
        if text and ":%}" in text:
            fe[field] = re.sub(r"\{var:(\w+):%\}", r"{var:\1}%", text)
            fixes.append("fixed {var:name:%} → {var:name}%")

    # Fix 3: base == max → plain number
    for vk, vv in list(vars_dict.items()):
        if isinstance(vv, dict) and "base" in vv and "max" in vv and vv["base"] == vv["max"]:
            val = vv["base"]
            vars_dict[vk] = val
            fixes.append(f"vars.{vk} base==max → {val}")

    # Fix 4: 受{scale:X}影響 → {scale:X}
    for field in ("description", "commander_description"):
        text = fe.get(field, "")
        if text and "受{scale:" in text:
            fe[field] = re.sub(r"受\{scale:([^}]+)\}影響", r"{scale:\1}", text)
            fixes.append("fixed 受{scale:X}影響 → {scale:X}")

    # Fix 5: {{var:X}} → {var:X}, {{status:X}} → {status:X}, etc.
    for field in ("description", "commander_description"):
        text = fe.get(field, "")
        if text and "{{" in text:
            new_text = re.sub(r"\{\{(var|status|scale|dmg|stat):([^}]+)\}\}", r"{\1:\2}", text)
            if new_text != text:
                fe[field] = new_text
                fixes.append("fixed double braces {{X}} → {X}")

    return fixes


# Hiragana + Katakana detection. Excludes ・(U+30FB) which is shared CJK punctuation.
_KANA_RE = re.compile(r"[\u3040-\u309F\u30A0-\u30FA\u30FC-\u30FF]")


def has_kana(value) -> bool:
    """Return True if string contains Japanese kana (hiragana/katakana)."""
    return isinstance(value, str) and bool(_KANA_RE.search(value))


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def load_llm_cache(key: str, cache_dir: Path = LLM_CACHE_DIR) -> dict | None:
    path = cache_dir / f"{key}.yaml"
    if not path.exists():
        return None
    try:
        data = yaml.safe_load(path.read_text("utf-8"))
    except yaml.YAMLError:
        return None
    # Reject empty/non-dict cache entries so a corrupted file gets re-translated
    # instead of silently returning a broken result.
    if not isinstance(data, dict) or not data:
        return None
    return data


def save_llm_cache(key: str, data: dict, cache_dir: Path = LLM_CACHE_DIR):
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{key}.yaml"
    path.write_text(
        yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
        "utf-8",
    )


def save_raw_cache(label: str, raw_text: str, cache_dir: Path = LLM_CACHE_DIR):
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{label}.raw.txt"
    path.write_text(raw_text, "utf-8")


# ---------------------------------------------------------------------------
# Overrides
# ---------------------------------------------------------------------------

def load_overrides() -> dict:
    """Load overrides.yaml if it exists. Returns dict with clean strings."""
    if not OVERRIDES_YAML.exists():
        return {}
    data = yaml.safe_load(OVERRIDES_YAML.read_text("utf-8"))
    return clean_strings(data) if isinstance(data, dict) else {}
