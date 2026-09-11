# Supabase cheat sheet

Two hosted projects. CLI `link` is global for this repo — check `.temp/linked-project.json` before `db push`.

| | Project ref | Env file | Vite |
|---|---|---|---|
| **dev** | `pptoljoymqbflmucyxzo` | `.env.dev` | `npm run dev:supabase-dev` |
| **prod** | `ebmamfpeffgkmhpyoyul` | `.env` | `npx vite` / `npm run build` |

## CLI

```bash
# Which project is linked?
grep '"name\|"ref' supabase/.temp/linked-project.json

npm run db:link:dev    # pptoljoymqbflmucyxzo
npm run db:link:prod   # ebmamfpeffgkmhpyoyul

# Push pending migrations only. Do NOT use `npm run db:push`
# (that also overwrites supabase/schema.sql).
npx supabase db push --yes

# Edge functions are not included in db push. Deploy after link.
# `verify_jwt = false` in supabase/config.toml is required: gateway JWT
# would 401 the browser OPTIONS preflight and GitHub Pages would see CORS.
npx supabase functions deploy handbook-snapshot --no-verify-jwt
```

GRANT/REVOKE in migrations: never quote `"boolean"` (Postgres type name is `bool`). Use unquoted `boolean` / `text` / `uuid` / `jsonb`.

## SQL Editor

Run in the **same** project you intend to change (dev vs prod). Dashboard → SQL Editor.

### Set admin

Merges into existing `raw_app_meta_data` so OAuth `provider` / `providers` are kept. User must **sign out and sign in** afterwards (JWT).

```sql
UPDATE auth.users
SET raw_app_meta_data = raw_app_meta_data || '{"role": "admin"}'::jsonb
WHERE email = 'you@example.com';

SELECT email, raw_app_meta_data
FROM auth.users
WHERE email = 'you@example.com';
```

### List admins

```sql
SELECT email, id, raw_app_meta_data
FROM auth.users
WHERE raw_app_meta_data->>'role' = 'admin'
ORDER BY email;
```

Remove admin:

```sql
UPDATE auth.users
SET raw_app_meta_data = raw_app_meta_data - 'role'
WHERE email = 'you@example.com';
```

### List banned users

```sql
SELECT
  u.email,
  b.user_id,
  b.banned_at,
  b.reason,
  banner.email AS banned_by_email
FROM public.user_bans b
JOIN auth.users u ON u.id = b.user_id
LEFT JOIN auth.users banner ON banner.id = b.banned_by
ORDER BY b.banned_at DESC;
```

### Unban

```sql
DELETE FROM public.user_bans
WHERE user_id = (
  SELECT id FROM auth.users WHERE email = 'them@example.com'
);
```

Or from a featured-team card: 管理 → 解除封鎖 (admin JWT required).

### Ban from SQL (optional)

Prefer the in-app 封鎖此作者. SQL equivalent (replace both emails):

```sql
INSERT INTO public.user_bans (user_id, banned_by, reason)
VALUES (
  (SELECT id FROM auth.users WHERE email = 'them@example.com'),
  (SELECT id FROM auth.users WHERE email = 'you@example.com'),
  NULL
)
ON CONFLICT (user_id) DO UPDATE
  SET banned_at = now(),
      banned_by = EXCLUDED.banned_by;
```

Cannot self-ban via the RPC; SQL has no such guard — do not ban your own admin account.

## What admin / ban actually do

- **Admin** (`app_metadata.role = admin`): 管理 on 精選卡片 — spoiler hide, permanent lock (`••••`), ban/unban 原作.
- **Ban** (`public.user_bans`): blocked from `submit_variant` and from creating/flipping a proposal **public**. Private proposals, private share URLs, votes, withdraw, public→private still work. Existing public variants are not auto-removed.
