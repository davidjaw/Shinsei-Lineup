"""
Shared LLM infrastructure for Gemini CLI calls.

Provides: constants, prompt rules, call_gemini(), parse_llm_output(), cache functions.
"""

import os
import re
import subprocess
import yaml
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GCP_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "")
DEFAULT_MODEL = "gemini-3-flash-preview"
CACHE_DIR = Path("data/.llm_cache")

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
    "兵刃傷害 計略傷害 真實傷害 "
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
IMPORTANT — Status Effect Names:
When referencing status effects in {status:name}, you MUST use ONLY these canonical names:
""" + CANONICAL_STATUSES + """
Do NOT use synonyms or aliases (e.g., use 挑釁 not 嘲諷, use 威壓 not 震懾, use 混亂 not 恐慌, use 封擊 not 繳械, use 奇謀 not 奇策).

Skill type MUST be exactly one of: 被動, 主動, 指揮, 突擊, 兵種, 陣法
Do NOT append 戰法 (e.g., use 被動 not 被動戰法).

Template syntax rules:
- In `description`, replace numeric values that scale with level with variable refs: {var:variable_name}
  - Example: "10%→20%の会心" → "{var:crit_rate}的會心"
  - Variable names MUST match keys in `vars`
  - EXCEPTION: Status effect intensity percentages (e.g., "30%麻痺", "90%封擊") describe how often the status actually takes effect once applied. These are distinct from the probability of applying the status.
    Keep these percentages as plain text if they don't scale with level.
    Example: "施加30%{status:麻痺}狀態" — the 30% is the status intensity, keep as-is.
    Only use {var:} if the percentage changes between lv1 and lv10.
- In `vars`, each variable must specify its unit type:
  - Percentages/ratios (傷害率, 機率, 會心率, etc.): store as raw decimal (0.1 for 10%), do NOT add `type` (percent is default).
    Example: damage_rate: {base: 0.58, max: 1.16}
  - Absolute values (點數, stat points like 武勇+60, 統率-18, etc.): store the actual number AND add `type: flat`.
    Example: valor_buff: {base: 60, max: 120, type: flat}
  - Counts/turns/stacks (回合, 次數, 層數, 人數): store as plain integer, do NOT add `type`.
    Example: duration: 2, max_stacks: 3, target_count: 2
  - Fixed values (no level scaling): just a number (or number with type: flat if it's stat points).
- Stat dependency: add `scale: stat_name` in the var (use Chinese: 武勇, 智略, 統率, 速度, 魅力, 政務)
- In description, use {scale:stat} which renders as "受stat影響". So write "（{scale:智略}）" NOT "（受{scale:智略}影響）"
- ONLY use {status:name} when explicitly referencing a canonical status effect (麻痺, 混亂, etc.). Do NOT convert verbs like 治療/恢復 into {status:休養}.
- `activation_rate` must be a string: "35%" or "35%→90%" format. NOT a number.

Output ONLY valid YAML. No markdown fences. No explanation."""


# ---------------------------------------------------------------------------
# Gemini CLI
# ---------------------------------------------------------------------------

def call_gemini(prompt: str, model: str = DEFAULT_MODEL, timeout: int = 180) -> str:
    env = {**os.environ, "GOOGLE_CLOUD_PROJECT": GCP_PROJECT} if GCP_PROJECT else None
    result = subprocess.run(
        ["gemini", "-m", model, "-p", prompt, "-o", "text"],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gemini-cli failed: {result.stderr[:300]}")
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# YAML parsing
# ---------------------------------------------------------------------------

def _clean_strings(obj):
    if isinstance(obj, str):
        lines = [line.rstrip() for line in obj.split("\n")]
        while lines and not lines[-1]:
            lines.pop()
        return "\n".join(lines)
    if isinstance(obj, dict):
        return {k: _clean_strings(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean_strings(v) for v in obj]
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
        return _clean_strings(data)
    except yaml.YAMLError:
        # Try parsing frontend sections only (battle often has unquoted colons)
        try:
            parts = re.split(r"\nbattle:\s*\n", text, maxsplit=1)
            fe_data = yaml.safe_load(parts[0])
            result = _clean_strings(fe_data) if fe_data else {}
            if len(parts) > 1:
                try:
                    bt_data = yaml.safe_load("battle:\n" + parts[1])
                    if bt_data:
                        result.update(_clean_strings(bt_data))
                except yaml.YAMLError:
                    pass
            return result if result else None
        except yaml.YAMLError:
            return None


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def load_llm_cache(key: str, cache_dir: Path = CACHE_DIR) -> dict | None:
    path = cache_dir / f"{key}.yaml"
    if path.exists():
        try:
            return yaml.safe_load(path.read_text("utf-8"))
        except yaml.YAMLError:
            return None
    return None


def save_llm_cache(key: str, data: dict, cache_dir: Path = CACHE_DIR):
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{key}.yaml"
    path.write_text(
        yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
        "utf-8",
    )


def save_raw_cache(label: str, raw_text: str, cache_dir: Path = CACHE_DIR):
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{label}.raw.txt"
    path.write_text(raw_text, "utf-8")
