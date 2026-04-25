"""
Centralized file path constants for the data pipeline.

All scripts import paths from here instead of defining their own.
"""

from pathlib import Path

DATA_DIR = Path("data")
BUILD_DIR = Path(".build")
CRAWL_CACHE_DIR = DATA_DIR / ".crawl_cache"
LLM_CACHE_DIR = DATA_DIR / ".llm_cache"

# Crawl outputs
HEROES_CRAWLED = DATA_DIR / "heroes_crawled.yaml"
SKILLS_CRAWLED = DATA_DIR / "skills_crawled.yaml"
TRAITS_CRAWLED = DATA_DIR / "traits_crawled.yaml"
ASSEMBLY_CRAWLED = DATA_DIR / "assembly_skills_crawled.yaml"
BINGXUE_CRAWLED = DATA_DIR / "bingxue_crawled.yaml"

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

# Crawl cache
HERO_INDEX_CACHE = CRAWL_CACHE_DIR / "_hero_index.json"

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
