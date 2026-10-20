# Nobunaga Lineup Builder

## Project Overview

A data pipeline + single-file SPA for **信長之野望：真戰** (Nobunaga's Ambition: Shinsei). It merges the game8.jp
crawl with the official Sialia cfg, translates JP → CHT through an LLM, and serves a Vue 3 lineup builder with
inventory profiles, team groups, shares, a variant feed and a gacha log.

Current build (2026-10-18): **161 heroes, 263 skills, 48 status effects, 60 兵學 options**. Data is Traditional
Chinese; code, comments and documentation are English.

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
- **Build output**: `.build/heroes.json`, `skills.json`, `statuses.json`, `bingxue.json`
  (gitignored); `dist/index.html` is the single-file bundle.
- **Translation failure manifest**: `.build/translation_failures.json` — `ok` flag, per-kind summary and
  copy/paste `suggested_actions`.

## Key Commands

```bash
npm install
uv sync

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

# Translation (kinds: skills, traits, heroes, bingxue)
uv run script/llm_translate.py --batch-size 10 --parallel 3
uv run script/llm_translate.py --skills --force
uv run script/llm_translate.py --heroes
uv run script/llm_translate.py --bingxue --limit 10

# Manual data edits
uv run script/override.py                 # interactive override CLI
uv run script/apply_bingxue_override.py paste.txt   # 兵學 table → overrides.yaml
```

### LLM backend

`llm_translate.py` and `override.py` default to the **OMP backend** (`@smol`; requires `omp` on `PATH`, or
`OMP_BIN`). Use `--backend openrouter` (or just `--model vendor/name`) for OpenRouter; the OpenRouter default is
`anthropic/claude-haiku-4.5`. Other useful flags: `--provider`, `--preserve-vars`, `--force-vars`.

## Override System

`data/overrides.yaml` supports:

- `_action: add` — add an entry; `_replaces: <JP name>` folds an old entry (legacy `_replaces` lists are
  normalized).
- `_action: modify` (default) — deep-merge fields into the existing entry.
- `_action: replace` — drop the existing entry and write the override wholesale.
- `_action: delete` — remove the entry.

Skill overrides may set `is_event_skill: true`; the frontend renders an "事件戰法" label. Applied as the last step
in `build_frontend_data.py`.

### Hero 兵學 (bingxue) overrides

When the user pastes a hero's 兵學 table (often messy OCR/AI text): normalize it → run
`apply_bingxue_override.py` → on conflict/`ERROR`, ask before `--force`. Details:
[doc/bingxue-override.md](doc/bingxue-override.md).

## Frontend

Vue 3 + Element Plus + TailwindCSS + Vite, hash router, built as one self-contained `dist/index.html`.
Description template syntax: `{var:name}`, `{status:name}`, `{scale:stat}`, `{dmg:type}`, `{stat:key}`.

Views:

- `/` **編隊** — lineup builder (inventory / free modes), drag-and-drop skill assignment, 兵學, team conflict checks.
- `/profiles` **角色管理** — named inventory profiles (hero + skill ownership).
- `/groups` **我的編組** — up to 10 teams per group, with cross-team uniqueness.
- `/shares` **我的分享** — named/pinned share links.
- `/proposals` **精選隊伍** — public variant feed, voting, fork/import.
- `/gacha-log` **抽卡紀錄** — per-banner draw log, pity progress and share snapshots.
- `/settings` **設定** — language, appearance, account.

Supabase is optional and feature-detected (`isSupabaseConfigured()`). Without it, local editing still works and
cloud sync/short shares/proposals/gacha are silently disabled. The client uses direct `fetch` + PostgREST/GoTrue
(no `supabase-js`). A handbook snapshot proxy runs as the `handbook-snapshot` edge function.

## Environment

- `.env`: `OPENROUTER_API_KEY` (required for the OpenRouter backend), optional `ANTHROPIC_API_KEY`,
  optional `VITE_SUPABASE_URL` + `VITE_SUPABASE_PUBLISHABLE_KEY`.
- Supabase projects: dev `pptoljoymqbflmucyxzo`, prod `ebmamfpeffgkmhpyoyul`. Link, push, admin/ban SQL:
  [doc/supabase.md](doc/supabase.md).

## Conventions

- All game text in Traditional Chinese (繁體中文); code and comments in English.
- Hero names: JP in `name_jp`, CHT in `name`. Skill names: JP key in YAML, CHT `name` in translated data.
- `data/` is gitignored except `overrides.yaml`, `statuses.yaml`, `source_corrections.yaml`, the cfg archive and
  `cfg/last_diff_summary.txt`.
- Never hand-edit `.build/` or `dist/`; regenerate them.
- Changelog (`src/constants/changelog.ts`): released versions are frozen — never append entries to them. After a
  release, start the next unreleased batch by adding 1 to the patch (`0.4.8` → `0.4.9`). Fold all subsequent
  unreleased work into that one unshipped version. Do not bump per session, per feature, or per commit; do not jump
  minor (`0.5.0`) unless asked.
