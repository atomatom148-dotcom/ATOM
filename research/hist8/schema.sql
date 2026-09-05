-- ATOM-HIST8-CORPUS-AMENDMENT-1
-- Isolated installation only: pjbjpgnmniwcajqkuhge / postgres.

SET lock_timeout = '5s';
SET statement_timeout = '60s';

DO $hist8$
BEGIN
  IF current_database() <> 'postgres' THEN
    RAISE EXCEPTION 'HIST8_PROJECT_MISMATCH: database %', current_database();
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'atom_hist8_importer') THEN
    CREATE ROLE atom_hist8_importer
      LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE
      NOREPLICATION NOBYPASSRLS;
  ELSIF EXISTS (
    SELECT 1 FROM pg_roles
    WHERE rolname = 'atom_hist8_importer'
      AND (rolsuper OR rolinherit OR rolcreaterole OR rolcreatedb
           OR rolreplication OR rolbypassrls OR NOT rolcanlogin)
  ) THEN
    RAISE EXCEPTION 'HIST8_ROLE_MISMATCH';
  END IF;

  IF EXISTS (
    SELECT 1 FROM pg_auth_members m
    JOIN pg_roles member_role ON member_role.oid = m.member
    WHERE member_role.rolname = 'atom_hist8_importer'
  ) THEN
    RAISE EXCEPTION 'HIST8_ROLE_MEMBERSHIP_MISMATCH';
  END IF;
END
$hist8$;

CREATE SCHEMA IF NOT EXISTS atom_research_history AUTHORIZATION postgres;
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
    CHECK (manifest_kind IN ('RETRIEVAL', 'IMPORT_ATTEMPT', 'REPLAY_ATTEMPT', 'SNAPSHOT')),
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
  metadata_json jsonb NOT NULL CHECK (jsonb_typeof(metadata_json) = 'object'),
  created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT hist8_retrieval_artifact_required CHECK (
    manifest_kind <> 'RETRIEVAL'
    OR (source IS NOT NULL AND feed IS NOT NULL AND product IS NOT NULL
        AND endpoint IS NOT NULL AND retrieved_at IS NOT NULL
        AND http_status IS NOT NULL AND artifact_id IS NOT NULL
        AND artifact_byte_length IS NOT NULL)
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
  research_eligible boolean NOT NULL,
  created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT hist8_bar_interval CHECK (bar_end_utc > bar_start_utc),
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

CREATE INDEX hist8_bars_snapshot_scan_idx
  ON atom_research_history.bars (corpus_id, instrument, timeframe, bar_start_utc);
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

DO $hist8_verify$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind IN ('r','p','v','m','f')
      AND n.nspname NOT IN ('pg_catalog','information_schema','atom_research_history')
      AND (has_table_privilege('atom_hist8_importer', c.oid, 'SELECT')
        OR has_table_privilege('atom_hist8_importer', c.oid, 'INSERT')
        OR has_table_privilege('atom_hist8_importer', c.oid, 'UPDATE')
        OR has_table_privilege('atom_hist8_importer', c.oid, 'DELETE')
        OR has_table_privilege('atom_hist8_importer', c.oid, 'TRUNCATE'))
  ) THEN
    RAISE EXCEPTION 'HIST8_EFFECTIVE_PRIVILEGE_BOUNDARY_UNSATISFIED';
  END IF;
END
$hist8_verify$;
