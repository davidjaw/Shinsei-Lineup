# Nobunaga Lineup Builder

## Project Overview

A data pipeline + SPA for **信長之野望：真戰** (Nobunaga's Ambition: Shinsei). Crawls game data from game8.jp, translates JP→CHT via Gemini LLM, and serves a Vue 3 lineup builder.

## Architecture

```
game8.jp → crawl_heroes.py → llm_translate.py → build_frontend_data.py → Vite SPA
                                                  ↑ overrides.yaml (manual additions)
```

### Pipeline Scripts (in `script/`)

| Script | Purpose | Run |
|--------|---------|-----|
| `crawl_heroes.py` | Crawl game8.jp for heroes/skills/traits | `python3 script/crawl_heroes.py --detail` |
| `llm_translate.py` | Batch translate JP→CHT via Gemini CLI | `python3 script/llm_translate.py --batch-size 5` |
| `llm_core.py` | Shared LLM infra (prompts, Gemini CLI, cache, parsing) | Imported by other scripts |
| `build_frontend_data.py` | Merge crawled+translated+overrides → JSON | `python3 script/build_frontend_data.py` |
| `check_data_integrity.py` | Validate output JSON references | `python3 script/check_data_integrity.py` |
| `override.py` | Interactive CLI for manual skill/hero additions | `python3 script/override.py` |
| `extract_data.py` | **DEPRECATED** — old crawler, kept for reference only |

### Data Flow

- **Source of truth**: `data/heroes_crawled.yaml`, `data/skills_crawled.yaml`, `data/traits_crawled.yaml`
- **LLM output**: `data/skills_translated.yaml`, `data/traits_translated.yaml`, `data/heroes_translated.yaml`
- **Manual overrides**: `data/overrides.yaml` (committed to git, highest priority)
- **Static definitions**: `data/statuses.yaml` (hand-maintained canonical status effects)
- **Build output**: `.build/heroes.json`, `.build/skills.json`, `.build/statuses.json` (gitignored)

### Frontend (Vue 3 + Element Plus + TailwindCSS)

- Single-file SPA via `vite-plugin-singlefile` — all data inlined into `dist/index.html`
- Key composables: `useData.ts` (data loading), `useTemplateParser.ts` (template rendering), `useLineups.ts`, `useInventory.ts`
- Template syntax in descriptions: `{var:name}`, `{status:name}`, `{scale:stat}`, `{dmg:type}`, `{stat:key}`

## Key Commands

```bash
npm run dev          # Build data + start dev server
npm run build        # Build data + production build
npm run data         # Build data only (build_frontend_data + check_data_integrity)

# Pipeline
python3 script/crawl_heroes.py --detail                    # Full crawl
python3 script/llm_translate.py --batch-size 5             # Translate all (skills+traits+heroes)
python3 script/llm_translate.py --skills --force            # Re-translate skills only
python3 script/llm_translate.py --heroes                    # Translate hero names only
python3 script/override.py                                  # Interactive override CLI
python3 script/build_frontend_data.py                       # Build frontend JSON
```

## Post-processing (build_frontend_data.py)

The `postprocess()` function runs after all merges and normalizes:
- `STATUS_ALIASES` — LLM status name aliases → canonical names
- `SCALE_ALIASES` — fixes `知略→智略`, English→Chinese stat names
- `SKILL_NAME_FIXES` — CHT skill name corrections
- `normalize_status_refs()` — fixes `{status:}` and `{scale:}` templates + plain text `知略→智略`
- `normalize_vars()` — fixes `vars.*.scale` aliases
- `ensure_str()` — ensures `activation_rate` is always a string
- Sort heroes by rarity desc, cost desc

## Override System

`data/overrides.yaml` supports:
- `_action: add` — add new skill/hero
- `_action: modify` (default) — deep merge fields into existing entry
- `_action: delete` — remove entry

Applied as last step in `build_frontend_data.py`, highest priority.

## LLM Prompts

All prompts share `COMMON_RULES` from `llm_core.py` which enforces:
- Canonical status effect names
- Template syntax rules (`{var:}`, `{status:}`, `{scale:}`)
- Chinese stat names in `{scale:}`
- Status intensity percentages kept as plain text
- `activation_rate` as string format
- `brief_description` (15-25 char summary) and `tags` (from fixed `SKILL_TAGS` set)

## Environment

- Python 3.10+ with `pyyaml`, `beautifulsoup4`, `requests`, `tqdm`, `python-dotenv`
- Node 20+ with Vue 3, Element Plus, TailwindCSS
- Gemini CLI (`gemini`) for LLM calls — requires `GOOGLE_CLOUD_PROJECT` in `.env`

## Conventions

- All game text in Traditional Chinese (繁體中文)
- Code and comments in English
- Hero names: JP in `name_jp`, CHT in `name`
- Skill names: JP key in YAML, CHT `name` field in translated data
- Data files in `data/` are gitignored except `overrides.yaml` and `statuses.yaml`
