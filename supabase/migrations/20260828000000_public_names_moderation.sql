-- Public team-name + display-name moderation.
--
-- Public 精選隊伍 cards need a typed 隊伍名稱, but submit_variant historically
-- only stored author_name on variant_contributors. This migration:
--
--   1. Stores a per-contributor team_name (capped at 50) without putting a
--      title column on team_variants — the displayed title is resolved
--      client-side from contributors (first-author first, skip hidden).
--   2. Adds hide flags for team_name (per contributor row) and author_name
--      (per user, via display_name_hides, fanned out to contributor rows).
--   3. Adds content_reports + report_content so 3 unique reports auto-hide
--      unless an admin has already set the hide source.
--   4. Recreates submit_variant with p_team_name; hash/upsert path is unchanged.
--
-- compute_variant_hashes is not modified. team_variants schema is not modified.


-- 1. Contributor columns -----------------------------------------------------

ALTER TABLE "public"."variant_contributors"
    ADD COLUMN IF NOT EXISTS "team_name" text,
    ADD COLUMN IF NOT EXISTS "team_name_hidden" boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS "team_name_hide_source" text,
    ADD COLUMN IF NOT EXISTS "author_name_hidden" boolean NOT NULL DEFAULT false;

-- Existing contributor snapshots were stored uncapped (proposal backfill) or
-- capped at 10 (old submit_variant). Truncate before the new length CHECK.
UPDATE "public"."variant_contributors"
   SET "author_name" = left(btrim("author_name"), 30)
 WHERE "author_name" IS NOT NULL
   AND char_length("author_name") > 30;

ALTER TABLE "public"."variant_contributors"
    DROP CONSTRAINT IF EXISTS "variant_contributors_team_name_len",
    DROP CONSTRAINT IF EXISTS "variant_contributors_author_name_len",
    DROP CONSTRAINT IF EXISTS "variant_contributors_team_name_hide_source";

ALTER TABLE "public"."variant_contributors"
    ADD CONSTRAINT "variant_contributors_team_name_len"
        CHECK ("team_name" IS NULL OR char_length("team_name") <= 50),
    ADD CONSTRAINT "variant_contributors_author_name_len"
        CHECK ("author_name" IS NULL OR char_length("author_name") <= 30),
    ADD CONSTRAINT "variant_contributors_team_name_hide_source"
        CHECK ("team_name_hide_source" IS NULL
               OR "team_name_hide_source" IN ('auto', 'admin'));


-- 2. Per-user display-name hide (admin or auto). Writes via SECURITY DEFINER
--    RPCs only — no SELECT/INSERT policies for anon/authenticated.

CREATE TABLE IF NOT EXISTS "public"."display_name_hides" (
    "user_id"    uuid        PRIMARY KEY REFERENCES "auth"."users"("id") ON DELETE CASCADE,
    "hidden"     boolean     NOT NULL,
    "source"     text        NOT NULL CHECK ("source" IN ('auto', 'admin')),
    "updated_at" timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE "public"."display_name_hides" OWNER TO "postgres";
ALTER TABLE "public"."display_name_hides" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE "public"."display_name_hides" FROM PUBLIC;
REVOKE ALL ON TABLE "public"."display_name_hides" FROM "anon";
REVOKE ALL ON TABLE "public"."display_name_hides" FROM "authenticated";
GRANT ALL ON TABLE "public"."display_name_hides" TO "service_role";


-- 3. Content reports. target_key is the de-dupe / count key, set by RPC:
--      team_name:    'team_name:' || variant_id::text || ':' || target_user_id::text
--      display_name: 'display_name:' || target_user_id::text

CREATE TABLE IF NOT EXISTS "public"."content_reports" (
    "id"             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    "reporter_id"    uuid        NOT NULL DEFAULT auth.uid() REFERENCES "auth"."users"("id") ON DELETE CASCADE,
    "kind"           text        NOT NULL CHECK ("kind" IN ('team_name', 'display_name')),
    "variant_id"     uuid        REFERENCES "public"."team_variants"("id") ON DELETE CASCADE,
    "target_user_id" uuid        NOT NULL REFERENCES "auth"."users"("id") ON DELETE CASCADE,
    "target_key"     text        NOT NULL,
    "created_at"     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT "content_reports_kind_shape" CHECK (
        ("kind" = 'team_name' AND "variant_id" IS NOT NULL)
        OR ("kind" = 'display_name' AND "variant_id" IS NULL)
    ),
    CONSTRAINT "content_reports_not_self" CHECK ("reporter_id" <> "target_user_id"),
    CONSTRAINT "content_reports_reporter_target_key" UNIQUE ("reporter_id", "target_key")
);

ALTER TABLE "public"."content_reports" OWNER TO "postgres";
ALTER TABLE "public"."content_reports" ENABLE ROW LEVEL SECURITY;

CREATE INDEX IF NOT EXISTS "content_reports_target_key_idx"
    ON "public"."content_reports" ("target_key");

REVOKE ALL ON TABLE "public"."content_reports" FROM PUBLIC;
REVOKE ALL ON TABLE "public"."content_reports" FROM "anon";
REVOKE ALL ON TABLE "public"."content_reports" FROM "authenticated";
GRANT ALL ON TABLE "public"."content_reports" TO "service_role";


-- 4. Admin gate. Internal helper — not granted to PUBLIC/anon/authenticated.
--    Reads app_metadata.role from the caller's JWT (request GUC, not definer).

CREATE OR REPLACE FUNCTION "public"."is_admin"()
RETURNS boolean
LANGUAGE sql
STABLE
AS $$
    SELECT coalesce((auth.jwt() -> 'app_metadata' ->> 'role') = 'admin', false);
$$;

REVOKE ALL ON FUNCTION public.is_admin() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.is_admin() FROM anon;
REVOKE ALL ON FUNCTION public.is_admin() FROM authenticated;


-- 5. submit_variant: same hash + team_variants upsert + first_author +
--    contributor upsert, plus p_team_name and hide-aware author_name.
--    CREATE OR REPLACE cannot change the argument list, so drop the 2-arg
--    overload first — otherwise PostgREST would see two candidates.

DROP FUNCTION IF EXISTS public.submit_variant(jsonb, text);

CREATE OR REPLACE FUNCTION "public"."submit_variant"(
    p_team jsonb,
    p_author_name text DEFAULT NULL,
    p_team_name text DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_user           uuid := auth.uid();
    v_variant_hash   text;
    v_hero_set_hash  text;
    v_variant_id     uuid;
    v_is_new         boolean := false;
    v_capped_author  text;
    v_capped_team    text;
    v_author_hidden  boolean;
BEGIN
    IF v_user IS NULL THEN
        RAISE EXCEPTION 'auth required';
    END IF;

    SELECT h.variant_hash, h.hero_set_hash
      INTO v_variant_hash, v_hero_set_hash
      FROM public.compute_variant_hashes(p_team) h;

    -- Defensive: a hash of NULL/empty inputs would still be deterministic but
    -- meaningless — refuse to register a variant with no main hero.
    IF (p_team->'main'->'hero'->>'name') IS NULL THEN
        RAISE EXCEPTION 'main hero required';
    END IF;

    v_capped_author := NULLIF(left(btrim(coalesce(p_author_name, '')), 30), '');
    v_capped_team   := NULLIF(left(btrim(coalesce(p_team_name, '')),   50), '');
    v_author_hidden := coalesce(
        (SELECT hidden FROM public.display_name_hides WHERE user_id = v_user),
        false
    );

    -- Upsert variant. ON CONFLICT (variant_hash) DO NOTHING returns no row,
    -- so we read it back in the IF NOT FOUND branch.
    INSERT INTO public.team_variants
        (variant_hash, hero_set_hash, team_blob, first_author)
    VALUES
        (v_variant_hash, v_hero_set_hash, p_team, v_user)
    ON CONFLICT (variant_hash) DO NOTHING
    RETURNING id INTO v_variant_id;

    IF v_variant_id IS NOT NULL THEN
        v_is_new := true;
    ELSE
        SELECT id INTO v_variant_id
          FROM public.team_variants
         WHERE variant_hash = v_variant_hash;
    END IF;

    -- Register caller as contributor. Idempotent. Resubmit refreshes the
    -- typed names and the live author-name hide, but must not clear a
    -- team_name hide (auto or admin) already applied to this row.
    INSERT INTO public.variant_contributors
        (variant_id, user_id, author_name, team_name, author_name_hidden)
    VALUES
        (v_variant_id, v_user, v_capped_author, v_capped_team, v_author_hidden)
    ON CONFLICT (variant_id, user_id) DO UPDATE
       SET author_name        = EXCLUDED.author_name,
           team_name          = EXCLUDED.team_name,
           author_name_hidden = EXCLUDED.author_name_hidden;

    -- Last-contributor withdraw deletes the row; resubmit inserts a fresh
    -- unhidden one. Re-apply auto-hide when 3+ team_name reports already
    -- exist, unless an admin hide/unhide is on record.
    UPDATE public.variant_contributors
       SET team_name_hidden = true,
           team_name_hide_source = 'auto'
     WHERE variant_id = v_variant_id
       AND user_id = v_user
       AND team_name_hide_source IS DISTINCT FROM 'admin'
       AND (
           SELECT count(*) FROM public.content_reports
            WHERE target_key = 'team_name:' || v_variant_id::text || ':' || v_user::text
       ) >= 3;

    RETURN jsonb_build_object(
        'variant_id',    v_variant_id,
        'variant_hash',  v_variant_hash,
        'hero_set_hash', v_hero_set_hash,
        'is_new',        v_is_new
    );
END;
$$;

REVOKE ALL ON FUNCTION public.submit_variant(jsonb, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.submit_variant(jsonb, text, text)
    TO authenticated, service_role;


-- 6. report_content: insert-or-touch a report; 3 unique reporters auto-hide
--    unless an admin hide/unhide is already on record.

CREATE OR REPLACE FUNCTION "public"."report_content"(
    p_kind text,
    p_variant_id uuid,
    p_target_user_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_reporter          uuid := auth.uid();
    v_target_key        text;
    v_variant_id        uuid;
    v_already_reported  boolean;
    v_report_count      int;
    v_hidden            boolean := false;
BEGIN
    IF v_reporter IS NULL THEN
        RAISE EXCEPTION 'auth required';
    END IF;

    IF v_reporter = p_target_user_id THEN
        RAISE EXCEPTION 'cannot report yourself';
    END IF;

    IF p_kind IS DISTINCT FROM 'team_name'
       AND p_kind IS DISTINCT FROM 'display_name' THEN
        RAISE EXCEPTION 'unknown kind';
    END IF;

    IF p_kind = 'team_name' THEN
        IF p_variant_id IS NULL THEN
            RAISE EXCEPTION 'variant required';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM public.variant_contributors
             WHERE variant_id = p_variant_id
               AND user_id = p_target_user_id
        ) THEN
            RAISE EXCEPTION 'target is not a contributor';
        END IF;
        v_variant_id := p_variant_id;
        v_target_key := 'team_name:' || p_variant_id::text || ':' || p_target_user_id::text;
    ELSE
        -- display_name reports are user-scoped; variant_id is forced NULL so
        -- the kind-shape CHECK holds even if the client sent a variant id.
        v_variant_id := NULL;
        v_target_key := 'display_name:' || p_target_user_id::text;
    END IF;

    -- Serialize count + auto-hide for this target so concurrent 3rd reports
    -- cannot both observe count=2 and skip the hide.
    PERFORM pg_advisory_xact_lock(hashtextextended(v_target_key, 0));

    SELECT EXISTS (
        SELECT 1 FROM public.content_reports
         WHERE reporter_id = v_reporter AND target_key = v_target_key
    ) INTO v_already_reported;

    INSERT INTO public.content_reports
        (reporter_id, kind, variant_id, target_user_id, target_key)
    VALUES
        (v_reporter, p_kind, v_variant_id, p_target_user_id, v_target_key)
    ON CONFLICT (reporter_id, target_key) DO UPDATE
       SET created_at = now();

    SELECT count(*) INTO v_report_count
      FROM public.content_reports
     WHERE target_key = v_target_key;

    IF v_report_count >= 3 THEN
        IF p_kind = 'team_name' THEN
            UPDATE public.variant_contributors
               SET team_name_hidden = true,
                   team_name_hide_source = 'auto'
             WHERE variant_id = v_variant_id
               AND user_id = p_target_user_id
               AND team_name_hide_source IS DISTINCT FROM 'admin';
        ELSE
            INSERT INTO public.display_name_hides (user_id, hidden, source)
            VALUES (p_target_user_id, true, 'auto')
            ON CONFLICT (user_id) DO UPDATE
               SET hidden     = true,
                   source     = 'auto',
                   updated_at = now()
             WHERE public.display_name_hides.source IS DISTINCT FROM 'admin';

            -- Fan-out only when admin has not claimed this hide. An admin
            -- unhide (hidden=false, source=admin) must not be overwritten.
            UPDATE public.variant_contributors
               SET author_name_hidden = true
             WHERE user_id = p_target_user_id
               AND NOT EXISTS (
                   SELECT 1 FROM public.display_name_hides h
                    WHERE h.user_id = p_target_user_id
                      AND h.source = 'admin'
               );
        END IF;
    END IF;

    IF p_kind = 'team_name' THEN
        SELECT team_name_hidden INTO v_hidden
          FROM public.variant_contributors
         WHERE variant_id = v_variant_id
           AND user_id = p_target_user_id;
    ELSE
        SELECT coalesce(
            (SELECT hidden FROM public.display_name_hides WHERE user_id = p_target_user_id),
            false
        ) INTO v_hidden;
    END IF;

    RETURN jsonb_build_object(
        'ok',                true,
        'hidden',            coalesce(v_hidden, false),
        'already_reported',  v_already_reported
    );
END;
$$;

REVOKE ALL ON FUNCTION public.report_content(text, uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.report_content(text, uuid, uuid)
    TO authenticated, service_role;


-- 7. admin_set_name_hidden: self-gated by is_admin(). source is always
--    'admin' so a later auto-hide will not override the admin decision.

CREATE OR REPLACE FUNCTION "public"."admin_set_name_hidden"(
    p_kind text,
    p_variant_id uuid,
    p_target_user_id uuid,
    p_hidden boolean
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    IF NOT public.is_admin() THEN
        RAISE EXCEPTION 'admin required';
    END IF;

    IF p_kind IS DISTINCT FROM 'team_name'
       AND p_kind IS DISTINCT FROM 'display_name' THEN
        RAISE EXCEPTION 'unknown kind';
    END IF;

    IF p_kind = 'team_name' THEN
        IF p_variant_id IS NULL THEN
            RAISE EXCEPTION 'variant required';
        END IF;
        UPDATE public.variant_contributors
           SET team_name_hidden = p_hidden,
               team_name_hide_source = 'admin'
         WHERE variant_id = p_variant_id
           AND user_id = p_target_user_id;
    ELSE
        INSERT INTO public.display_name_hides (user_id, hidden, source)
        VALUES (p_target_user_id, p_hidden, 'admin')
        ON CONFLICT (user_id) DO UPDATE
           SET hidden     = EXCLUDED.hidden,
               source     = 'admin',
               updated_at = now();

        UPDATE public.variant_contributors
           SET author_name_hidden = p_hidden
         WHERE user_id = p_target_user_id;
    END IF;

    RETURN jsonb_build_object('ok', true, 'hidden', p_hidden);
END;
$$;

REVOKE ALL ON FUNCTION public.admin_set_name_hidden(text, uuid, uuid, boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.admin_set_name_hidden(text, uuid, uuid, boolean)
    TO authenticated, service_role;


-- 8. Backfill team_name from the matching public proposal's name.

UPDATE public.variant_contributors vc
   SET team_name = left(btrim(p.name), 50)
  FROM public.proposals p
  JOIN public.team_variants tv
    ON (public.compute_variant_hashes(p.team_blob)).variant_hash = tv.variant_hash
 WHERE tv.id = vc.variant_id
   AND p.user_id = vc.user_id
   AND p.is_public
   AND vc.team_name IS NULL;
