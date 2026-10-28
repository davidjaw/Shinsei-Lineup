-- Community battle-report uploads from the capture web client.
--
-- The capture-ingest edge function verifies the user, validates the payload,
-- computes the fingerprint and the name HMACs, then calls
-- public.capture_ingest() with the service role. Everything lives in the
-- `capture` schema, which PostgREST does not expose; anon / authenticated get
-- no grants on it.
--
--   capture.uploads       one row per accepted request (payload without names)
--   capture.observations  one row per accepted battle, per user, append-only
--   capture.identities    raw player / alliance names + HMACs, per side
--
-- Dedup is per user only, by two unique keys (a violation of either is a
-- duplicate): (user_id, session_id, seq) makes a retry idempotent, null-fp
-- rows included; (user_id, edition, server, level, fp, fp_ordinal) makes a
-- rescan of the same battles in a new session idempotent. Merging
-- one battle across users (alliance mates, the mirrored opponent) is a later
-- derived job.


CREATE SCHEMA IF NOT EXISTS "capture";
ALTER SCHEMA "capture" OWNER TO "postgres";
REVOKE ALL ON SCHEMA "capture" FROM PUBLIC;
REVOKE ALL ON SCHEMA "capture" FROM "anon";
REVOKE ALL ON SCHEMA "capture" FROM "authenticated";
GRANT USAGE ON SCHEMA "capture" TO "service_role";


-- 1. Tables -------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS "capture"."uploads" (
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
    -- The validated header + accepted battles (with fp, no names) + rejected
    -- indexes. Also the source of fp_ordinal for later uploads of the session.
    "payload"         jsonb       NOT NULL,
    "battle_count"    integer     NOT NULL,
    "accepted_count"  integer     NOT NULL DEFAULT 0,
    "duplicate_count" integer     NOT NULL DEFAULT 0,
    "rejected_count"  integer     NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS "uploads_user_received_idx"
    ON "capture"."uploads" ("user_id", "received_at");
CREATE INDEX IF NOT EXISTS "uploads_user_session_idx"
    ON "capture"."uploads" ("user_id", "session_id");


CREATE TABLE IF NOT EXISTS "capture"."observations" (
    "id"          bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    "upload_id"   bigint      NOT NULL REFERENCES "capture"."uploads"("id") ON DELETE CASCADE,
    "user_id"     uuid        NOT NULL REFERENCES "auth"."users"("id") ON DELETE CASCADE,
    "session_id"  uuid        NOT NULL,
    "seq"         integer     NOT NULL CHECK ("seq" >= 0),
    "level"       text        NOT NULL CHECK ("level" IN ('list', 'brief')),
    "edition"     text        NOT NULL CHECK ("edition" IN ('tw', 'hk')),
    "server"      text        NOT NULL,
    -- Game time as printed (no zone).
    "battle_at"   timestamp,
    "result"      text        CHECK ("result" IN ('win', 'loss', 'draw')),
    "coord_x"     integer,
    "coord_y"     integer,
    -- Side objects as sent, without player / alliance.
    "left_side"   jsonb       NOT NULL,
    "right_side"  jsonb       NOT NULL,
    "fp"          text,
    "fp_ordinal"  integer,
    "mirrored"    boolean     NOT NULL,
    -- For the later merge job.
    "status"      text        NOT NULL DEFAULT 'new',
    "created_at"  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT "observations_fp_ordinal_pair" CHECK (("fp" IS NULL) = ("fp_ordinal" IS NULL)),
    CONSTRAINT "observations_session_seq_key" UNIQUE ("user_id", "session_id", "seq"),
    CONSTRAINT "observations_user_fp_key"
        UNIQUE ("user_id", "edition", "server", "level", "fp", "fp_ordinal")
);

CREATE INDEX IF NOT EXISTS "observations_upload_idx"
    ON "capture"."observations" ("upload_id");
CREATE INDEX IF NOT EXISTS "observations_fp_idx"
    ON "capture"."observations" ("server", "fp") WHERE "fp" IS NOT NULL;


-- Raw names are service-role only and kept while the service runs (privacy
-- notice); capture.purge_identity_raw clears them on demand, the HMACs stay.
CREATE TABLE IF NOT EXISTS "capture"."identities" (
    "observation_id" bigint      NOT NULL REFERENCES "capture"."observations"("id") ON DELETE CASCADE,
    "side"           text        NOT NULL CHECK ("side" IN ('left', 'right')),
    "player_raw"     text,
    "alliance_raw"   text,
    "player_hmac"    text,
    "alliance_hmac"  text,
    "created_at"     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY ("observation_id", "side")
);

CREATE INDEX IF NOT EXISTS "identities_created_idx"
    ON "capture"."identities" ("created_at");


ALTER TABLE "capture"."uploads" OWNER TO "postgres";
ALTER TABLE "capture"."observations" OWNER TO "postgres";
ALTER TABLE "capture"."identities" OWNER TO "postgres";

ALTER TABLE "capture"."uploads" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "capture"."observations" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "capture"."identities" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE "capture"."uploads", "capture"."observations", "capture"."identities" FROM PUBLIC;
REVOKE ALL ON TABLE "capture"."uploads", "capture"."observations", "capture"."identities" FROM "anon";
REVOKE ALL ON TABLE "capture"."uploads", "capture"."observations", "capture"."identities" FROM "authenticated";
GRANT ALL ON TABLE "capture"."uploads", "capture"."observations", "capture"."identities" TO "service_role";


-- 2. Ingest RPC -----------------------------------------------------------------
--
-- p_header:   the validated upload header (schema_version .. anonymous).
-- p_battles:  accepted battles as capture-ingest/core.ts shapes them
--             (seq, level, date, result, coord, left, right, fp, mirrored,
--             identities | null).
-- p_rejected: [{index, reason}] of the battles the function rejected.
--
-- Returns {accepted, duplicates}, or {error: 'banned' | 'rate_limited'} with
-- nothing written. One transaction; a per-user advisory lock serialises
-- concurrent uploads so the rate limits and ordinals cannot race.
--
-- fp_ordinal = how many distinct seqs of this (user, session, edition, server,
-- level) carry the same fp at a lower seq, over every payload of the session
-- (duplicates included) plus this one. So the ordinal is the order of first
-- upload within a session: seq 10 uploaded before seq 3 with the same fp
-- takes ordinal 0, and seq 3 then counts as its duplicate (accepted design).

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
    v_accepted  integer;
BEGIN
    IF p_user_id IS NULL THEN
        RAISE EXCEPTION 'user required';
    END IF;

    IF public.is_user_banned(p_user_id) THEN
        RETURN jsonb_build_object('error', 'banned');
    END IF;

    PERFORM pg_advisory_xact_lock(hashtextextended('capture_ingest:' || p_user_id::text, 0));

    IF (SELECT count(*) FROM capture.uploads
         WHERE user_id = p_user_id
           AND received_at > now() - interval '1 hour') >= c_uploads_per_hour
       OR (SELECT coalesce(sum(battle_count), 0) FROM capture.uploads
         WHERE user_id = p_user_id
           AND received_at > now() - interval '1 day') + v_count > c_battles_per_day
    THEN
        RETURN jsonb_build_object('error', 'rate_limited');
    END IF;

    INSERT INTO capture.uploads (
        user_id, schema_version, client_version, ocr_model, consent_version,
        edition, server, session_id, anonymous, captured_at, payload,
        battle_count, rejected_count
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
        p_header || jsonb_build_object(
            'battles', (SELECT coalesce(jsonb_agg(b - 'identities'), '[]'::jsonb)
                          FROM jsonb_array_elements(p_battles) b),
            'rejected', p_rejected
        ),
        v_count,
        jsonb_array_length(p_rejected)
    )
    RETURNING id INTO v_upload;

    WITH cur AS (
        SELECT b, (b->>'seq')::integer AS seq, b->>'fp' AS fp, b->>'level' AS level
          FROM jsonb_array_elements(p_battles) b
    ),
    seen AS (
        SELECT DISTINCT sb->>'level' AS level, sb->>'fp' AS fp, (sb->>'seq')::integer AS seq
          FROM capture.uploads u,
               jsonb_array_elements(u.payload->'battles') sb
         WHERE u.user_id = p_user_id
           AND u.session_id = v_session
           AND u.edition = v_edition
           AND u.server = v_server
           AND sb->>'fp' IS NOT NULL
    ),
    ins AS (
        INSERT INTO capture.observations (
            upload_id, user_id, session_id, seq, level, edition, server,
            battle_at, result, coord_x, coord_y, left_side, right_side,
            fp, fp_ordinal, mirrored
        )
        SELECT
            v_upload, p_user_id, v_session, cur.seq, cur.level,
            v_edition, v_server,
            (cur.b->>'date')::timestamp,
            cur.b->>'result',
            (cur.b->'coord'->>'x')::integer,
            (cur.b->'coord'->>'y')::integer,
            cur.b->'left',
            cur.b->'right',
            cur.fp,
            -- Order of first upload within the session (see the header note).
            CASE WHEN cur.fp IS NULL THEN NULL ELSE (
                SELECT count(*)::integer FROM seen
                 WHERE seen.level = cur.level
                   AND seen.fp = cur.fp
                   AND seen.seq < cur.seq
            ) END,
            coalesce((cur.b->>'mirrored')::boolean, false)
          FROM cur
        -- Either unique key: a duplicate.
        ON CONFLICT DO NOTHING
        RETURNING id, seq
    ),
    names AS (
        INSERT INTO capture.identities (
            observation_id, side, player_raw, alliance_raw, player_hmac, alliance_hmac
        )
        SELECT ins.id, s.side, s.i->>'player_raw', s.i->>'alliance_raw',
               s.i->>'player_hmac', s.i->>'alliance_hmac'
          FROM ins
          JOIN cur ON cur.seq = ins.seq
         CROSS JOIN LATERAL (VALUES
               ('left',  cur.b->'identities'->'left'),
               ('right', cur.b->'identities'->'right')
         ) AS s(side, i)
         WHERE NOT v_anonymous
           AND jsonb_typeof(s.i) = 'object'
        RETURNING 1
    )
    SELECT count(*) INTO v_accepted FROM ins;

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


-- 3. Retention ------------------------------------------------------------------
--
-- Null the raw names older than `older_than`; returns the
-- rows changed. Not scheduled: raw names are kept by policy; run by hand only
-- for a deletion request or a policy change, e.g.
--   SELECT capture.purge_identity_raw(interval '120 days');

CREATE OR REPLACE FUNCTION capture.purge_identity_raw(older_than interval)
RETURNS bigint
LANGUAGE sql
SECURITY DEFINER
SET search_path = ''
AS $$
    WITH purged AS (
        UPDATE capture.identities
           SET player_raw = NULL,
               alliance_raw = NULL
         WHERE created_at < now() - older_than
           AND (player_raw IS NOT NULL OR alliance_raw IS NOT NULL)
        RETURNING 1
    )
    SELECT count(*) FROM purged;
$$;

ALTER FUNCTION capture.purge_identity_raw(interval) OWNER TO "postgres";
REVOKE ALL ON FUNCTION capture.purge_identity_raw(interval) FROM PUBLIC;
REVOKE ALL ON FUNCTION capture.purge_identity_raw(interval) FROM anon;
REVOKE ALL ON FUNCTION capture.purge_identity_raw(interval) FROM authenticated;
GRANT EXECUTE ON FUNCTION capture.purge_identity_raw(interval) TO service_role;
