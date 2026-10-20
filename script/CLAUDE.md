# Pipeline scripts

## Post-processing (build_frontend_data.py)

The `postprocess()` function runs after all merges and normalizes:
- `STATUS_ALIASES` — LLM status name aliases → canonical names
- `SCALE_ALIASES` — fixes `知略→智略`, English→Chinese stat names
- `SKILL_NAME_FIXES` — CHT skill name corrections
- `normalize_status_refs()` — fixes `{status:}` and `{scale:}` templates + plain text `知略→智略`
- `normalize_vars()` — fixes `vars.*.scale` aliases
- `ensure_str()` — ensures `activation_rate` is always a string
- Sort heroes by rarity desc, cost desc

## LLM Prompts

All prompts share `COMMON_RULES` from `llm_core.py` which enforces:
- Canonical status effect names
- Template syntax rules (`{var:}`, `{status:}`, `{scale:}`)
- Chinese stat names in `{scale:}`
- Status intensity percentages kept as plain text
- `activation_rate` as string format
- `brief_description` (15-25 char summary) and `tags` (from fixed `SKILL_TAGS` set)

### Prompt caching (OpenRouter / Anthropic)

- `llm_core.py` uses raw `httpx` (NOT OpenAI SDK) with per-block `cache_control` in the system message content array — the only method that actually works for prompt caching via OpenRouter
- Anthropic cache thresholds: Haiku 4096 tokens, Sonnet 2048 tokens. System prompts are sized to exceed these
- `_run_batches_parallel()` runs batch 1 alone to warm the cache, then dispatches the rest in parallel — avoids multiple cache writes
- `text.description` uses `{var:}` / `{status:}` / `{scale:}` template syntax; `battle` section uses `$key` for vars and plain Chinese for statuses/scaling — this distinction is a common LLM error source
- Trait validation uses `validate_trait_entry()` (not `validate_skill_entry()`) — passive traits have `passive` section, no `battle`
- See `ai-doc/openrouter-cache.md` for tested caching methods and what does NOT work
