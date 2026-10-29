-- Community uploads, step 2: 總覽 (brief) observations.
--
-- 20261028000000_capture_ingest.sql is already applied; this migration adds
-- what a brief needs on top of it:
--
--   - observations.cards: the six 總覽 cards as sent (hero and skill names, no
--     player or alliance names); required for level 'brief', null for 'list'.
--   - The retry key gains level, so a brief and its list row (same seq) are
--     two observations: (user_id, session_id, level, seq).
--   - capture_ingest stores cards and pairs identities by (seq, level).
--   - capture.session_fps: every (session, level, fp, seq) ever sent, duplicates
--     included, so fp_ordinal is an index lookup instead of a scan of every
--     earlier payload of the session. Backfilled from capture.uploads.
--   - rate_limited says which limit was hit and when to retry.
--
--   - Raw player / alliance names are no longer stored: capture.identities keeps
--     only the HMACs (a name is looked up by computing its HMAC with the
--     function secret). The raw columns and capture.purge_identity_raw go;
--     existing raw values are dropped with the columns.
--
-- A brief is sent with the seq, date and coord of its list row: (user,
-- session, seq) is the join; its own troop numbers usually, not always, give
-- the same fp.


DROP FUNCTION IF EXISTS capture.purge_identity_raw(interval);
ALTER TABLE "capture"."identities" DROP COLUMN IF EXISTS "player_raw";
ALTER TABLE "capture"."identities" DROP COLUMN IF EXISTS "alliance_raw";

ALTER TABLE "capture"."observations" ADD COLUMN IF NOT EXISTS "cards" jsonb;

ALTER TABLE "capture"."observations" ADD CONSTRAINT "observations_cards_brief" CHECK (
    ("level" = 'brief') = ("cards" IS NOT NULL)
    AND ("cards" IS NULL OR (jsonb_typeof("cards") = 'array' AND jsonb_array_length("cards") = 6))
);

ALTER TABLE "capture"."observations" DROP CONSTRAINT "observations_session_seq_key";
ALTER TABLE "capture"."observations"
    ADD CONSTRAINT "observations_session_seq_key" UNIQUE ("user_id", "session_id", "level", "seq");


-- fp_ordinal counts the seqs that duplicates carried too, and a duplicate of
-- another session's battle has no observation row, so observations alone would
-- give a later battle with the same fp a wrong (too low) ordinal. Hence its own
-- table; the primary key is the ordinal query's index.
CREATE TABLE IF NOT EXISTS "capture"."session_fps" (
    "user_id"    uuid    NOT NULL REFERENCES "auth"."users"("id") ON DELETE CASCADE,
    "session_id" uuid    NOT NULL,
    "edition"    text    NOT NULL,
    "server"     text    NOT NULL,
    "level"      text    NOT NULL,
    "fp"         text    NOT NULL,
    "seq"        integer NOT NULL,
    PRIMARY KEY ("user_id", "session_id", "edition", "server", "level", "fp", "seq")
);

ALTER TABLE "capture"."session_fps" OWNER TO "postgres";
ALTER TABLE "capture"."session_fps" ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE "capture"."session_fps" FROM PUBLIC;
REVOKE ALL ON TABLE "capture"."session_fps" FROM "anon";
REVOKE ALL ON TABLE "capture"."session_fps" FROM "authenticated";
GRANT ALL ON TABLE "capture"."session_fps" TO "service_role";

INSERT INTO capture.session_fps (user_id, session_id, edition, server, level, fp, seq)
SELECT DISTINCT u.user_id, u.session_id, u.edition, u.server,
       b->>'level', b->>'fp', (b->>'seq')::integer
  FROM capture.uploads u, jsonb_array_elements(u.payload->'battles') b
 WHERE b->>'fp' IS NOT NULL
ON CONFLICT DO NOTHING;


-- Ingest RPC (replaces the step-1 body) --------------------------------------
--
-- p_header:   the validated upload header (schema_version .. anonymous).
-- p_battles:  accepted battles as capture-ingest/core.ts shapes them
--             (seq, level, date, result, coord, left, right, cards (brief
--             only), fp, mirrored, identities | null).
-- p_rejected: [{index, reason}] of the battles the function rejected.
--
-- Returns {accepted, duplicates}, or {error: 'banned'} or {error:
-- 'rate_limited', limit: 'hour' | 'day', retry_after_s} with nothing written.
-- retry_after_s: until enough of the window ages out for this request to pass
-- (both limits hit: the later one). One transaction; a per-user advisory lock
-- serialises concurrent uploads so the rate limits and ordinals cannot race.
--
-- fp_ordinal = how many distinct seqs of this (user, session, edition, server,
-- level) carry the same fp at a lower seq, over every payload of the session
-- (duplicates included) plus this one, as recorded in capture.session_fps. So
-- the ordinal is the order of first upload within a session: seq 10 uploaded
-- before seq 3 with the same fp takes ordinal 0, and seq 3 then counts as its
-- duplicate (accepted design).

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
    v_hour_at   timestamptz;
    v_day_at    timestamptz;
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

    INSERT INTO capture.session_fps (user_id, session_id, edition, server, level, fp, seq)
    SELECT p_user_id, v_session, v_edition, v_server, b->>'level', b->>'fp', (b->>'seq')::integer
      FROM jsonb_array_elements(p_battles) b
     WHERE b->>'fp' IS NOT NULL
    ON CONFLICT DO NOTHING;

    WITH cur AS (
        SELECT b, (b->>'seq')::integer AS seq, b->>'fp' AS fp, b->>'level' AS level
          FROM jsonb_array_elements(p_battles) b
    ),
    ins AS (
        INSERT INTO capture.observations (
            upload_id, user_id, session_id, seq, level, edition, server,
            battle_at, result, coord_x, coord_y, left_side, right_side,
            cards, fp, fp_ordinal, mirrored
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
            cur.b->'cards',
            cur.fp,
            -- Order of first upload within the session (see the header note).
            CASE WHEN cur.fp IS NULL THEN NULL ELSE (
                SELECT count(*)::integer FROM capture.session_fps s
                 WHERE s.user_id = p_user_id
                   AND s.session_id = v_session
                   AND s.edition = v_edition
                   AND s.server = v_server
                   AND s.level = cur.level
                   AND s.fp = cur.fp
                   AND s.seq < cur.seq
            ) END,
            coalesce((cur.b->>'mirrored')::boolean, false)
          FROM cur
        -- Either unique key: a duplicate.
        ON CONFLICT DO NOTHING
        RETURNING id, seq, level
    ),
    names AS (
        INSERT INTO capture.identities (
            observation_id, side, player_hmac, alliance_hmac
        )
        SELECT ins.id, s.side, s.i->>'player_hmac', s.i->>'alliance_hmac'
          FROM ins
          JOIN cur ON cur.seq = ins.seq AND cur.level = ins.level
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
