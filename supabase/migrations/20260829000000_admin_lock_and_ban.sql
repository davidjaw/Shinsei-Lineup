-- Permanent name lock + account ban.
--
-- Builds on 20260828000000_public_names_moderation:
--
--   1. Locked names stay stored on the row but GET goes through
--      variant_contributors_read, which nulls locked name columns so the
--      UI cannot click-to-reveal. Spoiler hide (unlocked) is unchanged.
--   2. user_bans blocks publish to 公開精選 and flipping a proposal public.
--      Private proposals, private shares, votes, withdraw, and public→private
--      still work.
--
-- compute_variant_hashes is not modified. team_variants / variants are not
-- deleted. report_content stays spoiler-only (does not set locked).


-- 1. Lock columns ------------------------------------------------------------

ALTER TABLE "public"."variant_contributors"
    ADD COLUMN IF NOT EXISTS "team_name_locked" boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS "author_name_locked" boolean NOT NULL DEFAULT false;

ALTER TABLE "public"."variant_contributors"
    DROP CONSTRAINT IF EXISTS "variant_contributors_team_name_locked_hidden",
    DROP CONSTRAINT IF EXISTS "variant_contributors_author_name_locked_hidden";

ALTER TABLE "public"."variant_contributors"
    ADD CONSTRAINT "variant_contributors_team_name_locked_hidden"
        CHECK (NOT "team_name_locked" OR "team_name_hidden"),
    ADD CONSTRAINT "variant_contributors_author_name_locked_hidden"
        CHECK (NOT "author_name_locked" OR "author_name_hidden");

ALTER TABLE "public"."display_name_hides"
    ADD COLUMN IF NOT EXISTS "locked" boolean NOT NULL DEFAULT false;

ALTER TABLE "public"."display_name_hides"
    DROP CONSTRAINT IF EXISTS "display_name_hides_locked_hidden";

ALTER TABLE "public"."display_name_hides"
    ADD CONSTRAINT "display_name_hides_locked_hidden"
        CHECK (NOT "locked" OR "hidden");


-- team_name hide/lock survives contributor withdraw+resubmit (the row is
-- deleted on withdraw). Mirrors display_name_hides, keyed per variant+user.
CREATE TABLE IF NOT EXISTS "public"."team_name_hides" (
    "variant_id" uuid        NOT NULL REFERENCES "public"."team_variants"("id") ON DELETE CASCADE,
    "user_id"    uuid        NOT NULL REFERENCES "auth"."users"("id") ON DELETE CASCADE,
    "hidden"     boolean     NOT NULL,
    "locked"     boolean     NOT NULL DEFAULT false,
    "source"     text        NOT NULL CHECK ("source" IN ('auto', 'admin')),
    "updated_at" timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY ("variant_id", "user_id"),
    CONSTRAINT "team_name_hides_locked_hidden" CHECK (NOT "locked" OR "hidden")
);

ALTER TABLE "public"."team_name_hides" OWNER TO "postgres";
ALTER TABLE "public"."team_name_hides" ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE "public"."team_name_hides" FROM PUBLIC;
REVOKE ALL ON TABLE "public"."team_name_hides" FROM "anon";
REVOKE ALL ON TABLE "public"."team_name_hides" FROM "authenticated";
GRANT ALL ON TABLE "public"."team_name_hides" TO "service_role";


-- 2. user_bans ---------------------------------------------------------------

CREATE TABLE IF NOT EXISTS "public"."user_bans" (
    "user_id"    uuid        PRIMARY KEY REFERENCES "auth"."users"("id") ON DELETE CASCADE,
    "banned_at"  timestamptz NOT NULL DEFAULT now(),
    "banned_by"  uuid        NOT NULL REFERENCES "auth"."users"("id"),
    "reason"     text
);

ALTER TABLE "public"."user_bans" OWNER TO "postgres";
ALTER TABLE "public"."user_bans" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE "public"."user_bans" FROM PUBLIC;
REVOKE ALL ON TABLE "public"."user_bans" FROM "anon";
REVOKE ALL ON TABLE "public"."user_bans" FROM "authenticated";
GRANT ALL ON TABLE "public"."user_bans" TO "service_role";
GRANT SELECT ON TABLE "public"."user_bans" TO "authenticated";

DROP POLICY IF EXISTS "user_bans_self_select" ON "public"."user_bans";
CREATE POLICY "user_bans_self_select"
    ON "public"."user_bans" FOR SELECT TO "authenticated"
    USING ("user_id" = auth.uid());


-- 3. Read view: null locked names. Owner postgres, NOT security_invoker, so
--    it can still read variant_contributors after table SELECT is revoked.

CREATE OR REPLACE VIEW "public"."variant_contributors_read"
    WITH (security_invoker = false)
AS
SELECT
    variant_id,
    user_id,
    contributed_at,
    CASE WHEN team_name_locked THEN NULL ELSE team_name END AS team_name,
    CASE WHEN author_name_locked THEN NULL ELSE author_name END AS author_name,
    team_name_hidden,
    team_name_hide_source,
    team_name_locked,
    author_name_hidden,
    author_name_locked
FROM public.variant_contributors;

ALTER VIEW "public"."variant_contributors_read" OWNER TO "postgres";

REVOKE ALL ON TABLE "public"."variant_contributors_read" FROM PUBLIC;
GRANT SELECT ON TABLE "public"."variant_contributors_read" TO "anon", "authenticated";
GRANT ALL ON TABLE "public"."variant_contributors_read" TO "service_role";
REVOKE SELECT ON TABLE "public"."variant_contributors" FROM "anon", "authenticated";


-- Vote policies subquery variant_contributors; after REVOKE SELECT the
-- invoker cannot read that table. Point them at the granted view instead
-- so votes keep working.

DROP POLICY IF EXISTS "variant_votes_self_insert" ON "public"."variant_votes";
DROP POLICY IF EXISTS "variant_votes_self_update" ON "public"."variant_votes";

CREATE POLICY "variant_votes_self_insert"
    ON "public"."variant_votes" FOR INSERT TO "authenticated"
    WITH CHECK (
        "user_id" = auth.uid()
        AND "variant_id" NOT IN (
            SELECT "variant_id" FROM "public"."variant_contributors_read"
             WHERE "user_id" = auth.uid()
        )
    );

CREATE POLICY "variant_votes_self_update"
    ON "public"."variant_votes" FOR UPDATE TO "authenticated"
    USING ("user_id" = auth.uid())
    WITH CHECK (
        "user_id" = auth.uid()
        AND "variant_id" NOT IN (
            SELECT "variant_id" FROM "public"."variant_contributors_read"
             WHERE "user_id" = auth.uid()
        )
    );


-- 4. Helpers + RPCs ----------------------------------------------------------

CREATE OR REPLACE FUNCTION public.is_user_banned(p_user_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.user_bans WHERE user_id = p_user_id
    );
$$;

REVOKE ALL ON FUNCTION public.is_user_banned(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.is_user_banned(uuid) FROM anon;
REVOKE ALL ON FUNCTION public.is_user_banned(uuid) FROM authenticated;


-- submit_variant: same hash/upsert/contributor path as 20260828, plus a
-- ban gate and author_name_locked copied from display_name_hides.
-- Must not clear team_name_hidden / team_name_hide_source / team_name_locked.

CREATE OR REPLACE FUNCTION public.submit_variant(
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
    v_author_locked  boolean;
BEGIN
    IF v_user IS NULL THEN
        RAISE EXCEPTION 'auth required';
    END IF;

    IF public.is_user_banned(v_user) THEN
        RAISE EXCEPTION 'account banned';
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
    v_author_locked := coalesce(
        (SELECT locked FROM public.display_name_hides WHERE user_id = v_user),
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
    -- typed names and the live author-name hide/lock, but must not clear a
    -- team_name hide/lock already applied to this row.
    INSERT INTO public.variant_contributors
        (variant_id, user_id, author_name, team_name, author_name_hidden, author_name_locked)
    VALUES
        (v_variant_id, v_user, v_capped_author, v_capped_team, v_author_hidden, v_author_locked)
    ON CONFLICT (variant_id, user_id) DO UPDATE
       SET author_name        = EXCLUDED.author_name,
           team_name          = CASE
               WHEN public.variant_contributors.team_name_locked
               THEN public.variant_contributors.team_name
               ELSE EXCLUDED.team_name
           END,
           author_name_hidden = EXCLUDED.author_name_hidden,
           author_name_locked = EXCLUDED.author_name_locked;

    -- Re-apply persisted team-name hide/lock after withdraw deleted the row.
    UPDATE public.variant_contributors vc
       SET team_name_hidden      = h.hidden,
           team_name_locked      = h.locked,
           team_name_hide_source = h.source
      FROM public.team_name_hides h
     WHERE h.variant_id = v_variant_id
       AND h.user_id = v_user
       AND vc.variant_id = v_variant_id
       AND vc.user_id = v_user;

    -- Re-apply auto-hide when 3+ team_name reports already exist, unless an
    -- admin hide/unhide is on record.
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


-- Block INSERT of a public proposal, and private→public flips, for banned
-- users. Already-public rows may still be updated (rename) or set private.

CREATE OR REPLACE FUNCTION public.proposals_reject_banned_public()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    IF NEW.is_public
       AND public.is_user_banned(NEW.user_id)
       AND (TG_OP = 'INSERT' OR OLD.is_public IS DISTINCT FROM TRUE)
    THEN
        RAISE EXCEPTION 'account banned';
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION public.proposals_reject_banned_public() FROM PUBLIC;

DROP TRIGGER IF EXISTS proposals_reject_banned_public ON public.proposals;
CREATE TRIGGER proposals_reject_banned_public
    BEFORE INSERT OR UPDATE ON public.proposals
    FOR EACH ROW
    EXECUTE FUNCTION public.proposals_reject_banned_public();


DROP FUNCTION IF EXISTS public.admin_set_name_hidden(text, uuid, uuid, boolean);

CREATE OR REPLACE FUNCTION public.admin_set_name_hidden(
    p_kind text,
    p_variant_id uuid,
    p_target_user_id uuid,
    p_hidden boolean,
    p_locked boolean DEFAULT false
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_hidden boolean;
    v_locked boolean;
BEGIN
    IF NOT public.is_admin() THEN
        RAISE EXCEPTION 'admin required';
    END IF;

    IF p_kind IS DISTINCT FROM 'team_name'
       AND p_kind IS DISTINCT FROM 'display_name' THEN
        RAISE EXCEPTION 'unknown kind';
    END IF;

    -- Locked implies hidden.
    v_locked := coalesce(p_locked, false);
    v_hidden := coalesce(p_hidden, false) OR v_locked;

    IF p_kind = 'team_name' THEN
        IF p_variant_id IS NULL THEN
            RAISE EXCEPTION 'variant required';
        END IF;
        UPDATE public.variant_contributors
           SET team_name_hidden = v_hidden,
               team_name_locked = v_locked,
               team_name_hide_source = 'admin'
         WHERE variant_id = p_variant_id
           AND user_id = p_target_user_id;

        INSERT INTO public.team_name_hides
            (variant_id, user_id, hidden, locked, source)
        VALUES
            (p_variant_id, p_target_user_id, v_hidden, v_locked, 'admin')
        ON CONFLICT (variant_id, user_id) DO UPDATE
           SET hidden     = EXCLUDED.hidden,
               locked     = EXCLUDED.locked,
               source     = 'admin',
               updated_at = now();
    ELSE
        INSERT INTO public.display_name_hides (user_id, hidden, source, locked)
        VALUES (p_target_user_id, v_hidden, 'admin', v_locked)
        ON CONFLICT (user_id) DO UPDATE
           SET hidden     = EXCLUDED.hidden,
               locked     = EXCLUDED.locked,
               source     = 'admin',
               updated_at = now();

        UPDATE public.variant_contributors
           SET author_name_hidden = v_hidden,
               author_name_locked = v_locked
         WHERE user_id = p_target_user_id;
    END IF;

    RETURN jsonb_build_object('ok', true, 'hidden', v_hidden, 'locked', v_locked);
END;
$$;

REVOKE ALL ON FUNCTION public.admin_set_name_hidden(text, uuid, uuid, boolean, boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.admin_set_name_hidden(text, uuid, uuid, boolean, boolean)
    TO authenticated, service_role;


CREATE OR REPLACE FUNCTION public.admin_set_user_banned(
    p_user_id uuid,
    p_banned boolean,
    p_reason text DEFAULT NULL
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

    IF p_user_id = auth.uid() THEN
        RAISE EXCEPTION 'cannot ban yourself';
    END IF;

    IF p_banned THEN
        INSERT INTO public.user_bans (user_id, banned_by, reason)
        VALUES (p_user_id, auth.uid(), p_reason)
        ON CONFLICT (user_id) DO UPDATE
           SET banned_at = now(),
               banned_by = EXCLUDED.banned_by,
               reason    = EXCLUDED.reason;
    ELSE
        DELETE FROM public.user_bans WHERE user_id = p_user_id;
    END IF;

    RETURN jsonb_build_object('ok', true, 'banned', p_banned);
END;
$$;

REVOKE ALL ON FUNCTION public.admin_set_user_banned(uuid, boolean, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.admin_set_user_banned(uuid, boolean, text)
    TO authenticated, service_role;


CREATE OR REPLACE FUNCTION public.admin_list_banned_users()
RETURNS SETOF uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    IF NOT public.is_admin() THEN
        RAISE EXCEPTION 'admin required';
    END IF;

    RETURN QUERY SELECT user_id FROM public.user_bans;
END;
$$;

REVOKE ALL ON FUNCTION public.admin_list_banned_users() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.admin_list_banned_users()
    TO authenticated, service_role;
