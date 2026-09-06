-- ATOM-HIST8-CORPUS-AMENDMENT-1
-- Isolated installation only: pjbjpgnmniwcajqkuhge / postgres.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

DO $hist8_install$
DECLARE
  research_schema_exists boolean;
  importer_role_exists boolean;
  protection_signature text;
  routine_signature text;
  column_signature text;
  index_signature text;
  trigger_signature text;
BEGIN
  -- The reviewed installer sets this marker only after establishing a
  -- verify-full TLS session to the frozen direct project endpoint. Refuse
  -- ad-hoc execution before any database object is created.
  IF current_setting('atom.hist8_verified_project_ref', true)
       IS DISTINCT FROM 'pjbjpgnmniwcajqkuhge'
  THEN
    RAISE EXCEPTION 'HIST8_ENDPOINT_IDENTITY_UNVERIFIED';
  END IF;

  IF current_database() <> 'postgres' THEN
    RAISE EXCEPTION 'HIST8_DATABASE_MISMATCH: database %', current_database();
  END IF;

  -- Positive project fingerprint: both legacy V8 objects are present only in the
  -- Owner-designated pjbjpgnmniwcajqkuhge project at the reviewed baseline.
  IF to_regclass('public.coin_v8_market_bars') IS NULL
    OR to_regclass('public.coin_v8_ai_decision_logs') IS NULL
  THEN
    RAISE EXCEPTION
      'HIST8_PROJECT_MISMATCH: not legacy V8 project pjbjpgnmniwcajqkuhge';
  END IF;

  research_schema_exists :=
    to_regnamespace('atom_research_history') IS NOT NULL;
  importer_role_exists := EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = 'atom_hist8_importer'
  );

  -- A partial name collision is never adopted or changed. When both names
  -- exist, make no DDL/grant changes here; the read-only verifier below must
  -- prove the exact prior HIST8 installation before the transaction commits.
  IF research_schema_exists AND NOT importer_role_exists THEN
    RAISE EXCEPTION 'HIST8_RESEARCH_SCHEMA_ALREADY_EXISTS';
  END IF;
  IF importer_role_exists AND NOT research_schema_exists THEN
    RAISE EXCEPTION 'HIST8_IMPORTER_ROLE_ALREADY_EXISTS';
  END IF;

  IF NOT research_schema_exists THEN
    CREATE ROLE atom_hist8_importer
      LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE
      NOREPLICATION NOBYPASSRLS;

    IF EXISTS (
      SELECT 1 FROM pg_auth_members m
      JOIN pg_roles member_role ON member_role.oid = m.member
      WHERE member_role.rolname = 'atom_hist8_importer'
    ) THEN
      RAISE EXCEPTION 'HIST8_ROLE_MEMBERSHIP_MISMATCH';
    END IF;

CREATE SCHEMA atom_research_history AUTHORIZATION postgres;
COMMENT ON ROLE atom_hist8_importer IS
  'ATOM-HIST8-CORPUS-AMENDMENT-1:INSTALLATION-V1';
COMMENT ON SCHEMA atom_research_history IS
  'ATOM-HIST8-CORPUS-AMENDMENT-1:INSTALLATION-V1';
ALTER ROLE atom_hist8_importer
  SET search_path = atom_research_history, pg_catalog;
REVOKE ALL ON SCHEMA atom_research_history FROM PUBLIC, anon, authenticated, service_role;
GRANT USAGE ON SCHEMA atom_research_history TO atom_hist8_importer;

CREATE TABLE atom_research_history.raw_responses (
  artifact_id text PRIMARY KEY
    CHECK (artifact_id ~ '^sha256:[0-9a-f]{64}$'),
  body bytea NOT NULL,
  byte_length bigint NOT NULL CHECK (byte_length >= 0),
  created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT hist8_raw_length_matches CHECK (byte_length = octet_length(body))
);

CREATE TABLE atom_research_history.manifests (
  manifest_id text PRIMARY KEY
    CHECK (manifest_id ~ '^sha256:[0-9a-f]{64}$'),
  corpus_id text NOT NULL CHECK (corpus_id = 'HIST8_20240901_20260901_V1'),
  manifest_kind text NOT NULL
    CHECK (manifest_kind IN (
      'RETRIEVAL', 'IMPORT_ATTEMPT', 'REPLAY_ATTEMPT',
      'BAR_CONFLICT', 'SNAPSHOT_MEMBER', 'SNAPSHOT'
    )),
  import_id text NOT NULL CHECK (length(import_id) BETWEEN 1 AND 128),
  sequence_no bigint NOT NULL CHECK (sequence_no >= 0),
  source text,
  feed text,
  product text,
  instrument text,
  endpoint text,
  request_params jsonb NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(request_params) = 'object'),
  retrieved_at timestamptz,
  http_status integer CHECK (http_status BETWEEN 100 AND 599),
  content_type text,
  content_encoding text,
  artifact_id text REFERENCES atom_research_history.raw_responses(artifact_id)
    ON DELETE RESTRICT,
  artifact_byte_length bigint CHECK (artifact_byte_length >= 0),
  member_bar_id text,
  member_content_hash text CHECK (
    member_content_hash IS NULL OR member_content_hash ~ '^[0-9a-f]{64}$'
  ),
  member_provenance_hash text CHECK (
    member_provenance_hash IS NULL
    OR member_provenance_hash ~ '^[0-9a-f]{64}$'
  ),
  member_timeframe text CHECK (
    member_timeframe IS NULL OR member_timeframe IN ('1m','5m','15m','30m','1H')
  ),
  member_bar_start_utc timestamptz,
  member_research_eligible boolean,
  metadata_json jsonb NOT NULL CHECK (jsonb_typeof(metadata_json) = 'object'),
  created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT hist8_retrieval_artifact_required CHECK (
    manifest_kind <> 'RETRIEVAL'
    OR (source IS NOT NULL AND feed IS NOT NULL AND product IS NOT NULL
        AND endpoint IS NOT NULL AND retrieved_at IS NOT NULL
        AND http_status IS NOT NULL AND artifact_id IS NOT NULL
        AND artifact_byte_length IS NOT NULL)
  ),
  CONSTRAINT hist8_snapshot_member_required CHECK (
    (manifest_kind = 'SNAPSHOT_MEMBER'
      AND instrument IS NOT NULL AND member_bar_id IS NOT NULL
      AND member_content_hash IS NOT NULL AND member_timeframe IS NOT NULL
      AND member_provenance_hash IS NOT NULL
      AND member_bar_start_utc IS NOT NULL
      AND member_research_eligible IS NOT NULL)
    OR (manifest_kind <> 'SNAPSHOT_MEMBER'
      AND member_bar_id IS NULL AND member_content_hash IS NULL
      AND member_provenance_hash IS NULL
      AND member_timeframe IS NULL AND member_bar_start_utc IS NULL
      AND member_research_eligible IS NULL)
  ),
  UNIQUE (import_id, sequence_no, manifest_kind)
);

CREATE TABLE atom_research_history.bars (
  bar_id text PRIMARY KEY CHECK (bar_id ~ '^hist8bar:[0-9a-f]{64}$'),
  content_hash text UNIQUE NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  corpus_id text NOT NULL CHECK (corpus_id = 'HIST8_20240901_20260901_V1'),
  instrument text NOT NULL
    CHECK (instrument IN ('COIN','QQQ','SPY','NVDA','XLE','GLD','BTC-USD','NASDAQ')),
  timeframe text NOT NULL CHECK (timeframe IN ('1m','5m','15m','30m','1H')),
  bar_start_utc timestamptz NOT NULL,
  bar_end_utc timestamptz NOT NULL,
  session_date text NOT NULL CHECK (session_date ~ '^20[0-9]{2}-[0-9]{2}-[0-9]{2}$'),
  calendar_id text NOT NULL,
  calendar_sha256 text NOT NULL CHECK (calendar_sha256 ~ '^[0-9a-f]{64}$'),
  open numeric NOT NULL CHECK (open > 0),
  high numeric NOT NULL CHECK (high > 0),
  low numeric NOT NULL CHECK (low > 0),
  close numeric NOT NULL CHECK (close > 0),
  volume numeric CHECK (volume >= 0),
  trade_count bigint CHECK (trade_count >= 0),
  vwap numeric CHECK (vwap > 0),
  volume_unit text NOT NULL CHECK (volume_unit IN ('SHARES','BTC','NOT_APPLICABLE')),
  source text NOT NULL,
  feed text NOT NULL,
  product text NOT NULL,
  adjustment text NOT NULL,
  currency text NOT NULL CHECK (currency = 'USD'),
  import_id text NOT NULL CHECK (length(import_id) BETWEEN 1 AND 128),
  derivation_version text,
  source_artifact_id text REFERENCES atom_research_history.raw_responses(artifact_id)
    ON DELETE RESTRICT,
  source_record_locator text,
  lineage_json jsonb NOT NULL CHECK (jsonb_typeof(lineage_json) = 'array'),
  created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT hist8_bar_interval CHECK (bar_end_utc > bar_start_utc),
  CONSTRAINT hist8_bar_duration CHECK (
    bar_end_utc - bar_start_utc = CASE timeframe
      WHEN '1m' THEN interval '60 seconds'
      WHEN '5m' THEN interval '300 seconds'
      WHEN '15m' THEN interval '900 seconds'
      WHEN '30m' THEN interval '1800 seconds'
      ELSE interval '3600 seconds'
    END
  ),
  CONSTRAINT hist8_bar_ohlc CHECK (
    low <= LEAST(open, close) AND GREATEST(open, close) <= high
  ),
  CONSTRAINT hist8_bar_volume_semantics CHECK (
    (instrument = 'NASDAQ' AND volume IS NULL AND volume_unit = 'NOT_APPLICABLE')
    OR (instrument <> 'NASDAQ' AND volume IS NOT NULL AND volume_unit IN ('SHARES','BTC'))
  ),
  CONSTRAINT hist8_bar_lineage CHECK (
    (timeframe = '1m' AND derivation_version IS NULL
      AND source_artifact_id IS NOT NULL AND source_record_locator IS NOT NULL
      AND jsonb_array_length(lineage_json) = 0)
    OR (timeframe <> '1m' AND derivation_version = 'HIST8_DERIVE_1'
      AND source_artifact_id IS NULL AND source_record_locator IS NULL
      AND jsonb_array_length(lineage_json) > 0)
  ),
  UNIQUE (corpus_id, instrument, timeframe, bar_start_utc)
);

ALTER TABLE atom_research_history.bars
  ADD CONSTRAINT hist8_bar_identity_pair UNIQUE (bar_id, content_hash);
ALTER TABLE atom_research_history.manifests
  ADD CONSTRAINT hist8_snapshot_member_bar_fk
  FOREIGN KEY (member_bar_id, member_content_hash)
  REFERENCES atom_research_history.bars (bar_id, content_hash)
  ON DELETE RESTRICT;

CREATE INDEX hist8_bars_snapshot_scan_idx
  ON atom_research_history.bars (corpus_id, instrument, timeframe, bar_start_utc);
CREATE INDEX hist8_bars_session_lookup_idx
  ON atom_research_history.bars
  (corpus_id, instrument, session_date, timeframe, bar_start_utc);
CREATE INDEX hist8_manifests_import_idx
  ON atom_research_history.manifests (corpus_id, import_id, manifest_kind, sequence_no);

CREATE OR REPLACE FUNCTION atom_research_history.reject_mutation()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $function$
BEGIN
  RAISE EXCEPTION 'HIST8 evidence is append-only';
END
$function$;

REVOKE ALL ON FUNCTION atom_research_history.reject_mutation() FROM PUBLIC, anon, authenticated, service_role, atom_hist8_importer;

CREATE OR REPLACE FUNCTION atom_research_history.guard_snapshot_membership()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $function$
BEGIN
  IF NEW.manifest_kind IN ('SNAPSHOT_MEMBER', 'RETRIEVAL') THEN
    PERFORM pg_catalog.pg_advisory_xact_lock(
      pg_catalog.hashtextextended(NEW.import_id, 0)
    );
    IF EXISTS (
      SELECT 1
      FROM atom_research_history.manifests
      WHERE corpus_id = NEW.corpus_id
        AND import_id = NEW.import_id
        AND manifest_kind = 'SNAPSHOT'
    ) THEN
      RAISE EXCEPTION 'HIST8 import evidence is sealed';
    END IF;
  END IF;
  RETURN NEW;
END
$function$;

REVOKE ALL ON FUNCTION atom_research_history.guard_snapshot_membership() FROM PUBLIC, anon, authenticated, service_role, atom_hist8_importer;

CREATE TRIGGER hist8_raw_reject_update_delete
  BEFORE UPDATE OR DELETE ON atom_research_history.raw_responses
  FOR EACH ROW EXECUTE FUNCTION atom_research_history.reject_mutation();
CREATE TRIGGER hist8_raw_reject_truncate
  BEFORE TRUNCATE ON atom_research_history.raw_responses
  FOR EACH STATEMENT EXECUTE FUNCTION atom_research_history.reject_mutation();
CREATE TRIGGER hist8_manifests_reject_update_delete
  BEFORE UPDATE OR DELETE ON atom_research_history.manifests
  FOR EACH ROW EXECUTE FUNCTION atom_research_history.reject_mutation();
CREATE TRIGGER hist8_manifests_reject_truncate
  BEFORE TRUNCATE ON atom_research_history.manifests
  FOR EACH STATEMENT EXECUTE FUNCTION atom_research_history.reject_mutation();
CREATE TRIGGER hist8_snapshot_membership_guard
  BEFORE INSERT ON atom_research_history.manifests
  FOR EACH ROW EXECUTE FUNCTION atom_research_history.guard_snapshot_membership();
CREATE TRIGGER hist8_bars_reject_update_delete
  BEFORE UPDATE OR DELETE ON atom_research_history.bars
  FOR EACH ROW EXECUTE FUNCTION atom_research_history.reject_mutation();
CREATE TRIGGER hist8_bars_reject_truncate
  BEFORE TRUNCATE ON atom_research_history.bars
  FOR EACH STATEMENT EXECUTE FUNCTION atom_research_history.reject_mutation();

ALTER TABLE atom_research_history.raw_responses ENABLE ROW LEVEL SECURITY;
ALTER TABLE atom_research_history.raw_responses FORCE ROW LEVEL SECURITY;
ALTER TABLE atom_research_history.manifests ENABLE ROW LEVEL SECURITY;
ALTER TABLE atom_research_history.manifests FORCE ROW LEVEL SECURITY;
ALTER TABLE atom_research_history.bars ENABLE ROW LEVEL SECURITY;
ALTER TABLE atom_research_history.bars FORCE ROW LEVEL SECURITY;

CREATE POLICY hist8_raw_importer_select ON atom_research_history.raw_responses
  FOR SELECT TO atom_hist8_importer USING (true);
CREATE POLICY hist8_raw_importer_insert ON atom_research_history.raw_responses
  FOR INSERT TO atom_hist8_importer WITH CHECK (true);
CREATE POLICY hist8_manifests_importer_select ON atom_research_history.manifests
  FOR SELECT TO atom_hist8_importer USING (true);
CREATE POLICY hist8_manifests_importer_insert ON atom_research_history.manifests
  FOR INSERT TO atom_hist8_importer WITH CHECK (true);
CREATE POLICY hist8_bars_importer_select ON atom_research_history.bars
  FOR SELECT TO atom_hist8_importer USING (true);
CREATE POLICY hist8_bars_importer_insert ON atom_research_history.bars
  FOR INSERT TO atom_hist8_importer WITH CHECK (true);

REVOKE ALL ON ALL TABLES IN SCHEMA atom_research_history FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON atom_research_history.raw_responses,
  atom_research_history.manifests, atom_research_history.bars
  TO atom_hist8_importer;

  -- Seal every normalized constraint definition from this reviewed creation.
  -- The retry verifier recomputes this catalog signature, so a renamed,
  -- weakened, added, removed, or action-modified protection cannot be adopted.
  SELECT md5(string_agg(
           format('%s.%s|%s|%s|%s|%s', schema.nspname,
                  table_object.relname, constraint_object.conname,
                  constraint_object.contype,
                  constraint_object.convalidated,
                  pg_get_constraintdef(constraint_object.oid, true)),
           E'\n' ORDER BY table_object.relname, constraint_object.conname
         ))
    INTO protection_signature
  FROM pg_constraint constraint_object
  JOIN pg_class table_object
    ON table_object.oid = constraint_object.conrelid
  JOIN pg_namespace schema ON schema.oid = table_object.relnamespace
  WHERE schema.nspname = 'atom_research_history'
    AND table_object.relname IN ('raw_responses','manifests','bars');
  IF protection_signature IS NULL THEN
    RAISE EXCEPTION 'HIST8_INSTALLATION_PROTECTION_SIGNATURE_MISSING';
  END IF;

  -- Seal the complete normalized definitions of both trigger functions. A
  -- retry must reject any changed body, even when a replacement happens to
  -- retain an expected error-message substring.
  SELECT md5(string_agg(
           format('%s.%s(%s)|%s|%s', schema.nspname, routine.proname,
                  pg_get_function_identity_arguments(routine.oid),
                  routine.proowner,
                  pg_get_functiondef(routine.oid)),
           E'\n' ORDER BY routine.proname,
                          pg_get_function_identity_arguments(routine.oid)
         ))
    INTO routine_signature
  FROM pg_proc routine
  JOIN pg_namespace schema ON schema.oid = routine.pronamespace
  WHERE schema.nspname = 'atom_research_history';
  IF routine_signature IS NULL THEN
    RAISE EXCEPTION 'HIST8_INSTALLATION_ROUTINE_SIGNATURE_MISSING';
  END IF;

  -- Bind all durable column attributes, including nullability and defaults,
  -- plus the stable logical table properties. Physical/statistics fields are
  -- deliberately excluded because VACUUM and rewrites may change them.
  SELECT md5(jsonb_agg(jsonb_build_array(
           schema.nspname, table_object.relname,
           table_object.relkind::text, table_object.relpersistence::text,
           table_object.relowner, table_object.relam,
           table_object.reltablespace, table_object.reloptions,
           table_object.relrowsecurity, table_object.relforcerowsecurity,
           table_object.relreplident::text,
           column_object.attnum, column_object.attname,
           format_type(column_object.atttypid, column_object.atttypmod),
           column_object.attnotnull, column_object.atthasdef,
           column_object.atthasmissing, column_object.attidentity::text,
           column_object.attgenerated::text, column_object.attcollation,
           column_object.attstorage::text, column_object.attcompression::text,
           column_object.attstattarget, column_object.attislocal,
           column_object.attinhcount, column_object.attacl,
           column_object.attoptions, column_object.attfdwoptions,
           pg_get_expr(default_object.adbin, default_object.adrelid, true)
         ) ORDER BY table_object.relname, column_object.attnum)::text)
    INTO column_signature
  FROM pg_class table_object
  JOIN pg_namespace schema ON schema.oid = table_object.relnamespace
  JOIN pg_attribute column_object
    ON column_object.attrelid = table_object.oid
  LEFT JOIN pg_attrdef default_object
    ON default_object.adrelid = table_object.oid
   AND default_object.adnum = column_object.attnum
  WHERE schema.nspname = 'atom_research_history'
    AND table_object.relname IN ('raw_responses','manifests','bars')
    AND table_object.relkind = 'r'
    AND column_object.attnum > 0
    AND NOT column_object.attisdropped;

  SELECT md5(jsonb_agg(jsonb_build_array(
           schema.nspname, index_object.relname, table_object.relname,
           index_object.relowner, index_object.relpersistence::text,
           index_object.relam, index_object.reltablespace,
           index_object.reloptions, index_metadata.indnatts,
           index_metadata.indnkeyatts, index_metadata.indisunique,
           index_metadata.indisprimary, index_metadata.indisexclusion,
           index_metadata.indimmediate, index_metadata.indisclustered,
           index_metadata.indisvalid, index_metadata.indcheckxmin,
           index_metadata.indisready, index_metadata.indislive,
           index_metadata.indisreplident, index_metadata.indkey::text,
           index_metadata.indcollation::text,
           index_metadata.indclass::text, index_metadata.indoption::text,
           pg_get_expr(index_metadata.indexprs,
                       index_metadata.indrelid, true),
           pg_get_expr(index_metadata.indpred,
                       index_metadata.indrelid, true),
           pg_get_indexdef(index_object.oid)
         ) ORDER BY index_object.relname)::text)
    INTO index_signature
  FROM pg_class index_object
  JOIN pg_namespace schema ON schema.oid = index_object.relnamespace
  JOIN pg_index index_metadata
    ON index_metadata.indexrelid = index_object.oid
  JOIN pg_class table_object ON table_object.oid = index_metadata.indrelid
  WHERE schema.nspname = 'atom_research_history';

  SELECT md5(jsonb_agg(jsonb_build_array(
           schema.nspname, table_object.relname, trigger_object.tgname,
           trigger_object.tgfoid, trigger_object.tgtype,
           trigger_object.tgenabled::text, trigger_object.tgconstraint,
           trigger_object.tgconstrrelid, trigger_object.tgdeferrable,
           trigger_object.tginitdeferred, trigger_object.tgnargs,
           encode(trigger_object.tgargs, 'hex'),
           trigger_object.tgattr::text, trigger_object.tgoldtable,
           trigger_object.tgnewtable,
           pg_get_triggerdef(trigger_object.oid, true)
         ) ORDER BY table_object.relname, trigger_object.tgname)::text)
    INTO trigger_signature
  FROM pg_trigger trigger_object
  JOIN pg_class table_object ON table_object.oid = trigger_object.tgrelid
  JOIN pg_namespace schema ON schema.oid = table_object.relnamespace
  WHERE schema.nspname = 'atom_research_history'
    AND NOT trigger_object.tgisinternal;

  IF column_signature IS NULL OR index_signature IS NULL
    OR trigger_signature IS NULL
  THEN
    RAISE EXCEPTION 'HIST8_INSTALLATION_SURFACE_SIGNATURE_MISSING';
  END IF;
  EXECUTE format(
    'COMMENT ON SCHEMA atom_research_history IS %L',
    'ATOM-HIST8-CORPUS-AMENDMENT-1:INSTALLATION-V1:'
      || protection_signature || ':' || routine_signature
      || ':' || column_signature || ':' || index_signature
      || ':' || trigger_signature
  );

  END IF;
END
$hist8_install$;

DO $hist8_verify$
DECLARE
  protection_signature text;
  routine_signature text;
  column_signature text;
  index_signature text;
  trigger_signature text;
BEGIN
  -- This block is also the retry path after an ambiguous client disconnect.
  -- It is deliberately read-only: an existing pair is accepted only when the
  -- installation marker and independently inspected catalog structure match.
  IF NOT EXISTS (
    SELECT 1
    FROM pg_roles role
    WHERE role.rolname = 'atom_hist8_importer'
      AND role.rolcanlogin AND NOT role.rolinherit
      AND NOT role.rolsuper AND NOT role.rolcreatedb
      AND NOT role.rolcreaterole AND NOT role.rolreplication
      AND NOT role.rolbypassrls AND role.rolconnlimit = -1
      AND shobj_description(role.oid, 'pg_authid') =
        'ATOM-HIST8-CORPUS-AMENDMENT-1:INSTALLATION-V1'
  ) OR EXISTS (
    SELECT 1
    FROM pg_auth_members membership
    WHERE membership.member = 'atom_hist8_importer'::regrole
       OR membership.roleid = 'atom_hist8_importer'::regrole
  ) OR (SELECT count(*)
        FROM pg_db_role_setting setting
        WHERE setting.setrole = 'atom_hist8_importer'::regrole) <> 1
    OR NOT EXISTS (
      SELECT 1
      FROM pg_db_role_setting setting
      WHERE setting.setrole = 'atom_hist8_importer'::regrole
        AND setting.setdatabase = 0
        AND setting.setconfig =
          ARRAY['search_path=atom_research_history, pg_catalog']
  ) THEN
    RAISE EXCEPTION 'HIST8_EXISTING_INSTALLATION_ROLE_MISMATCH';
  END IF;

  SELECT md5(string_agg(
           format('%s.%s|%s|%s|%s|%s', schema.nspname,
                  table_object.relname, constraint_object.conname,
                  constraint_object.contype,
                  constraint_object.convalidated,
                  pg_get_constraintdef(constraint_object.oid, true)),
           E'\n' ORDER BY table_object.relname, constraint_object.conname
         ))
    INTO protection_signature
  FROM pg_constraint constraint_object
  JOIN pg_class table_object
    ON table_object.oid = constraint_object.conrelid
  JOIN pg_namespace schema ON schema.oid = table_object.relnamespace
  WHERE schema.nspname = 'atom_research_history'
    AND table_object.relname IN ('raw_responses','manifests','bars');

  SELECT md5(string_agg(
           format('%s.%s(%s)|%s|%s', schema.nspname, routine.proname,
                  pg_get_function_identity_arguments(routine.oid),
                  routine.proowner,
                  pg_get_functiondef(routine.oid)),
           E'\n' ORDER BY routine.proname,
                          pg_get_function_identity_arguments(routine.oid)
         ))
    INTO routine_signature
  FROM pg_proc routine
  JOIN pg_namespace schema ON schema.oid = routine.pronamespace
  WHERE schema.nspname = 'atom_research_history';

  SELECT md5(jsonb_agg(jsonb_build_array(
           schema.nspname, table_object.relname,
           table_object.relkind::text, table_object.relpersistence::text,
           table_object.relowner, table_object.relam,
           table_object.reltablespace, table_object.reloptions,
           table_object.relrowsecurity, table_object.relforcerowsecurity,
           table_object.relreplident::text,
           column_object.attnum, column_object.attname,
           format_type(column_object.atttypid, column_object.atttypmod),
           column_object.attnotnull, column_object.atthasdef,
           column_object.atthasmissing, column_object.attidentity::text,
           column_object.attgenerated::text, column_object.attcollation,
           column_object.attstorage::text, column_object.attcompression::text,
           column_object.attstattarget, column_object.attislocal,
           column_object.attinhcount, column_object.attacl,
           column_object.attoptions, column_object.attfdwoptions,
           pg_get_expr(default_object.adbin, default_object.adrelid, true)
         ) ORDER BY table_object.relname, column_object.attnum)::text)
    INTO column_signature
  FROM pg_class table_object
  JOIN pg_namespace schema ON schema.oid = table_object.relnamespace
  JOIN pg_attribute column_object
    ON column_object.attrelid = table_object.oid
  LEFT JOIN pg_attrdef default_object
    ON default_object.adrelid = table_object.oid
   AND default_object.adnum = column_object.attnum
  WHERE schema.nspname = 'atom_research_history'
    AND table_object.relname IN ('raw_responses','manifests','bars')
    AND table_object.relkind = 'r'
    AND column_object.attnum > 0
    AND NOT column_object.attisdropped;

  SELECT md5(jsonb_agg(jsonb_build_array(
           schema.nspname, index_object.relname, table_object.relname,
           index_object.relowner, index_object.relpersistence::text,
           index_object.relam, index_object.reltablespace,
           index_object.reloptions, index_metadata.indnatts,
           index_metadata.indnkeyatts, index_metadata.indisunique,
           index_metadata.indisprimary, index_metadata.indisexclusion,
           index_metadata.indimmediate, index_metadata.indisclustered,
           index_metadata.indisvalid, index_metadata.indcheckxmin,
           index_metadata.indisready, index_metadata.indislive,
           index_metadata.indisreplident, index_metadata.indkey::text,
           index_metadata.indcollation::text,
           index_metadata.indclass::text, index_metadata.indoption::text,
           pg_get_expr(index_metadata.indexprs,
                       index_metadata.indrelid, true),
           pg_get_expr(index_metadata.indpred,
                       index_metadata.indrelid, true),
           pg_get_indexdef(index_object.oid)
         ) ORDER BY index_object.relname)::text)
    INTO index_signature
  FROM pg_class index_object
  JOIN pg_namespace schema ON schema.oid = index_object.relnamespace
  JOIN pg_index index_metadata
    ON index_metadata.indexrelid = index_object.oid
  JOIN pg_class table_object ON table_object.oid = index_metadata.indrelid
  WHERE schema.nspname = 'atom_research_history';

  SELECT md5(jsonb_agg(jsonb_build_array(
           schema.nspname, table_object.relname, trigger_object.tgname,
           trigger_object.tgfoid, trigger_object.tgtype,
           trigger_object.tgenabled::text, trigger_object.tgconstraint,
           trigger_object.tgconstrrelid, trigger_object.tgdeferrable,
           trigger_object.tginitdeferred, trigger_object.tgnargs,
           encode(trigger_object.tgargs, 'hex'),
           trigger_object.tgattr::text, trigger_object.tgoldtable,
           trigger_object.tgnewtable,
           pg_get_triggerdef(trigger_object.oid, true)
         ) ORDER BY table_object.relname, trigger_object.tgname)::text)
    INTO trigger_signature
  FROM pg_trigger trigger_object
  JOIN pg_class table_object ON table_object.oid = trigger_object.tgrelid
  JOIN pg_namespace schema ON schema.oid = table_object.relnamespace
  WHERE schema.nspname = 'atom_research_history'
    AND NOT trigger_object.tgisinternal;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_namespace schema
    WHERE schema.nspname = 'atom_research_history'
      AND schema.nspowner = 'postgres'::regrole
      AND obj_description(schema.oid, 'pg_namespace') LIKE
        'ATOM-HIST8-CORPUS-AMENDMENT-1:INSTALLATION-V1:%'
  ) THEN
    RAISE EXCEPTION 'HIST8_EXISTING_INSTALLATION_SCHEMA_MISMATCH';
  END IF;

  IF (SELECT count(*)
      FROM pg_class object
      JOIN pg_namespace schema ON schema.oid = object.relnamespace
      WHERE schema.nspname = 'atom_research_history'
        AND object.relkind = 'r') <> 3
    OR (SELECT count(*)
        FROM pg_class object
        JOIN pg_namespace schema ON schema.oid = object.relnamespace
        WHERE schema.nspname = 'atom_research_history'
          AND object.relkind = 'i') <> 10
    OR EXISTS (
      SELECT 1
      FROM pg_class object
      JOIN pg_namespace schema ON schema.oid = object.relnamespace
      WHERE schema.nspname = 'atom_research_history'
        AND NOT (
          (object.relkind = 'r' AND object.relname IN (
            'raw_responses', 'manifests', 'bars'
          ))
          OR (object.relkind = 'i' AND object.relname IN (
            'raw_responses_pkey',
            'manifests_pkey',
            'manifests_import_id_sequence_no_manifest_kind_key',
            'bars_pkey',
            'bars_content_hash_key',
            'bars_corpus_id_instrument_timeframe_bar_start_utc_key',
            'hist8_bar_identity_pair',
            'hist8_bars_snapshot_scan_idx',
            'hist8_bars_session_lookup_idx',
            'hist8_manifests_import_idx'
          ))
        )
    )
    OR EXISTS (
      SELECT 1
      FROM (VALUES
        ('raw_responses', 4, ARRAY[
          'artifact_id','body','byte_length','created_at'
        ]::text[], ARRAY[
          'text','bytea','bigint','timestamp with time zone'
        ]::text[]),
        ('manifests', 25, ARRAY[
          'manifest_id','corpus_id','manifest_kind','import_id','sequence_no',
          'source','feed','product','instrument','endpoint','request_params',
          'retrieved_at','http_status','content_type','content_encoding',
          'artifact_id','artifact_byte_length','member_bar_id',
          'member_content_hash','member_provenance_hash','member_timeframe',
          'member_bar_start_utc','member_research_eligible','metadata_json',
          'created_at'
        ]::text[], ARRAY[
          'text','text','text','text','bigint','text','text','text','text',
          'text','jsonb','timestamp with time zone','integer','text','text',
          'text','bigint','text','text','text','text',
          'timestamp with time zone','boolean','jsonb',
          'timestamp with time zone'
        ]::text[]),
        ('bars', 29, ARRAY[
          'bar_id','content_hash','corpus_id','instrument','timeframe',
          'bar_start_utc','bar_end_utc','session_date','calendar_id',
          'calendar_sha256','open','high','low','close','volume','trade_count',
          'vwap','volume_unit','source','feed','product','adjustment','currency',
          'import_id','derivation_version','source_artifact_id',
          'source_record_locator','lineage_json','created_at'
        ]::text[], ARRAY[
          'text','text','text','text','text','timestamp with time zone',
          'timestamp with time zone','text','text','text','numeric','numeric',
          'numeric','numeric','numeric','bigint','numeric','text','text','text',
          'text','text','text','text','text','text','text','jsonb',
          'timestamp with time zone'
        ]::text[])
      ) expected(table_name, column_count, column_names, column_types)
      LEFT JOIN pg_class table_object
        ON table_object.oid = to_regclass(
          'atom_research_history.' || expected.table_name
        )
      WHERE table_object.oid IS NULL
        OR table_object.relkind <> 'r'
        OR table_object.relpersistence <> 'p'
        OR table_object.relowner <> 'postgres'::regrole
        OR NOT table_object.relrowsecurity
        OR NOT table_object.relforcerowsecurity
        OR table_object.relhasrules
        OR (SELECT count(*) FROM pg_attribute column_object
            WHERE column_object.attrelid = table_object.oid
              AND column_object.attnum > 0
              AND NOT column_object.attisdropped) <> expected.column_count
        OR (SELECT array_agg(column_object.attname::text
                            ORDER BY column_object.attnum)
            FROM pg_attribute column_object
            WHERE column_object.attrelid = table_object.oid
              AND column_object.attnum > 0
              AND NOT column_object.attisdropped) <> expected.column_names
        OR (SELECT array_agg(
                     format_type(column_object.atttypid,
                                 column_object.atttypmod)
                     ORDER BY column_object.attnum)
            FROM pg_attribute column_object
            WHERE column_object.attrelid = table_object.oid
              AND column_object.attnum > 0
              AND NOT column_object.attisdropped) <> expected.column_types
    )
    OR EXISTS (
      SELECT 1
      FROM pg_attribute column_object
      JOIN pg_class table_object
        ON table_object.oid = column_object.attrelid
      JOIN pg_namespace schema ON schema.oid = table_object.relnamespace
      WHERE schema.nspname = 'atom_research_history'
        AND table_object.relname IN ('raw_responses','manifests','bars')
        AND column_object.attnum > 0
        AND column_object.attisdropped
    )
    OR EXISTS (
      SELECT 1
      FROM pg_rewrite rewrite_object
      JOIN pg_class table_object
        ON table_object.oid = rewrite_object.ev_class
      JOIN pg_namespace schema ON schema.oid = table_object.relnamespace
      WHERE schema.nspname = 'atom_research_history'
        AND table_object.relname IN ('raw_responses','manifests','bars')
    )
    OR EXISTS (
      SELECT 1
      FROM pg_inherits inheritance
      WHERE inheritance.inhrelid IN (
              to_regclass('atom_research_history.raw_responses'),
              to_regclass('atom_research_history.manifests'),
              to_regclass('atom_research_history.bars')
            )
         OR inheritance.inhparent IN (
              to_regclass('atom_research_history.raw_responses'),
              to_regclass('atom_research_history.manifests'),
              to_regclass('atom_research_history.bars')
            )
    )
  THEN
    RAISE EXCEPTION 'HIST8_EXISTING_INSTALLATION_TABLE_MISMATCH';
  END IF;

  IF (SELECT count(*)
      FROM pg_proc routine
      JOIN pg_namespace schema ON schema.oid = routine.pronamespace
      WHERE schema.nspname = 'atom_research_history') <> 2
    OR EXISTS (
      SELECT 1
      FROM (VALUES
        ('reject_mutation', 'HIST8 evidence is append-only'),
        ('guard_snapshot_membership', 'HIST8 import evidence is sealed')
      ) expected(routine_name, required_source)
      LEFT JOIN pg_proc routine
        ON routine.oid = to_regprocedure(
          'atom_research_history.' || expected.routine_name || '()'
        )
      WHERE routine.oid IS NULL
        OR routine.proowner <> 'postgres'::regrole
        OR routine.pronargs <> 0
        OR routine.prorettype <> 'pg_catalog.trigger'::regtype
        OR routine.prosecdef
        OR routine.proconfig IS DISTINCT FROM ARRAY['search_path=pg_catalog']
        OR position(expected.required_source in routine.prosrc) = 0
    )
  THEN
    RAISE EXCEPTION 'HIST8_EXISTING_INSTALLATION_ROUTINE_MISMATCH';
  END IF;

  IF (SELECT count(*)
      FROM pg_trigger trigger_object
      JOIN pg_class table_object ON table_object.oid = trigger_object.tgrelid
      JOIN pg_namespace schema ON schema.oid = table_object.relnamespace
      WHERE schema.nspname = 'atom_research_history'
        AND NOT trigger_object.tgisinternal) <> 7
    OR EXISTS (
      SELECT 1
      FROM (VALUES
        ('hist8_raw_reject_update_delete','raw_responses','reject_mutation',27),
        ('hist8_raw_reject_truncate','raw_responses','reject_mutation',34),
        ('hist8_manifests_reject_update_delete','manifests','reject_mutation',27),
        ('hist8_manifests_reject_truncate','manifests','reject_mutation',34),
        ('hist8_snapshot_membership_guard','manifests','guard_snapshot_membership',7),
        ('hist8_bars_reject_update_delete','bars','reject_mutation',27),
        ('hist8_bars_reject_truncate','bars','reject_mutation',34)
      ) expected(trigger_name, table_name, routine_name, trigger_type)
      LEFT JOIN pg_trigger trigger_object
        ON trigger_object.tgname = expected.trigger_name
       AND trigger_object.tgrelid = to_regclass(
         'atom_research_history.' || expected.table_name
       )
      WHERE trigger_object.oid IS NULL
        OR trigger_object.tgfoid <> to_regprocedure(
          'atom_research_history.' || expected.routine_name || '()'
        )
        OR trigger_object.tgtype <> expected.trigger_type
        OR trigger_object.tgenabled <> 'O'
    )
  THEN
    RAISE EXCEPTION 'HIST8_EXISTING_INSTALLATION_TRIGGER_MISMATCH';
  END IF;

  IF (SELECT count(*)
      FROM pg_policy policy
      JOIN pg_class table_object ON table_object.oid = policy.polrelid
      JOIN pg_namespace schema ON schema.oid = table_object.relnamespace
      WHERE schema.nspname = 'atom_research_history') <> 6
    OR EXISTS (
      SELECT 1
      FROM (VALUES
        ('hist8_raw_importer_select','raw_responses','r'),
        ('hist8_raw_importer_insert','raw_responses','a'),
        ('hist8_manifests_importer_select','manifests','r'),
        ('hist8_manifests_importer_insert','manifests','a'),
        ('hist8_bars_importer_select','bars','r'),
        ('hist8_bars_importer_insert','bars','a')
      ) expected(policy_name, table_name, policy_command)
      LEFT JOIN pg_policy policy
        ON policy.polname = expected.policy_name
       AND policy.polrelid = to_regclass(
         'atom_research_history.' || expected.table_name
       )
      WHERE policy.oid IS NULL
        OR policy.polcmd <> expected.policy_command::"char"
        OR NOT policy.polpermissive
        OR policy.polroles <> ARRAY[
          (SELECT oid FROM pg_roles WHERE rolname = 'atom_hist8_importer')
        ]
        OR (expected.policy_command = 'r' AND (
          pg_get_expr(policy.polqual, policy.polrelid) IS DISTINCT FROM 'true'
          OR policy.polwithcheck IS NOT NULL
        ))
        OR (expected.policy_command = 'a' AND (
          pg_get_expr(policy.polwithcheck, policy.polrelid)
            IS DISTINCT FROM 'true'
          OR policy.polqual IS NOT NULL
        ))
    )
  THEN
    RAISE EXCEPTION 'HIST8_EXISTING_INSTALLATION_POLICY_MISMATCH';
  END IF;

  IF protection_signature IS NULL
    OR routine_signature IS NULL
    OR column_signature IS NULL
    OR index_signature IS NULL
    OR trigger_signature IS NULL
    OR (SELECT obj_description(schema.oid, 'pg_namespace')
        FROM pg_namespace schema
        WHERE schema.nspname = 'atom_research_history')
       IS DISTINCT FROM
         'ATOM-HIST8-CORPUS-AMENDMENT-1:INSTALLATION-V1:'
           || protection_signature || ':' || routine_signature
           || ':' || column_signature || ':' || index_signature
           || ':' || trigger_signature
    OR EXISTS (
    SELECT 1
    FROM (VALUES
      ('hist8_bars_snapshot_scan_idx','bars'),
      ('hist8_bars_session_lookup_idx','bars'),
      ('hist8_manifests_import_idx','manifests')
    ) expected(index_name, table_name)
    LEFT JOIN pg_class index_object
      ON index_object.oid = to_regclass(
        'atom_research_history.' || expected.index_name
      )
    LEFT JOIN pg_index index_metadata
      ON index_metadata.indexrelid = index_object.oid
    WHERE index_object.oid IS NULL
      OR index_object.relkind <> 'i'
      OR index_metadata.indrelid <> to_regclass(
        'atom_research_history.' || expected.table_name
      )
      OR NOT index_metadata.indisvalid OR NOT index_metadata.indisready
  ) OR EXISTS (
    SELECT 1
    FROM (VALUES
      ('hist8_raw_length_matches','raw_responses','c'),
      ('hist8_retrieval_artifact_required','manifests','c'),
      ('hist8_snapshot_member_required','manifests','c'),
      ('hist8_snapshot_member_bar_fk','manifests','f'),
      ('hist8_bar_interval','bars','c'),
      ('hist8_bar_duration','bars','c'),
      ('hist8_bar_ohlc','bars','c'),
      ('hist8_bar_volume_semantics','bars','c'),
      ('hist8_bar_lineage','bars','c'),
      ('hist8_bar_identity_pair','bars','u')
    ) expected(constraint_name, table_name, constraint_type)
    LEFT JOIN pg_constraint constraint_object
      ON constraint_object.conname = expected.constraint_name
     AND constraint_object.conrelid = to_regclass(
       'atom_research_history.' || expected.table_name
     )
    WHERE constraint_object.oid IS NULL
      OR constraint_object.contype <> expected.constraint_type::"char"
      OR NOT constraint_object.convalidated
  ) THEN
    RAISE EXCEPTION 'HIST8_EXISTING_INSTALLATION_PROTECTION_MISMATCH';
  END IF;

  IF NOT has_database_privilege('atom_hist8_importer', current_database(), 'CONNECT')
    OR NOT has_schema_privilege(
      'atom_hist8_importer', 'atom_research_history', 'USAGE'
    )
    OR has_schema_privilege(
      'atom_hist8_importer', 'atom_research_history', 'CREATE'
    )
    OR EXISTS (
      SELECT 1 FROM pg_database
      WHERE datname = current_database()
        AND datdba = (SELECT oid FROM pg_roles WHERE rolname = 'atom_hist8_importer')
    )
    OR EXISTS (
      SELECT 1 FROM pg_namespace
      WHERE nspowner = (SELECT oid FROM pg_roles WHERE rolname = 'atom_hist8_importer')
    )
    OR EXISTS (
      SELECT 1 FROM pg_class
      WHERE relowner = (SELECT oid FROM pg_roles WHERE rolname = 'atom_hist8_importer')
    )
  THEN
    RAISE EXCEPTION 'HIST8_ROLE_OWNERSHIP_OR_BASE_PRIVILEGE_MISMATCH';
  END IF;

  IF has_database_privilege(
       'atom_hist8_importer', current_database(), 'CREATE'
     )
    OR has_database_privilege(
       'atom_hist8_importer', current_database(), 'TEMPORARY'
     )
  THEN
    RAISE EXCEPTION 'HIST8_DATABASE_PRIVILEGE_BOUNDARY_UNSATISFIED';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM pg_database d
    WHERE d.datname <> current_database()
      AND d.datallowconn
      AND has_database_privilege(
        'atom_hist8_importer', d.oid, 'CONNECT'
      )
  ) THEN
    RAISE EXCEPTION 'HIST8_OTHER_DATABASE_CONNECT_BOUNDARY_UNSATISFIED';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM (VALUES ('raw_responses'), ('manifests'), ('bars')) expected(table_name)
    WHERE NOT has_table_privilege(
        'atom_hist8_importer', 'atom_research_history.' || expected.table_name,
        'SELECT'
      )
      OR NOT has_table_privilege(
        'atom_hist8_importer', 'atom_research_history.' || expected.table_name,
        'INSERT'
      )
      OR has_table_privilege(
        'atom_hist8_importer', 'atom_research_history.' || expected.table_name,
        'UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
      )
  ) THEN
    RAISE EXCEPTION 'HIST8_TABLE_PRIVILEGE_MISMATCH';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    CROSS JOIN LATERAL aclexplode(
      COALESCE(c.relacl, acldefault('r', c.relowner))
    ) acl
    WHERE n.nspname = 'atom_research_history'
      AND c.relname IN ('raw_responses', 'manifests', 'bars')
      -- OID 0 is PUBLIC. Every other non-owner/non-importer grantee is also
      -- forbidden, including custom roles inherited from default privileges.
      AND acl.grantee NOT IN (
        c.relowner,
        (SELECT oid FROM pg_roles WHERE rolname = 'atom_hist8_importer')
      )
  ) THEN
    RAISE EXCEPTION 'HIST8_FOREIGN_ROLE_ACCESS_BOUNDARY_UNSATISFIED';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM pg_namespace n
    CROSS JOIN LATERAL aclexplode(
      COALESCE(n.nspacl, acldefault('n', n.nspowner))
    ) acl
    WHERE n.nspname = 'atom_research_history'
      AND acl.grantee NOT IN (
        n.nspowner,
        (SELECT oid FROM pg_roles WHERE rolname = 'atom_hist8_importer')
      )
  ) THEN
    RAISE EXCEPTION 'HIST8_FOREIGN_SCHEMA_ACCESS_BOUNDARY_UNSATISFIED';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind IN ('r','p','v','m','f')
      AND n.nspname NOT IN (
        'pg_catalog','information_schema','atom_research_history'
      )
      AND (has_table_privilege('atom_hist8_importer', c.oid, 'SELECT')
        OR has_table_privilege('atom_hist8_importer', c.oid, 'INSERT')
        OR has_table_privilege('atom_hist8_importer', c.oid, 'UPDATE')
        OR has_table_privilege('atom_hist8_importer', c.oid, 'DELETE')
        OR has_table_privilege('atom_hist8_importer', c.oid, 'TRUNCATE')
        OR has_table_privilege('atom_hist8_importer', c.oid, 'REFERENCES')
        OR has_table_privilege('atom_hist8_importer', c.oid, 'TRIGGER'))
  ) THEN
    RAISE EXCEPTION 'HIST8_EFFECTIVE_PRIVILEGE_BOUNDARY_UNSATISFIED';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind IN ('r','p','v','m','f')
      AND n.nspname NOT IN (
        'pg_catalog','information_schema','atom_research_history'
      )
      AND has_any_column_privilege(
        'atom_hist8_importer', c.oid, 'SELECT,INSERT,UPDATE,REFERENCES'
      )
  ) THEN
    RAISE EXCEPTION 'HIST8_EFFECTIVE_COLUMN_PRIVILEGE_BOUNDARY_UNSATISFIED';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind = 'S'
      AND n.nspname NOT IN (
        'pg_catalog','information_schema','atom_research_history'
      )
      AND n.nspname NOT LIKE 'pg_toast%'
      AND n.nspname NOT LIKE 'pg_temp_%'
      AND has_schema_privilege('atom_hist8_importer', n.oid, 'USAGE')
      AND (has_sequence_privilege('atom_hist8_importer', c.oid, 'USAGE')
        OR has_sequence_privilege('atom_hist8_importer', c.oid, 'SELECT')
        OR has_sequence_privilege('atom_hist8_importer', c.oid, 'UPDATE'))
  ) THEN
    RAISE EXCEPTION 'HIST8_EFFECTIVE_SEQUENCE_BOUNDARY_UNSATISFIED';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname NOT IN ('pg_catalog','information_schema')
      AND n.nspname NOT LIKE 'pg_toast%'
      AND n.nspname NOT LIKE 'pg_temp_%'
      AND has_schema_privilege('atom_hist8_importer', n.oid, 'USAGE')
      -- Trigger/event-trigger routines cannot be invoked directly. Their ACLs
      -- convey no capability because the importer has no DML/DDL on their hosts.
      AND p.prorettype NOT IN (
        'pg_catalog.trigger'::regtype, 'pg_catalog.event_trigger'::regtype
      )
      AND has_function_privilege('atom_hist8_importer', p.oid, 'EXECUTE')
  ) THEN
    RAISE EXCEPTION 'HIST8_EFFECTIVE_ROUTINE_BOUNDARY_UNSATISFIED';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM pg_namespace n
    WHERE n.nspname NOT IN (
        'pg_catalog','information_schema','public','atom_research_history'
      )
      AND n.nspname NOT LIKE 'pg_toast%'
      AND n.nspname NOT LIKE 'pg_temp_%'
      AND has_schema_privilege('atom_hist8_importer', n.oid, 'USAGE')
  ) THEN
    RAISE EXCEPTION 'HIST8_EFFECTIVE_SCHEMA_USAGE_BOUNDARY_UNSATISFIED';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM pg_largeobject_metadata object
    CROSS JOIN LATERAL aclexplode(
      COALESCE(object.lomacl, acldefault('L', object.lomowner))
    ) acl
    WHERE acl.grantee IN (
        0, (SELECT oid FROM pg_roles WHERE rolname = 'atom_hist8_importer')
      )
      AND acl.privilege_type IN ('SELECT', 'UPDATE')
  ) THEN
    RAISE EXCEPTION 'HIST8_EFFECTIVE_LARGE_OBJECT_BOUNDARY_UNSATISFIED';
  END IF;

  -- A long-lived importer must not gain access when a legacy owner later
  -- creates a table in any schema the importer can use. PostgreSQL relation
  -- defaults are global plus schema-specific, so inspect both without
  -- rewriting any unrelated owner's defaults.
  IF EXISTS (
    SELECT 1
    FROM pg_namespace n
    JOIN pg_roles creator ON (
      creator.rolsuper
      OR creator.oid = n.nspowner
      OR has_schema_privilege(creator.oid, n.oid, 'CREATE')
    )
    LEFT JOIN pg_default_acl global_defaults
      ON global_defaults.defaclrole = creator.oid
     AND global_defaults.defaclnamespace = 0
     AND global_defaults.defaclobjtype = 'r'
    LEFT JOIN pg_default_acl schema_defaults
      ON schema_defaults.defaclrole = creator.oid
     AND schema_defaults.defaclnamespace = n.oid
     AND schema_defaults.defaclobjtype = 'r'
    WHERE n.nspname NOT IN ('pg_catalog','information_schema')
      AND n.nspname NOT LIKE 'pg_toast%'
      AND n.nspname NOT LIKE 'pg_temp_%'
      AND has_schema_privilege(
        'atom_hist8_importer', n.oid, 'USAGE'
      )
      AND (
        EXISTS (
          SELECT 1
          FROM unnest(COALESCE(
            global_defaults.defaclacl,
            acldefault('r', creator.oid)
          )) entry(aclitem)
          CROSS JOIN LATERAL aclexplode(ARRAY[entry.aclitem]) acl
          WHERE acl.grantee IN (
              0,
              (SELECT oid FROM pg_roles
               WHERE rolname = 'atom_hist8_importer')
            )
            AND acl.privilege_type IN (
              'SELECT','INSERT','UPDATE','DELETE','TRUNCATE',
              'REFERENCES','TRIGGER'
            )
        )
        OR EXISTS (
          SELECT 1
          FROM unnest(schema_defaults.defaclacl) entry(aclitem)
          CROSS JOIN LATERAL aclexplode(ARRAY[entry.aclitem]) acl
          WHERE acl.grantee IN (
              0,
              (SELECT oid FROM pg_roles
               WHERE rolname = 'atom_hist8_importer')
            )
            AND acl.privilege_type IN (
              'SELECT','INSERT','UPDATE','DELETE','TRUNCATE',
              'REFERENCES','TRIGGER'
            )
        )
      )
  ) THEN
    RAISE EXCEPTION
      'HIST8_FUTURE_TABLE_DEFAULT_BOUNDARY_UNSATISFIED';
  END IF;

  -- Ownership itself grants durable access. Reject any catalog routine the
  -- importer can execute that creates a new large object, because that object
  -- would fall outside the three-table HIST8 boundary after this check ends.
  IF EXISTS (
    SELECT 1
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'pg_catalog'
      AND p.proname IN (
        'lo_creat', 'lo_create', 'lo_from_bytea', 'lo_import'
      )
      AND has_function_privilege(
        'atom_hist8_importer', p.oid, 'EXECUTE'
      )
  ) THEN
    RAISE EXCEPTION
      'HIST8_EFFECTIVE_LARGE_OBJECT_CREATE_BOUNDARY_UNSATISFIED';
  END IF;

  -- PostgreSQL grants EXECUTE on new routines to PUBLIC by default. Require
  -- every role that can create in a schema visible to the importer to have a
  -- non-PUBLIC routine default, so later legacy DDL cannot silently expand the
  -- long-lived credential. This verifier reports BLOCKED; it does not rewrite
  -- any unrelated owner's default privileges.
  IF EXISTS (
    SELECT 1
    FROM pg_namespace n
    JOIN pg_roles creator ON (
      creator.rolsuper
      OR creator.oid = n.nspowner
      OR has_schema_privilege(creator.oid, n.oid, 'CREATE')
    )
    LEFT JOIN pg_default_acl global_defaults
      ON global_defaults.defaclrole = creator.oid
     AND global_defaults.defaclnamespace = 0
     AND global_defaults.defaclobjtype = 'f'
    LEFT JOIN pg_default_acl schema_defaults
      ON schema_defaults.defaclrole = creator.oid
     AND schema_defaults.defaclnamespace = n.oid
     AND schema_defaults.defaclobjtype = 'f'
    WHERE n.nspname NOT IN ('pg_catalog','information_schema')
      AND n.nspname NOT LIKE 'pg_toast%'
      AND n.nspname NOT LIKE 'pg_temp_%'
      AND has_schema_privilege(
        'atom_hist8_importer', n.oid, 'USAGE'
      )
      AND (
        EXISTS (
          SELECT 1
          FROM unnest(COALESCE(
            global_defaults.defaclacl,
            acldefault('f', creator.oid)
          )) entry(aclitem)
          CROSS JOIN LATERAL aclexplode(ARRAY[entry.aclitem]) acl
          WHERE acl.grantee = 0 AND acl.privilege_type = 'EXECUTE'
        )
        OR EXISTS (
          SELECT 1
          FROM unnest(schema_defaults.defaclacl) entry(aclitem)
          CROSS JOIN LATERAL aclexplode(ARRAY[entry.aclitem]) acl
          WHERE acl.grantee = 0 AND acl.privilege_type = 'EXECUTE'
        )
      )
  ) THEN
    RAISE EXCEPTION
      'HIST8_FUTURE_ROUTINE_DEFAULT_BOUNDARY_UNSATISFIED';
  END IF;

  IF EXISTS (
    SELECT 1 FROM pg_namespace n
    WHERE n.nspname NOT LIKE 'pg_temp_%'
      AND has_schema_privilege('atom_hist8_importer', n.oid, 'CREATE')
  ) THEN
    RAISE EXCEPTION 'HIST8_EFFECTIVE_SCHEMA_CREATE_BOUNDARY_UNSATISFIED';
  END IF;
END
$hist8_verify$;

COMMIT;
