"""
Centralized file path constants for the data pipeline.

All scripts import paths from here instead of defining their own.
"""

from pathlib import Path

DATA_DIR = Path("data")
BUILD_DIR = Path(".build")
CRAWL_CACHE_DIR = DATA_DIR / ".crawl_cache"
LLM_CACHE_DIR = DATA_DIR / ".llm_cache"

# New layout (refactor): game8 outputs collected under data/game8/, cfg under
# data/cfg/, prototype merge artifacts under data/prototype/. Old *_CRAWLED
# constants below remain as the canonical paths for one migration cycle.
GAME8_DIR = DATA_DIR / "game8"
CFG_DIR = DATA_DIR / "cfg"
CFG_HISTORY_DIR = DATA_DIR / ".cfg_history"
PROTOTYPE_DIR = DATA_DIR / "prototype"

CFG_CURRENT_JSON = CFG_DIR / "cfg_current.json"
CFG_LAST_DIFF_SUMMARY = CFG_DIR / "last_diff_summary.txt"
CFG_DIFF_REPORT = BUILD_DIR / "cfg_diff_report.md"

# Manual files for the three-layer override system.
CFG_ALIASES_PATH = DATA_DIR / "cfg_aliases.yaml"
SOURCE_CORRECTIONS_PATH = DATA_DIR / "source_corrections.yaml"
KEY_NORMALIZATION_PATH = DATA_DIR / "key_normalization.yaml"

# Crawl outputs
HEROES_CRAWLED = DATA_DIR / "heroes_crawled.yaml"
SKILLS_CRAWLED = DATA_DIR / "skills_crawled.yaml"
TRAITS_CRAWLED = DATA_DIR / "traits_crawled.yaml"
ASSEMBLY_CRAWLED = DATA_DIR / "assembly_skills_crawled.yaml"
BINGXUE_CRAWLED = DATA_DIR / "bingxue_crawled.yaml"

# Staging crawl (crawl --staging → diff_crawl → review_server → merge_crawl).
# Isolated from live data: own output dir + own page cache. merge_crawl clears
# both on success so the next update cycle starts from fresh pages.
STAGING_DIR = DATA_DIR / "staging"
STAGING_CACHE_DIR = DATA_DIR / ".crawl_cache_staging"
STAGING_HEROES = STAGING_DIR / "heroes_crawled.yaml"
STAGING_SKILLS = STAGING_DIR / "skills_crawled.yaml"
STAGING_ASSEMBLY = STAGING_DIR / "assembly_skills_crawled.yaml"
STAGING_BINGXUE = STAGING_DIR / "bingxue_crawled.yaml"
CRAWL_DIFF_JSON = BUILD_DIR / "crawl_diff.json"

# LLM outputs
HEROES_TRANSLATED = DATA_DIR / "heroes_translated.yaml"

# Canonical (unified files — raw + vars + text + battle/passive per entry)
SKILLS_CANONICAL = DATA_DIR / "skills.yaml"
TRAITS_CANONICAL = DATA_DIR / "traits.yaml"
BINGXUE_CANONICAL = DATA_DIR / "bingxue.yaml"

# Static / manual
STATUSES_YAML = DATA_DIR / "statuses.yaml"
OVERRIDES_YAML = DATA_DIR / "overrides.yaml"

# Build outputs
HEROES_JSON = BUILD_DIR / "heroes.json"
SKILLS_JSON = BUILD_DIR / "skills.json"
STATUSES_JSON = BUILD_DIR / "statuses.json"
BINGXUE_JSON = BUILD_DIR / "bingxue.json"
TRANSLATION_FAILURES_JSON = BUILD_DIR / "translation_failures.json"

# ---------------------------------------------------------------------------
# Bingxue (兵學) direction mapping — shared constant, NOT a path.
# The CHT localization swaps 臨戦 ↔ 機略 relative to the JP source. This is
# the single source of truth used by populate_bingxue_names.py (to fill yaml)
# and build_frontend_data.py (to re-key heroes' bingxue for the frontend).
# ---------------------------------------------------------------------------
BINGXUE_JP_TO_CHT_DIR = {
    "武略": "武略",
    "陣立": "陣立",
    "臨戦": "機略",
    "機略": "臨戰",
}
