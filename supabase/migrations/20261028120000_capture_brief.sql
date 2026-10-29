-- Community uploads, step 2: 總覽 (brief) observations and the per-battle entity.
--
-- 20261028000000_capture_ingest.sql is already applied (test data only); this
-- migration rebuilds the capture tables on top of its schema and grants:
--
--   capture.uploads       one row per accepted request: the header, counts and the
--                         rejected indexes. No payload copy.
--   capture.battles       one row per real battle, keyed by what the game prints:
--                         server, time to the second, tile and both sides' four
--                         troop numbers in canonical order, plus `nth` for twins.
--                         Exact match only: a misread number makes a one-source
--                         battle (a split), never a merge of unrelated fights.
--                         No names.
--   capture.observations  one row per user, session, level (list | brief) and seq:
--                         what that user's client read, append-only. battle_id is
--                         null for a partial read (a number, the date or the tile
--                         unread). A user counts once per battle and level.
--   capture.identities    player / alliance HMACs (bytea) per observation, side =
--                         the battle's canonical side (0 = a, 1 = b), never the
--                         uploader's left / right.
--
-- Raw player / alliance names are not stored (HMACs only; a name is looked up by
-- computing its HMAC with the function secret). capture.purge_identity_raw,
-- capture.session_fps, fp_ordinal and the payload copy are gone.
--
-- Matching (capture_ingest below):
--   - A list row with a complete key takes the battle with that key; the nth
--     twin is the rank by seq among this user's rows of the session with the
--     same key (so it depends on the data, not on upload order; a lower seq
--     arriving after a higher one with the same key counts as a duplicate).
--   - A brief joins the battle of this user's list row with the same (session,
--     seq): that pair is the link, its own troop numbers "usually, not always"
--     equal the list row's. A brief without a list row yet uses its own key;
--     when its list row arrives later, the brief moves to the list's battle.
--     A battle listed twice in opposite orientations (both sides in the
--     alliance) is one battle: only rows of the same orientation count.
--   - Side order: ascending [hp, hp_max, wounded, dead]; equal keys: attacker
--     first (core.ts fingerprint). `mirrored` on an observation = its left side
--     is the battle's side b. result stays as read (the uploader's left).
--   - Rows are processed in battle-key order so concurrent uploads of the same
--     battles take their locks in one order; a user's uploads are serialised.


-- 1. Tables -------------------------------------------------------------------

DROP FUNCTION IF EXISTS capture.purge_identity_raw(interval);
DROP TABLE IF EXISTS capture.identities, capture.session_fps, capture.observations, capture.battles, capture.uploads CASCADE;


CREATE TABLE "capture"."uploads" (
    "id"              bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    "user_id"         uuid        NOT NULL REFERENCES "auth"."users"("id") ON DELETE CASCADE,
    "received_at"     timestamptz NOT NULL DEFAULT now(),
    "schema_version"  integer     NOT NULL,
    "client_version"  text        NOT NULL,
    "ocr_model"       text        NOT NULL,
    "consent_version" text        NOT NULL,
    "edition"         text        NOT NULL CHECK ("edition" IN ('tw', 'hk')),
    "server"          text        NOT NULL,
    "session_id"      uuid        NOT NULL,
    "anonymous"       boolean     NOT NULL,
    "captured_at"     timestamptz NOT NULL,
    "battle_count"    integer     NOT NULL,
    "accepted_count"  integer     NOT NULL DEFAULT 0,
    "duplicate_count" integer     NOT NULL DEFAULT 0,
    -- [{index, reason}] of the battles the function rejected.
    "rejected"        jsonb       NOT NULL DEFAULT '[]'::jsonb
);

CREATE INDEX "uploads_user_received_idx" ON "capture"."uploads" ("user_id", "received_at");
CREATE INDEX "uploads_user_session_idx" ON "capture"."uploads" ("user_id", "session_id");


CREATE TABLE "capture"."battles" (
    "id"         bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    "edition"    text        NOT NULL CHECK ("edition" IN ('tw', 'hk')),
    "server"     text        NOT NULL,
    -- Game time as printed (no zone).
    "battle_at"  timestamp   NOT NULL,
    "coord_x"    integer     NOT NULL,
    "coord_y"    integer     NOT NULL,
    "a_hp"       integer     NOT NULL,
    "a_hp_max"   integer     NOT NULL,
    "a_wounded"  integer     NOT NULL,
    "a_dead"     integer     NOT NULL,
    "b_hp"       integer     NOT NULL,
    "b_hp_max"   integer     NOT NULL,
    "b_wounded"  integer     NOT NULL,
    "b_dead"     integer     NOT NULL,
    -- Rank among rows with the otherwise identical key (twin fights of one second on one tile).
    "nth"        smallint    NOT NULL DEFAULT 1 CHECK ("nth" >= 1),
    "created_at" timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT "battles_key" UNIQUE (
        "edition", "server", "battle_at", "coord_x", "coord_y",
        "a_hp", "a_hp_max", "a_wounded", "a_dead",
        "b_hp", "b_hp_max", "b_wounded", "b_dead", "nth"
    )
);


CREATE TABLE "capture"."observations" (
    "id"          bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    "upload_id"   bigint      NOT NULL REFERENCES "capture"."uploads"("id") ON DELETE CASCADE,
    "user_id"     uuid        NOT NULL REFERENCES "auth"."users"("id") ON DELETE CASCADE,
    "session_id"  uuid        NOT NULL,
    "seq"         integer     NOT NULL CHECK ("seq" >= 0),
    "level"       text        NOT NULL CHECK ("level" IN ('list', 'brief')),
    "edition"     text        NOT NULL CHECK ("edition" IN ('tw', 'hk')),
    "server"      text        NOT NULL,
    "battle_id"   bigint      REFERENCES "capture"."battles"("id") ON DELETE SET NULL,
    -- This read's left side is the battle's side b.
    "mirrored"    boolean     NOT NULL DEFAULT false,
    "battle_at"   timestamp,
    "result"      text        CHECK ("result" IN ('win', 'loss', 'draw')),
    "coord_x"     integer,
    "coord_y"     integer,
    -- Side objects as sent, without player / alliance.
    "left_side"   jsonb       NOT NULL,
    "right_side"  jsonb       NOT NULL,
    -- The six 總覽 cards as sent; required for level 'brief', null for 'list'.
    "cards"       jsonb,
    "created_at"  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT "observations_cards_brief" CHECK (
        ("level" = 'brief') = ("cards" IS NOT NULL)
        AND ("cards" IS NULL OR (jsonb_typeof("cards") = 'array' AND jsonb_array_length("cards") = 6))
    ),
    -- The retry key.
    CONSTRAINT "observations_session_seq_key" UNIQUE ("user_id", "session_id", "level", "seq")
);

-- A user counts once per battle and level (also the index on battle_id).
CREATE UNIQUE INDEX "observations_battle_user_level_key"
    ON "capture"."observations" ("battle_id", "user_id", "level") WHERE "battle_id" IS NOT NULL;
CREATE INDEX "observations_upload_idx" ON "capture"."observations" ("upload_id");


CREATE TABLE "capture"."identities" (
    "observation_id" bigint   NOT NULL REFERENCES "capture"."observations"("id") ON DELETE CASCADE,
    -- The battle's canonical side: 0 = a, 1 = b.
    "side"           smallint NOT NULL CHECK ("side" IN (0, 1)),
    "player_hmac"    bytea,
    "alliance_hmac"  bytea,
    PRIMARY KEY ("observation_id", "side") DEFERRABLE INITIALLY DEFERRED
);

-- Removal requests: find a name by its HMAC.
CREATE INDEX "identities_player_hmac_idx" ON "capture"."identities" ("player_hmac") WHERE "player_hmac" IS NOT NULL;
CREATE INDEX "identities_alliance_hmac_idx" ON "capture"."identities" ("alliance_hmac") WHERE "alliance_hmac" IS NOT NULL;


ALTER TABLE "capture"."uploads" OWNER TO "postgres";
ALTER TABLE "capture"."battles" OWNER TO "postgres";
ALTER TABLE "capture"."observations" OWNER TO "postgres";
ALTER TABLE "capture"."identities" OWNER TO "postgres";

ALTER TABLE "capture"."uploads" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "capture"."battles" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "capture"."observations" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "capture"."identities" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE "capture"."uploads", "capture"."battles", "capture"."observations", "capture"."identities" FROM PUBLIC;
REVOKE ALL ON TABLE "capture"."uploads", "capture"."battles", "capture"."observations", "capture"."identities" FROM "anon";
REVOKE ALL ON TABLE "capture"."uploads", "capture"."battles", "capture"."observations", "capture"."identities" FROM "authenticated";
GRANT ALL ON TABLE "capture"."uploads", "capture"."battles", "capture"."observations", "capture"."identities" TO "service_role";


-- 2. Helpers ----------------------------------------------------------------------

-- Which side of battle p_battle the read's left side is: true = b. The side
-- whose four numbers match more of p_left wins; a tie keeps p_default.
CREATE OR REPLACE FUNCTION capture.left_is_b(p_battle bigint, p_left jsonb, p_default boolean)
RETURNS boolean
LANGUAGE sql
STABLE
SET search_path = ''
AS $$
    SELECT CASE
        WHEN sb > sa THEN true
        WHEN sa > sb THEN false
        ELSE p_default
    END
    FROM (
        SELECT (CASE WHEN (p_left->>'hp')::integer        = b.a_hp      THEN 1 ELSE 0 END
              + CASE WHEN (p_left->>'hp_max')::integer    = b.a_hp_max  THEN 1 ELSE 0 END
              + CASE WHEN (p_left->>'wounded')::integer   = b.a_wounded THEN 1 ELSE 0 END
              + CASE WHEN (p_left->>'dead')::integer      = b.a_dead    THEN 1 ELSE 0 END) AS sa,
               (CASE WHEN (p_left->>'hp')::integer        = b.b_hp      THEN 1 ELSE 0 END
              + CASE WHEN (p_left->>'hp_max')::integer    = b.b_hp_max  THEN 1 ELSE 0 END
              + CASE WHEN (p_left->>'wounded')::integer   = b.b_wounded THEN 1 ELSE 0 END
              + CASE WHEN (p_left->>'dead')::integer      = b.b_dead    THEN 1 ELSE 0 END) AS sb
          FROM capture.battles b
         WHERE b.id = p_battle
    ) s;
$$;

ALTER FUNCTION capture.left_is_b(bigint, jsonb, boolean) OWNER TO "postgres";
REVOKE ALL ON FUNCTION capture.left_is_b(bigint, jsonb, boolean) FROM PUBLIC;
REVOKE ALL ON FUNCTION capture.left_is_b(bigint, jsonb, boolean) FROM anon;
REVOKE ALL ON FUNCTION capture.left_is_b(bigint, jsonb, boolean) FROM authenticated;
GRANT EXECUTE ON FUNCTION capture.left_is_b(bigint, jsonb, boolean) TO service_role;


-- Delete the battles no observation points at (after a user, an upload or a
-- name was removed). Returns the rows deleted. Not scheduled.
CREATE OR REPLACE FUNCTION capture.prune_battles()
RETURNS bigint
LANGUAGE sql
SECURITY DEFINER
SET search_path = ''
AS $$
    WITH gone AS (
        DELETE FROM capture.battles b
         WHERE NOT EXISTS (SELECT 1 FROM capture.observations o WHERE o.battle_id = b.id)
        RETURNING 1
    )
    SELECT count(*) FROM gone;
$$;

ALTER FUNCTION capture.prune_battles() OWNER TO "postgres";
REVOKE ALL ON FUNCTION capture.prune_battles() FROM PUBLIC;
REVOKE ALL ON FUNCTION capture.prune_battles() FROM anon;
REVOKE ALL ON FUNCTION capture.prune_battles() FROM authenticated;
GRANT EXECUTE ON FUNCTION capture.prune_battles() TO service_role;


-- A battle with its sources, for the exports (service role only; the schema is
-- not exposed). n_users / n_briefs count distinct users. `dual`: both sides
-- were uploaded from their own list (the opposing alliance's mirrored upload
-- has its left side on the other canonical side). result_a: the result of
-- canonical side a by vote of the list reads (a read's result is its left
-- side's, so a mirrored read is flipped); result_conflict: the reads disagree.
CREATE OR REPLACE VIEW capture.battle_summary AS
WITH reads AS (
    SELECT battle_id, user_id, level, mirrored,
           CASE WHEN mirrored THEN CASE result WHEN 'win' THEN 'loss' WHEN 'loss' THEN 'win' ELSE result END
                ELSE result END AS result_a
      FROM capture.observations
     WHERE battle_id IS NOT NULL
)
SELECT b.id AS battle_id, b.edition, b.server, b.battle_at, b.coord_x, b.coord_y, b.nth,
       b.a_hp, b.a_hp_max, b.a_wounded, b.a_dead, b.b_hp, b.b_hp_max, b.b_wounded, b.b_dead,
       count(DISTINCT r.user_id) FILTER (WHERE r.level = 'list')  AS n_users,
       count(DISTINCT r.user_id) FILTER (WHERE r.level = 'brief') AS n_briefs,
       count(DISTINCT r.mirrored) FILTER (WHERE r.level = 'list') = 2 AS dual,
       mode() WITHIN GROUP (ORDER BY r.result_a) FILTER (WHERE r.level = 'list') AS result_a,
       count(DISTINCT r.result_a) FILTER (WHERE r.level = 'list') > 1 AS result_conflict
  FROM capture.battles b
  LEFT JOIN reads r ON r.battle_id = b.id
 GROUP BY b.id;

ALTER VIEW capture.battle_summary OWNER TO "postgres";
REVOKE ALL ON capture.battle_summary FROM PUBLIC;
REVOKE ALL ON capture.battle_summary FROM anon;
REVOKE ALL ON capture.battle_summary FROM authenticated;
GRANT SELECT ON capture.battle_summary TO service_role;


-- 3. Ingest RPC -------------------------------------------------------------------
--
-- p_header:   the validated upload header (schema_version .. anonymous).
-- p_battles:  accepted battles as capture-ingest/core.ts shapes them
--             (seq, level, date, result, coord, left, right, cards (brief
--             only), fp, nums, mirrored, identities | null).
-- p_rejected: [{index, reason}] of the battles the function rejected.
--
-- Returns {accepted, duplicates}, or {error: 'banned'} or {error:
-- 'rate_limited', limit: 'hour' | 'day', retry_after_s} with nothing written.
-- retry_after_s: until enough of the window ages out for this request to pass
-- (both limits hit: the later one). One transaction; a per-user advisory lock
-- serialises a user's uploads so the rate limits and the twin ranks cannot race.

CREATE OR REPLACE FUNCTION public.capture_ingest(
    p_user_id uuid,
    p_header jsonb,
    p_battles jsonb,
    p_rejected jsonb
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    c_uploads_per_hour constant integer := 20;
    c_battles_per_day  constant integer := 2000;
    v_session   uuid    := (p_header->>'session_id')::uuid;
    v_edition   text    := p_header->>'edition';
    v_server    text    := p_header->>'server';
    v_anonymous boolean := (p_header->>'anonymous')::boolean;
    v_count     integer := jsonb_array_length(p_battles) + jsonb_array_length(p_rejected);
    v_upload    bigint;
    v_accepted  integer := 0;
    v_hour_at   timestamptz;
    v_day_at    timestamptz;
    r           record;
    v_battle    bigint;
    v_nth       integer;
    v_mirrored  boolean;
    v_list_m    boolean;
    v_obs       bigint;
    v_moved     record;
    v_new_m     boolean;
BEGIN
    IF p_user_id IS NULL THEN
        RAISE EXCEPTION 'user required';
    END IF;

    IF public.is_user_banned(p_user_id) THEN
        RETURN jsonb_build_object('error', 'banned');
    END IF;

    PERFORM pg_advisory_xact_lock(hashtextextended('capture_ingest:' || p_user_id::text, 0));

    -- Hour: at most c_uploads_per_hour - 1 earlier uploads may stay in the
    -- window, so the retry time is when the one past them ages out.
    SELECT received_at + interval '1 hour' INTO v_hour_at
      FROM (SELECT received_at FROM capture.uploads
             WHERE user_id = p_user_id
               AND received_at > now() - interval '1 hour'
             ORDER BY received_at DESC
             OFFSET c_uploads_per_hour - 1 LIMIT 1) w;

    -- Day: the oldest uploads age out first; the retry time is when enough
    -- battles have left the window for this request's v_count to fit.
    SELECT received_at + interval '1 day' INTO v_day_at
      FROM (SELECT received_at,
                   sum(battle_count) OVER (ORDER BY received_at DESC, id DESC
                                           ROWS UNBOUNDED PRECEDING) AS kept
              FROM capture.uploads
             WHERE user_id = p_user_id
               AND received_at > now() - interval '1 day') w
     WHERE kept + v_count > c_battles_per_day
     ORDER BY kept
     LIMIT 1;

    IF v_hour_at IS NOT NULL OR v_day_at IS NOT NULL THEN
        RETURN jsonb_build_object(
            'error', 'rate_limited',
            'limit', CASE WHEN v_day_at > v_hour_at OR v_hour_at IS NULL THEN 'day' ELSE 'hour' END,
            'retry_after_s', ceil(extract(epoch FROM greatest(v_hour_at, v_day_at) - now()))::integer
        );
    END IF;

    INSERT INTO capture.uploads (
        user_id, schema_version, client_version, ocr_model, consent_version,
        edition, server, session_id, anonymous, captured_at, battle_count, rejected
    )
    VALUES (
        p_user_id,
        (p_header->>'schema_version')::integer,
        p_header->>'client_version',
        p_header->>'ocr_model',
        p_header->>'consent_version',
        v_edition,
        v_server,
        v_session,
        v_anonymous,
        (p_header->>'captured_at')::timestamptz,
        v_count,
        p_rejected
    )
    RETURNING id INTO v_upload;

    -- One pass in battle-key order (a brief sorts with its list row of this
    -- request), so concurrent uploads of the same battles lock in the same
    -- order; within a key by seq, a list row before its brief.
    FOR r IN
        SELECT s.b,
               (s.b->>'seq')::integer AS seq,
               s.b->>'level' AS level,
               s.k AS k
          FROM (
              SELECT b, CASE WHEN b->>'level' = 'brief'
                             THEN coalesce((SELECT l FROM jsonb_array_elements(p_battles) l
                                             WHERE l->>'level' = 'list'
                                               AND (l->>'seq')::integer = (b->>'seq')::integer
                                               AND l->>'fp' IS NOT NULL LIMIT 1), b)
                             ELSE b END AS k
                FROM jsonb_array_elements(p_battles) b
          ) s
         ORDER BY s.k->>'fp' NULLS LAST, (s.b->>'seq')::integer, (s.b->>'level' = 'brief')
    LOOP
        -- The retry key: this exact read arrived before.
        IF EXISTS (SELECT 1 FROM capture.observations
                    WHERE user_id = p_user_id AND session_id = v_session
                      AND level = r.level AND seq = r.seq) THEN
            CONTINUE;
        END IF;

        v_battle := NULL;
        v_mirrored := coalesce((r.b->>'mirrored')::boolean, false);

        -- A brief joins the battle of its list row (same session, seq).
        IF r.level = 'brief' THEN
            SELECT o.battle_id, o.mirrored INTO v_battle, v_list_m
              FROM capture.observations o
             WHERE o.user_id = p_user_id AND o.session_id = v_session
                   AND o.level = 'list' AND o.seq = r.seq AND o.battle_id IS NOT NULL;
            IF v_battle IS NOT NULL THEN
                v_mirrored := capture.left_is_b(v_battle, r.b->'left', v_list_m);
            END IF;
        END IF;

        -- Otherwise the battle of this read's own key, when it is complete.
        IF v_battle IS NULL AND r.k->'nums' IS NOT NULL AND jsonb_typeof(r.k->'nums') = 'array' THEN
            SELECT 1 + count(*) INTO v_nth
              FROM capture.observations o
              JOIN capture.battles x ON x.id = o.battle_id
             WHERE o.user_id = p_user_id AND o.session_id = v_session
                   AND o.level = r.level AND o.seq < r.seq
                   -- The opposite orientation of one key is the same battle listed from its other side.
                   AND o.mirrored = v_mirrored
                   AND x.edition = v_edition AND x.server = v_server
                   AND x.battle_at = (r.k->>'date')::timestamp
                   AND x.coord_x = (r.k->'coord'->>'x')::integer
                   AND x.coord_y = (r.k->'coord'->>'y')::integer
                   AND (x.a_hp, x.a_hp_max, x.a_wounded, x.a_dead, x.b_hp, x.b_hp_max, x.b_wounded, x.b_dead)
                     = ((r.k->'nums'->>0)::integer, (r.k->'nums'->>1)::integer, (r.k->'nums'->>2)::integer,
                        (r.k->'nums'->>3)::integer, (r.k->'nums'->>4)::integer, (r.k->'nums'->>5)::integer,
                        (r.k->'nums'->>6)::integer, (r.k->'nums'->>7)::integer);

            INSERT INTO capture.battles (
                edition, server, battle_at, coord_x, coord_y,
                a_hp, a_hp_max, a_wounded, a_dead, b_hp, b_hp_max, b_wounded, b_dead, nth
            )
            VALUES (
                v_edition, v_server, (r.k->>'date')::timestamp,
                (r.k->'coord'->>'x')::integer, (r.k->'coord'->>'y')::integer,
                (r.k->'nums'->>0)::integer, (r.k->'nums'->>1)::integer, (r.k->'nums'->>2)::integer,
                (r.k->'nums'->>3)::integer, (r.k->'nums'->>4)::integer, (r.k->'nums'->>5)::integer,
                (r.k->'nums'->>6)::integer, (r.k->'nums'->>7)::integer, v_nth
            )
            -- No-op update: returns the existing id without waiting on a cell lock.
            ON CONFLICT ON CONSTRAINT battles_key DO UPDATE SET nth = capture.battles.nth
            RETURNING id INTO v_battle;
            -- This read's own orientation (a brief without a list row uses its own key).
            v_mirrored := coalesce((r.k->>'mirrored')::boolean, false);
        END IF;

        INSERT INTO capture.observations (
            upload_id, user_id, session_id, seq, level, edition, server, battle_id, mirrored,
            battle_at, result, coord_x, coord_y, left_side, right_side, cards
        )
        VALUES (
            v_upload, p_user_id, v_session, r.seq, r.level, v_edition, v_server, v_battle, v_mirrored,
            (r.b->>'date')::timestamp,
            r.b->>'result',
            (r.b->'coord'->>'x')::integer,
            (r.b->'coord'->>'y')::integer,
            r.b->'left',
            r.b->'right',
            r.b->'cards'
        )
        -- This user already has the battle at this level: a rescan, not a new read.
        ON CONFLICT DO NOTHING
        RETURNING id INTO v_obs;

        IF v_obs IS NULL THEN
            CONTINUE;
        END IF;
        v_accepted := v_accepted + 1;

        IF NOT v_anonymous AND jsonb_typeof(r.b->'identities') = 'object' THEN
            INSERT INTO capture.identities (observation_id, side, player_hmac, alliance_hmac)
            SELECT v_obs, (CASE WHEN (s.side = 'left') <> v_mirrored THEN 0 ELSE 1 END)::smallint,
                   decode(s.i->>'player_hmac', 'hex'), decode(s.i->>'alliance_hmac', 'hex')
              FROM (VALUES ('left', r.b->'identities'->'left'), ('right', r.b->'identities'->'right')) AS s(side, i)
             WHERE jsonb_typeof(s.i) = 'object';
        END IF;

        -- A list row landing after its brief: the brief moves to the list's
        -- battle (or is dropped when this user already has a brief there).
        IF r.level = 'list' AND v_battle IS NOT NULL THEN
            FOR v_moved IN
                SELECT o.id, o.battle_id, o.mirrored, o.left_side
                  FROM capture.observations o
                 WHERE o.user_id = p_user_id AND o.session_id = v_session AND o.seq = r.seq
                       AND o.level = 'brief' AND o.battle_id IS DISTINCT FROM v_battle
            LOOP
                IF EXISTS (SELECT 1 FROM capture.observations
                            WHERE battle_id = v_battle AND user_id = p_user_id AND level = 'brief') THEN
                    DELETE FROM capture.observations WHERE id = v_moved.id;
                ELSE
                    v_new_m := capture.left_is_b(v_battle, v_moved.left_side, v_mirrored);
                    UPDATE capture.observations SET battle_id = v_battle, mirrored = v_new_m WHERE id = v_moved.id;
                    IF v_new_m <> v_moved.mirrored THEN
                        UPDATE capture.identities SET side = (1 - side)::smallint WHERE observation_id = v_moved.id;
                    END IF;
                END IF;
                IF v_moved.battle_id IS NOT NULL THEN
                    DELETE FROM capture.battles b
                     WHERE b.id = v_moved.battle_id
                       AND NOT EXISTS (SELECT 1 FROM capture.observations o WHERE o.battle_id = b.id);
                END IF;
            END LOOP;
        END IF;
    END LOOP;

    UPDATE capture.uploads
       SET accepted_count  = v_accepted,
           duplicate_count = jsonb_array_length(p_battles) - v_accepted
     WHERE id = v_upload;

    RETURN jsonb_build_object(
        'accepted',   v_accepted,
        'duplicates', jsonb_array_length(p_battles) - v_accepted
    );
END;
$$;

ALTER FUNCTION public.capture_ingest(uuid, jsonb, jsonb, jsonb) OWNER TO "postgres";
REVOKE ALL ON FUNCTION public.capture_ingest(uuid, jsonb, jsonb, jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.capture_ingest(uuid, jsonb, jsonb, jsonb) FROM anon;
REVOKE ALL ON FUNCTION public.capture_ingest(uuid, jsonb, jsonb, jsonb) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.capture_ingest(uuid, jsonb, jsonb, jsonb) TO service_role;
