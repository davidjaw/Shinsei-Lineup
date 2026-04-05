"""
Nobunaga Shinsen Hero Crawler - 2-Stage

Stage 1: Crawl hero list page → index file with basic info + detail URLs
Stage 2: Crawl each hero detail page → stats, traits, skill info

Outputs:
    data/heroes_crawled.yaml  — hero data (skills as name references only)
    data/skills_crawled.yaml  — skill details (type, rarity, target, rate, description)

Usage:
    python script/crawl_heroes.py [options]

Examples:
    python script/crawl_heroes.py                          # index only
    python script/crawl_heroes.py --detail                 # index + all detail pages
    python script/crawl_heroes.py --detail --limit 30      # first 30
    python script/crawl_heroes.py --detail --name 信長      # filter by name
    python script/crawl_heroes.py --refresh-index --detail  # re-fetch index, keep detail cache
    python script/crawl_heroes.py --force --detail          # ignore all cache
"""

import argparse
import json
import random
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
import yaml
from bs4 import BeautifulSoup
from tqdm import tqdm

from paths import (
    CRAWL_CACHE_DIR, HERO_INDEX_CACHE,
    HEROES_CRAWLED, SKILLS_CRAWLED, ASSEMBLY_CRAWLED,
)

DEFAULT_INDEX_URL = "https://game8.jp/nobunaga-shinsen/737773"
DEFAULT_TIMEOUT = 15

# JP skill type → normalized key
SKILL_TYPE_MAP = {
    "受動": "被動",
    "能動": "主動",
    "指揮": "指揮",
    "突撃": "突擊",
    "陣法": "陣法",
    "兵種": "兵種",
}


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------

def validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Invalid scheme: {parsed.scheme}")
    if "game8.jp" not in parsed.netloc:
        raise ValueError(f"Unexpected host: {parsed.netloc}, expected game8.jp")
    if "nobunaga-shinsen" not in parsed.path:
        raise ValueError(f"Path missing 'nobunaga-shinsen': {parsed.path}")
    return url


def fetch_page(url: str, timeout: float = DEFAULT_TIMEOUT) -> BeautifulSoup:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ja,zh-TW;q=0.9,zh;q=0.8,en;q=0.7",
    }
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def crawl_delay():
    time.sleep(random.random() * 0.5 + 0.5)


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def _detail_cache_path(url: str) -> Path:
    slug = urlparse(url).path.strip("/").replace("/", "_")
    return CRAWL_CACHE_DIR / f"{slug}.json"


def load_detail_cache(url: str) -> dict | None:
    path = _detail_cache_path(url)
    if path.exists():
        return json.loads(path.read_text("utf-8"))
    return None


def save_detail_cache(url: str, data: dict):
    CRAWL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _detail_cache_path(url)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


def load_index() -> list[dict] | None:
    if HERO_INDEX_CACHE.exists():
        return json.loads(HERO_INDEX_CACHE.read_text("utf-8"))
    return None


def save_index(heroes: list[dict]):
    CRAWL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    HERO_INDEX_CACHE.write_text(json.dumps(heroes, ensure_ascii=False, indent=2), "utf-8")


# ---------------------------------------------------------------------------
# Stage 1: List page → index
# ---------------------------------------------------------------------------

def extract_hero_list(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """Extract heroes from list page.

    Page has two table formats:
      - 13-td rows: structured cells at td[8]-td[12] for stars/cost/faction/clan/gender
      - 9-td rows: same data in td[4]-td[8] with class='hidden'
    Both have td[0]=name+portrait, td[1]=bracket fields with 【コスト】.
    We parse bracket text as the reliable source for all fields.
    """
    heroes = []

    for td in soup.find_all("td"):
        if "【コスト】" not in td.get_text():
            continue
        row = td.parent
        if not row or row.name != "tr":
            continue
        cells = row.find_all("td")
        if len(cells) < 4:
            continue

        link = cells[0].find("a", href=re.compile(r"/nobunaga-shinsen/\d+"))
        name = cells[0].get_text(strip=True)
        if not link or not name:
            continue

        detail_url = urljoin(base_url, link["href"])

        portrait_img = cells[0].find("img", attrs={"data-src": True})
        portrait = portrait_img["data-src"] if portrait_img else None

        # Parse all fields from bracket text (works for both table formats)
        bracket_text = td.get_text(separator=" ")
        fields = _parse_bracket_fields(bracket_text)
        skill_names = _parse_bracket_skills(bracket_text)

        # Star count from any cell containing ★
        rarity = 0
        for cell in cells:
            stars = cell.get_text(strip=True).count("★")
            if stars > 0:
                rarity = stars
                break

        heroes.append({
            "name": name,
            "detail_url": detail_url,
            "portrait": portrait,
            "rarity": rarity or fields.get("rarity", 0),
            "cost": fields.get("cost", 0),
            "faction": fields.get("faction", ""),
            "clan": fields.get("clan", ""),
            "gender": fields.get("gender", ""),
            **skill_names,
        })

    return heroes


def _parse_bracket_fields(text: str) -> dict:
    """Parse structured fields from bracket-delimited text."""
    data = {}
    cost_m = re.search(r"【コスト】\s*(\d+)", text)
    if cost_m:
        data["cost"] = int(cost_m.group(1))
    gender_m = re.search(r"【性別】\s*(男|女)", text)
    if gender_m:
        data["gender"] = gender_m.group(1)
    faction_m = re.search(r"【勢力】\s*(.+?)(?=\s*【|$)", text)
    if faction_m:
        data["faction"] = faction_m.group(1).strip()
    clan_m = re.search(r"【家門】\s*(.+?)(?=\s*【|$)", text)
    if clan_m:
        data["clan"] = clan_m.group(1).strip()
    return data


def _parse_bracket_skills(text: str) -> dict:
    data = {}
    patterns = {
        "unique_skill":    r"【固有戦法】\s*(.+?)(?=\s*【|$)",
        "teachable_skill": r"【伝授戦法】\s*(.+?)(?=\s*【|$)",
        "assembly_skill":  r"【評定衆技能】\s*(.+?)(?=\s*【|$)",
    }
    for key, pat in patterns.items():
        m = re.search(pat, text)
        if m:
            val = m.group(1).strip()
            data[key] = None if val == "なし" else val
    return data


# ---------------------------------------------------------------------------
# Stage 2: Detail page
# ---------------------------------------------------------------------------

STAT_MAP = {
    "武勇": "val", "知略": "int", "統率": "lea",
    "速度": "spd", "政務": "pol", "魅力": "cha",
}


def extract_hero_detail(soup: BeautifulSoup, hero_name: str) -> dict:
    """Returns hero detail dict. Skills stored under 'skills' as raw dicts
    (will be split into hero ref + skill file later)."""
    detail = {}
    text = soup.get_text(separator="\n")

    stats = {}
    for jp, key in STAT_MAP.items():
        m = re.search(rf"{jp}\s*[:：]?\s*(\d+)", text)
        if m:
            stats[key] = int(m.group(1))
    if stats:
        detail["stats"] = stats

    traits = _extract_traits(soup)
    if traits:
        detail["traits"] = traits

    skills = _extract_skill_details(soup, hero_name)
    if skills:
        detail["_raw_skills"] = skills
        # Override list-page skill names with detail-page names (more accurate)
        for sk in skills:
            if sk.get("is_unique"):
                detail["unique_skill"] = sk["name"]
            if sk.get("is_teachable"):
                detail["teachable_skill"] = sk["name"]

    return detail


def _extract_traits(soup: BeautifulSoup) -> list[dict]:
    traits = []
    for th in soup.find_all("th"):
        if th.get_text(strip=True) != "特性":
            continue
        table = th.find_parent("table")
        if not table:
            continue

        in_traits = False
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            text = row.get_text(strip=True)
            if len(cells) == 1 and text == "特性":
                in_traits = True
                continue
            if in_traits and len(cells) == 1:
                break
            if in_traits and len(cells) == 2:
                name = cells[0].get_text(strip=True)
                desc = cells[1].get_text(strip=True)
                if name and desc:
                    traits.append({"name": name, "description": desc})
        break
    return traits


def _parse_skill_description(desc: str, hero_name: str) -> dict:
    """Parse the bracket-delimited skill description into structured fields."""
    info: dict = {}

    # Type: first keyword after 【戦法詳細】
    type_m = re.search(r"【戦法詳細】\s*(受動|能動|指揮|突撃|陣法|兵種)", desc)
    if type_m:
        info["type"] = SKILL_TYPE_MAP.get(type_m.group(1), type_m.group(1))

    # Target
    target_m = re.search(r"【対象種別】(.+?)【", desc)
    if target_m:
        info["target"] = target_m.group(1).strip()

    # Activation rate
    rate_m = re.search(r"【発動確率】(.+?)【", desc)
    if rate_m:
        info["activation_rate"] = rate_m.group(1).strip()

    # Aptitude (often empty on game8)
    apt_m = re.search(r"【適性兵種】([^【]*?)【", desc)
    if apt_m:
        apt = apt_m.group(1).strip()
        if apt:
            info["aptitude"] = apt

    # Full description text after 【戦法詳細】<type>
    detail_m = re.search(
        r"【戦法詳細】\s*(?:受動|能動|指揮|突撃|陣法|兵種)\s*(.+?)(?:【戦法種類】|$)",
        desc, re.DOTALL,
    )
    if detail_m:
        info["description"] = detail_m.group(1).strip()

    # Commander skill (大将技)
    commander_m = re.search(r"大将技\s*[：:]\s*(.+?)(?:\n|【|$)", desc)
    if commander_m:
        info["commander_bonus"] = commander_m.group(1).strip()

    info["source_hero"] = hero_name

    return info


def _extract_skill_details(soup: BeautifulSoup, hero_name: str) -> list[dict]:
    """Extract skills from h3 headings. Returns list of skill dicts with parsed fields."""
    skills = []
    for section_label in ["固有戦法", "伝授戦法"]:
        h3 = soup.find("h3", string=re.compile(rf"^{section_label}$"))
        if not h3:
            continue
        table = h3.find_next_sibling("table")
        if not table:
            continue
        rows = table.find_all("tr")
        if not rows:
            continue

        first_cells = rows[0].find_all(["td", "th"])
        raw_rarity = first_cells[0].get_text(strip=True) if len(first_cells) > 0 else ""
        rarity = raw_rarity.replace("戦法", "").replace("戰法", "").strip()  # "S戦法" → "S"
        name = first_cells[1].get_text(strip=True) if len(first_cells) > 1 else ""

        desc_parts = []
        for row in rows[1:]:
            t = row.get_text(strip=True)
            if t:
                desc_parts.append(t)
        raw_desc = "\n".join(desc_parts)

        skill = {"name": name, "rarity": rarity, **_parse_skill_description(raw_desc, hero_name)}

        # Mark if this skill is the hero's unique (fixed) skill or teachable
        if section_label == "固有戦法":
            skill["is_unique"] = True
        else:
            skill["is_teachable"] = True

        skills.append(skill)
    return skills


# ---------------------------------------------------------------------------
# Output: split hero YAML + skill YAML
# ---------------------------------------------------------------------------

def save_outputs(heroes: list[dict], heroes_path: str, skills_path: str, assembly_path: str):
    """Split crawled data into:
    - heroes YAML (skill refs only)
    - skills YAML (battle skills: 固有戦法 + 伝授戦法)
    - assembly skills YAML (評定衆技能 — non-battle / domestic skills)
    """
    skills_db: dict[str, dict] = {}
    assembly_db: dict[str, dict] = {}
    hero_list = []

    for h in heroes:
        raw_skills = h.pop("_raw_skills", [])

        for sk in raw_skills:
            sk_name = sk["name"]
            if sk_name and sk_name not in skills_db:
                skills_db[sk_name] = sk
            elif sk_name in skills_db:
                if sk.get("is_unique"):
                    skills_db[sk_name]["is_unique"] = True
                if sk.get("is_teachable"):
                    skills_db[sk_name]["is_teachable"] = True

        # Collect assembly skill names (detail comes from future crawler)
        asm_name = h.get("assembly_skill")
        if asm_name and asm_name not in assembly_db:
            assembly_db[asm_name] = {
                "name": asm_name,
                "source_heroes": [h["name"]],
            }
        elif asm_name and asm_name in assembly_db:
            assembly_db[asm_name]["source_heroes"].append(h["name"])

        hero_out = {
            "name": h["name"],
            "rarity": h.get("rarity"),
            "cost": h.get("cost"),
            "faction": h.get("faction"),
            "clan": h.get("clan"),
            "gender": h.get("gender"),
            "detail_url": h.get("detail_url"),
            "portrait": h.get("portrait"),
        }
        if h.get("stats"):
            hero_out["stats"] = h["stats"]
        if h.get("traits"):
            hero_out["traits"] = h["traits"]

        hero_out["unique_skill"] = h.get("unique_skill")
        hero_out["teachable_skill"] = h.get("teachable_skill")
        hero_out["assembly_skill"] = asm_name

        hero_list.append(hero_out)

    for path, data in [(heroes_path, hero_list), (skills_path, skills_db), (assembly_path, assembly_db)]:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    return hero_list, skills_db, assembly_db


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def crawl(
    *,
    index_url: str = DEFAULT_INDEX_URL,
    do_detail: bool = False,
    limit: int | None = None,
    name_filter: str | None = None,
    refresh_index: bool = False,
    force: bool = False,
    timeout: float = DEFAULT_TIMEOUT,
    heroes_path: str = str(HEROES_CRAWLED),
    skills_path: str = str(SKILLS_CRAWLED),
    assembly_path: str = str(ASSEMBLY_CRAWLED),
):
    index_url = validate_url(index_url)

    # --- Stage 1: Index ---
    use_cached_index = not force and not refresh_index
    heroes = load_index() if use_cached_index else None

    if heroes:
        tqdm.write(f"[index] Loaded {len(heroes)} heroes from {HERO_INDEX_CACHE}")
    else:
        tqdm.write(f"[index] Fetching hero list: {index_url}")
        soup = fetch_page(index_url, timeout=timeout)
        heroes = extract_hero_list(soup, index_url)
        tqdm.write(f"[index] Found {len(heroes)} heroes")
        if heroes:
            save_index(heroes)
            tqdm.write(f"[index] Saved → {HERO_INDEX_CACHE}")

    if not heroes:
        tqdm.write("[error] No heroes found. Page structure may have changed.")
        sys.exit(1)

    # --- Filter ---
    targets = heroes
    if name_filter:
        targets = [h for h in heroes if name_filter in h.get("name", "")]
        tqdm.write(f"[filter] Matched {len(targets)} heroes for '{name_filter}'")
    if limit:
        targets = targets[:limit]

    for h in targets[:5]:
        tqdm.write(f"  {h['name']}  cost={h.get('cost')}  faction={h.get('faction')}")
    if len(targets) > 5:
        tqdm.write(f"  ... and {len(targets) - 5} more")

    # --- Stage 2: Detail pages ---
    if do_detail:
        skipped = 0
        failed = []

        for hero in tqdm(targets, desc="detail", unit="hero"):
            url = hero.get("detail_url")
            if not url:
                continue

            if not force:
                cached = load_detail_cache(url)
                if cached:
                    hero.update(cached)
                    skipped += 1
                    continue

            try:
                detail_soup = fetch_page(url, timeout=timeout)
                detail = extract_hero_detail(detail_soup, hero["name"])
                hero.update(detail)
                save_detail_cache(url, detail)
            except Exception as e:
                failed.append((hero["name"], str(e)))
                tqdm.write(f"  FAILED: {hero['name']} — {e}")

            crawl_delay()

        if skipped:
            tqdm.write(f"[detail] {skipped} from cache, {len(targets) - skipped} fetched")
        if failed:
            tqdm.write(f"[warn] {len(failed)} failed — re-run to retry (cache preserved)")

    # --- Save ---
    hero_list, skills_db, assembly_db = save_outputs(heroes, heroes_path, skills_path, assembly_path)
    tqdm.write(f"\n[done] {len(hero_list)} heroes → {heroes_path}")
    tqdm.write(f"[done] {len(skills_db)} skills → {skills_path}")
    tqdm.write(f"[done] {len(assembly_db)} assembly skills → {assembly_path}")

    return hero_list, skills_db, assembly_db


def main():
    p = argparse.ArgumentParser(description="Crawl hero data from game8.jp")
    p.add_argument("--url", default=DEFAULT_INDEX_URL, help="Hero list page URL")
    p.add_argument("--heroes-out", default=str(HEROES_CRAWLED), help="Heroes YAML output path")
    p.add_argument("--skills-out", default=str(SKILLS_CRAWLED), help="Skills YAML output path")
    p.add_argument("--assembly-out", default=str(ASSEMBLY_CRAWLED), help="Assembly skills YAML output path")
    p.add_argument("--detail", action="store_true", help="Enable stage 2 (crawl detail pages)")
    p.add_argument("--limit", type=int, help="Max heroes to crawl detail for")
    p.add_argument("--name", help="Filter heroes by name (substring match)")
    p.add_argument("--refresh-index", action="store_true", help="Re-fetch index page (keep detail cache)")
    p.add_argument("--force", action="store_true", help="Ignore all cache")
    p.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="Request timeout in seconds")
    args = p.parse_args()

    crawl(
        index_url=args.url,
        do_detail=args.detail,
        limit=args.limit,
        name_filter=args.name,
        refresh_index=args.refresh_index,
        force=args.force,
        timeout=args.timeout,
        heroes_path=args.heroes_out,
        skills_path=args.skills_out,
        assembly_path=args.assembly_out,
    )


if __name__ == "__main__":
    main()
