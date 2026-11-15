# Nobunaga Lineup Builder

## Project Overview

A data pipeline + single-file SPA for **信長之野望：真戰** (Nobunaga's Ambition: Shinsei). It merges the game8.jp
crawl with the official Sialia cfg, translates JP → CHT through an LLM, and serves a Vue 3 lineup builder with
inventory profiles, team groups, shares, a variant feed and a gacha log.

Data is Traditional Chinese; code, comments and documentation are English.

## Data Flow

```
game8.jp crawl ─┐
                 ├─ merge_sources.py → data/prototype/*_proto.yaml
Sialia cfg.json ─┘                              │
                                                ├─ LLM translate / reconcile
                                                ↓
                          data/skills.yaml, traits.yaml, bingxue.yaml, heroes_translated.yaml
                                                │
                    data/overrides.yaml ────────┤ (highest priority, applied last)
                    data/statuses.yaml ─────────┤
                                                ↓
                          build_frontend_data.py → .build/{heroes,skills,statuses,bingxue}.json
                                                ↓
                                   Vite + vite-plugin-singlefile → dist/index.html
```

- **Source of truth (crawled)**: `data/heroes_crawled.yaml`, `skills_crawled.yaml`,
  `traits_crawled.yaml`, `assembly_skills_crawled.yaml`, `bingxue_crawled.yaml`.
- **Official config**: `data/cfg/cfg_current.json` (versioned archive in `data/.cfg_history/`).
- **Deterministic merge**: `data/prototype/*_proto.yaml`, using the tracked match file
  `data/source_corrections.yaml` (upstream corrections + cfg/trait-key alias maps).
- **Canonical output**: `data/skills.yaml`, `data/traits.yaml`, `data/bingxue.yaml`,
  `data/heroes_translated.yaml` (gitignored).
- **Manual overrides**: `data/overrides.yaml` (tracked, applied last, highest priority) and
  `data/statuses.yaml` (tracked, hand-maintained status effects).
- **Game seasons**: `data/game_seasons.json` (tracked, hand-maintained): the season (S1 S2 S3 PK) of every hero by
  `name_jp` and of the skills with no hero of their own; the app imports it directly, outside `npm run data`.
  `src/lib/gameSeason.test.ts` fails when the catalog gains a hero or event skill the table lacks.
- **Build output**: `.build/heroes.json`, `skills.json`, `statuses.json`, `bingxue.json`
  (gitignored); `dist/index.html` is the single-file bundle.
- **Translation failure manifest**: `.build/translation_failures.json` — `ok` flag, per-kind summary and
  copy/paste `suggested_actions`.

## Key Commands

```bash
# Refresh inputs and build
npm run refresh          # game8 crawl + cfg fetch + cfg diff (refresh_sources.py)
npm run refresh:cfg      # cfg only (--skip-crawl)
npm run data             # merge_sources + build + check_build + check_coverage + check_cfg_drift
npm run dev              # data + Vite dev server (`d` in the terminal rebuilds data)
npm run build            # data + production single-file build → dist/index.html

# Crawl review flow (staged updates)
uv run script/crawl_heroes.py --detail --staging
uv run script/review_server.py            # http://127.0.0.1:8765
uv run script/merge_crawl.py decisions.json
```

Translation, override edits and pasted 兵學 tables: see the `data-edits` skill.

## Frontend

Built as one self-contained `dist/index.html` (hash router).
Description template syntax: `{var:name}`, `{status:name}`, `{scale:stat}`, `{dmg:type}`, `{stat:key}`.

Supabase is optional and feature-detected (`isSupabaseConfigured()`). Without it, local editing still works and
cloud sync/short shares/proposals/gacha are silently disabled. The client uses direct `fetch` + PostgREST/GoTrue
(no `supabase-js`). A handbook snapshot proxy runs as the `handbook-snapshot` edge function (deployed from outside this repo).

## Environment

- `.env`: `OPENROUTER_API_KEY` (required for the OpenRouter backend),
  optional `VITE_SUPABASE_URL` + `VITE_SUPABASE_PUBLISHABLE_KEY`.
- Supabase projects: dev `pptoljoymqbflmucyxzo`, prod `ebmamfpeffgkmhpyoyul`. This repo is only a client of them:
  migrations, edge functions and DB operations are not kept or deployed from here.

## Conventions

- All game text in Traditional Chinese (繁體中文); code and comments in English.
- Hero names: JP in `name_jp`, CHT in `name`. Skill names: JP key in YAML, CHT `name` in translated data.
- `data/` is gitignored except `overrides.yaml`, `statuses.yaml`, `source_corrections.yaml`, `game_seasons.json`,
  the cfg archive and `cfg/last_diff_summary.txt`.
- Never hand-edit `.build/` or `dist/`; regenerate them.
- Changelog (`src/constants/changelog.ts`): released versions are frozen — never append entries to them. After a
  release, start the next unreleased batch by adding 1 to the patch (`0.4.8` → `0.4.9`). Fold all subsequent
  unreleased work into that one unshipped version. Do not bump per session, per feature, or per commit; do not jump
  minor (`0.5.0`) unless asked.
