-- Standalone bootstrap for the isolated ATOM TRUE V9 simulator project.
--
-- The operator supplies atom_v9.sim_project_ref with SET LOCAL in the same
-- explicit transaction that executes this file.  This migration intentionally
-- contains no transaction-control statement.

DO $atom_v9_sim_refusal_gate$
DECLARE
    configured_project_ref text;
BEGIN
    configured_project_ref :=
        pg_catalog.current_setting('atom_v9.sim_project_ref', true);

    IF configured_project_ref IS NULL
       OR configured_project_ref !~ '^[a-z0-9]{20}$' THEN
        RAISE EXCEPTION USING
            ERRCODE = '22023',
            MESSAGE = 'atom_v9.sim_project_ref must be a same-transaction lowercase 20-character project ref';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class AS relation
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = 'public'
          AND relation.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '55000',
            MESSAGE = 'public contains a pre-existing user relation; refusing simulator bootstrap';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_namespace AS namespace
        WHERE namespace.nspname ~ '^atom_'
          AND namespace.nspname !~ '^pg_'
          AND namespace.nspname <> 'information_schema'
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '55000',
            MESSAGE = 'an atom_ application schema already exists; refusing simulator bootstrap';
    END IF;

    IF EXISTS (SELECT 1 FROM pg_catalog.pg_foreign_data_wrapper)
       OR EXISTS (SELECT 1 FROM pg_catalog.pg_foreign_server)
       OR EXISTS (SELECT 1 FROM pg_catalog.pg_user_mapping)
       OR EXISTS (SELECT 1 FROM pg_catalog.pg_foreign_table) THEN
        RAISE EXCEPTION USING
            ERRCODE = '55000',
            MESSAGE = 'a foreign-data object exists; refusing simulator bootstrap';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_roles AS db_role
        WHERE db_role.rolname IN (
            'atom_v9_sim_owner',
            'atom_v9_sim_runtime',
            'atom_v9_sim_entry_runtime'
        )
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '42710',
            MESSAGE = 'a simulator target role already exists; refusing to adopt it';
    END IF;

    -- Refuse every migration-owned name in every schema.  The prefix also
    -- catches an earlier or partial simulator installation not visible in
    -- public.
    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class AS rel
        WHERE rel.relname ~ '^atom_v9_sim'
    )
       OR EXISTS (
        SELECT 1
        FROM pg_catalog.pg_proc AS proc
        WHERE proc.proname ~ '^atom_v9_sim'
    )
       OR EXISTS (
        SELECT 1
        FROM pg_catalog.pg_trigger AS trg
        WHERE NOT trg.tgisinternal
          AND trg.tgname ~ '^atom_v9_sim'
    )
       OR EXISTS (
        SELECT 1
        FROM pg_catalog.pg_policy AS pol
        WHERE pol.polname ~ '^atom_v9_sim'
    )
       OR EXISTS (
        SELECT 1
        FROM pg_catalog.pg_type AS typ
        WHERE typ.typname ~ '^atom_v9_sim'
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '42710',
            MESSAGE = 'a simulator target object already exists; refusing to adopt it';
    END IF;

    -- Supabase-managed schemas are not application data planes.  Everywhere
    -- else, a production-shaped schema/object/role is a hard refusal.
    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_namespace AS nsp
        WHERE nsp.nspname !~ '^pg_'
          AND nsp.nspname <> 'information_schema'
          AND nsp.nspname NOT IN (
              'auth', 'extensions', 'graphql', 'graphql_public', 'net',
              'pgsodium', 'pgsodium_masks', 'realtime', 'storage',
              'supabase_functions', 'vault'
          )
          AND nsp.nspname ~* '(^|_)(atom|v9|prod|production|forecast|outcome|evidence|state|benchmark|archive)(_|$)'
    )
       OR EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class AS rel
        JOIN pg_catalog.pg_namespace AS nsp
          ON nsp.oid = rel.relnamespace
        WHERE nsp.nspname !~ '^pg_'
          AND nsp.nspname <> 'information_schema'
          AND nsp.nspname NOT IN (
              'auth', 'extensions', 'graphql', 'graphql_public', 'net',
              'pgsodium', 'pgsodium_masks', 'realtime', 'storage',
              'supabase_functions', 'vault'
          )
          AND rel.relname ~* '(^|_)(atom|v9|forecast|forecasts|outcome|outcomes|evidence|state|states|benchmark|archive)(_|$)'
    )
       OR EXISTS (
        SELECT 1
        FROM pg_catalog.pg_proc AS proc
        JOIN pg_catalog.pg_namespace AS nsp
          ON nsp.oid = proc.pronamespace
        WHERE nsp.nspname !~ '^pg_'
          AND nsp.nspname <> 'information_schema'
          AND nsp.nspname NOT IN (
              'auth', 'extensions', 'graphql', 'graphql_public', 'net',
              'pgsodium', 'pgsodium_masks', 'realtime', 'storage',
              'supabase_functions', 'vault'
          )
          AND proc.proname ~* '(^|_)(atom|v9|forecast|forecasts|outcome|outcomes|evidence|state|states|benchmark|archive)(_|$)'
    )
       OR EXISTS (
        SELECT 1
        FROM pg_catalog.pg_roles AS db_role
        WHERE db_role.rolname ~* '^(atom_v9_|v9_|forecast_|outcome_|evidence_|benchmark_|archive_)'
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '55000',
            MESSAGE = 'a production-shaped object or role exists; refusing simulator bootstrap';
    END IF;
END
$atom_v9_sim_refusal_gate$;

CREATE ROLE atom_v9_sim_owner WITH
    NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOREPLICATION NOBYPASSRLS;

CREATE ROLE atom_v9_sim_runtime WITH
    LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOREPLICATION NOBYPASSRLS;

CREATE ROLE atom_v9_sim_entry_runtime WITH
    LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOREPLICATION NOBYPASSRLS;

-- Supabase's administrative postgres role is intentionally not a superuser.
-- PostgreSQL therefore requires temporary SET ROLE authority for the
-- migration executor before ownership can move to the NOLOGIN owner.  The
-- owner's temporary schema-CREATE privilege and all usable SET/INHERIT
-- membership are removed below, inside the same operator-owned transaction.
-- Supabase PostgreSQL 17 retains one platform-managed, ADMIN-only catalog
-- grant from supabase_admin for each role created by its postgres executor.
-- The final authority check permits only those exact inert artifacts and
-- rejects every usable or unrelated grant.
DO $atom_v9_sim_grant_bootstrap_owner$
BEGIN
    EXECUTE pg_catalog.format(
        'GRANT atom_v9_sim_owner TO %I',
        CURRENT_USER
    );
END
$atom_v9_sim_grant_bootstrap_owner$;

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL PRIVILEGES ON SCHEMA public
FROM atom_v9_sim_owner, atom_v9_sim_runtime, atom_v9_sim_entry_runtime;
GRANT USAGE ON SCHEMA public
TO atom_v9_sim_owner, atom_v9_sim_runtime, atom_v9_sim_entry_runtime;
GRANT CREATE ON SCHEMA public TO atom_v9_sim_owner;

CREATE TABLE public.atom_v9_sim_installation (
    installation_id text PRIMARY KEY
        CONSTRAINT atom_v9_sim_installation_id_check
        CHECK (installation_id = 'ATOM_TRUE_V9_SIM_INSTALLATION_1'),
    project_ref text UNIQUE NOT NULL
        CONSTRAINT atom_v9_sim_installation_project_ref_check
        CHECK (project_ref ~ '^[a-z0-9]{20}$'),
    created_at timestamptz NOT NULL DEFAULT transaction_timestamp()
);

INSERT INTO public.atom_v9_sim_installation (
    installation_id,
    project_ref
)
VALUES (
    'ATOM_TRUE_V9_SIM_INSTALLATION_1',
    pg_catalog.current_setting('atom_v9.sim_project_ref', true)
);

-- Migration 010 is deliberately not replayed.  Its exact intent relation is
-- reproduced here for the clean simulator project.
CREATE TABLE public.atom_v9_sim_intents (
    intent_id text PRIMARY KEY CHECK (intent_id ~ '^v9simintent:[0-9a-f]{64}$'),
    intent_hash text UNIQUE NOT NULL CHECK (intent_hash ~ '^[0-9a-f]{64}$'),
    contract_version text NOT NULL CHECK (contract_version = 'ATOM_TRUE_V9_SIM1_INTENT_1'),
    canonicalization_version text NOT NULL CHECK (canonicalization_version = 'ATOM_TRUE_V9_SIM_CANONICAL_V4A_1'),
    simulator_version text NOT NULL CHECK (simulator_version = 'ATOM_TRUE_V9_SIM_1'),
    symbol text NOT NULL CHECK (symbol = 'COIN'),
    horizon text NOT NULL,
    horizon_seconds integer NOT NULL,
    cutoff_at timestamptz NOT NULL,
    eligible_at timestamptz NOT NULL,
    source_v3_status text NOT NULL CHECK (source_v3_status IN ('AVAILABLE', 'PROVISIONAL', 'UNAVAILABLE')),
    decision text NOT NULL CHECK (decision IN ('LONG', 'SHORT', 'NO_TRADE')),
    status text NOT NULL CHECK (status IN ('ACTIONABLE', 'NO_TRADE', 'UNAVAILABLE')),
    record_json jsonb NOT NULL CHECK (jsonb_typeof(record_json) = 'object'),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((horizon, horizon_seconds) IN
        (('30S', 30), ('1M', 60), ('5M', 300), ('15M', 900),
         ('30M', 1800), ('1H', 3600))),
    CHECK (eligible_at >= cutoff_at)
);

CREATE INDEX atom_v9_sim_intents_lookup_idx
ON public.atom_v9_sim_intents (symbol, horizon, eligible_at, intent_id);

CREATE SEQUENCE public.atom_v9_sim4_intent_admission_seq
    AS bigint
    INCREMENT BY 1
    MINVALUE 1
    START WITH 1
    CACHE 1
    NO CYCLE;

CREATE TABLE public.atom_v9_sim_intent_publications (
    publication_seq bigint PRIMARY KEY CHECK (publication_seq > 0),
    intent_id text UNIQUE NOT NULL
        REFERENCES public.atom_v9_sim_intents (intent_id) ON DELETE RESTRICT,
    publication_at timestamptz NOT NULL,
    horizon_order smallint NOT NULL CHECK (horizon_order BETWEEN 1 AND 6)
);

CREATE INDEX atom_v9_sim_intent_publications_semantic_idx
ON public.atom_v9_sim_intent_publications
    (publication_at, horizon_order, intent_id, publication_seq);

CREATE TABLE public.atom_v9_sim_entries (
    entry_id text PRIMARY KEY,
    entry_hash text UNIQUE NOT NULL,
    contract_version text NOT NULL,
    canonicalization_version text NOT NULL,
    simulator_version text NOT NULL,
    symbol text NOT NULL,
    horizon text NOT NULL,
    horizon_seconds integer NOT NULL,
    intent_id text UNIQUE NOT NULL,
    publication_at timestamptz NOT NULL,
    entry_deadline_at timestamptz NOT NULL,
    decision text NOT NULL,
    intent_status text NOT NULL,
    entry_status text NOT NULL,
    quantity_shares integer NOT NULL,
    blocking_entry_id text NULL,
    quote_id text NULL,
    quote_hash text NULL,
    quote_source_spec text NULL,
    quote_event_ns bigint NULL,
    quote_accepted_at timestamptz NULL,
    entry_price double precision NULL,
    record_json jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT atom_v9_sim_entries_entry_identity_check CHECK (
        entry_hash ~ '^[0-9a-f]{64}$'
        AND entry_id = 'v9simentry:' || entry_hash
    ),
    CONSTRAINT atom_v9_sim_entries_contract_check CHECK (
        contract_version = 'ATOM_TRUE_V9_SIM4_ENTRY_1'
        AND canonicalization_version = 'ATOM_TRUE_V9_SIM_CANONICAL_V4A_1'
        AND simulator_version = 'ATOM_TRUE_V9_SIM_1'
        AND symbol = 'COIN'
    ),
    CONSTRAINT atom_v9_sim_entries_horizon_check CHECK (
        (horizon, horizon_seconds) IN
        (('30S', 30), ('1M', 60), ('5M', 300), ('15M', 900),
         ('30M', 1800), ('1H', 3600))
    ),
    CONSTRAINT atom_v9_sim_entries_intent_id_check CHECK (
        intent_id ~ '^v9simintent:[0-9a-f]{64}$'
    ),
    CONSTRAINT atom_v9_sim_entries_time_check CHECK (
        publication_at NOT IN ('-infinity'::timestamptz, 'infinity'::timestamptz)
        AND entry_deadline_at = publication_at + interval '2 seconds'
    ),
    CONSTRAINT atom_v9_sim_entries_decision_check CHECK (
        decision IN ('LONG', 'SHORT', 'NO_TRADE')
    ),
    CONSTRAINT atom_v9_sim_entries_intent_status_check CHECK (
        intent_status IN ('ACTIONABLE', 'NO_TRADE', 'UNAVAILABLE')
    ),
    CONSTRAINT atom_v9_sim_entries_entry_status_check CHECK (
        entry_status IN (
            'ENTERED',
            'SKIPPED_NO_TRADE',
            'SKIPPED_UNAVAILABLE',
            'SKIPPED_POSITION_OPEN',
            'SKIPPED_WINDOW_EXPIRED',
            'SKIPPED_RESTART_GAP'
        )
    ),
    CONSTRAINT atom_v9_sim_entries_quote_identity_check CHECK (
        quote_id IS NULL
        OR (
            quote_hash ~ '^[0-9a-f]{64}$'
            AND quote_id = 'v9simquote:' || quote_hash
        )
    ),
    CONSTRAINT atom_v9_sim_entries_quote_values_check CHECK (
        quote_source_spec IS NULL
        OR quote_source_spec = 'ATOM_TRUE_V9_SIM4_ALPACA_SIP_QUOTE_1'
    ),
    CONSTRAINT atom_v9_sim_entries_quote_event_ns_check CHECK (
        quote_event_ns IS NULL OR quote_event_ns >= 0
    ),
    CONSTRAINT atom_v9_sim_entries_blocking_id_check CHECK (
        blocking_entry_id IS NULL
        OR blocking_entry_id ~ '^v9simentry:[0-9a-f]{64}$'
    ),
    CONSTRAINT atom_v9_sim_entries_record_json_check CHECK (
        jsonb_typeof(record_json) = 'object'
    ),
    CONSTRAINT atom_v9_sim_entries_status_fields_check CHECK (
        (
            entry_status = 'ENTERED'
            AND intent_status = 'ACTIONABLE'
            AND decision IN ('LONG', 'SHORT')
            AND quantity_shares = 1
            AND blocking_entry_id IS NULL
            AND quote_id IS NOT NULL
            AND quote_hash IS NOT NULL
            AND quote_source_spec = 'ATOM_TRUE_V9_SIM4_ALPACA_SIP_QUOTE_1'
            AND quote_event_ns IS NOT NULL
            AND quote_event_ns >= 0
            AND quote_accepted_at IS NOT NULL
            AND quote_accepted_at NOT IN (
                '-infinity'::timestamptz,
                'infinity'::timestamptz
            )
            AND entry_price IS NOT NULL
            AND entry_price > 0
            AND entry_price NOT IN (
                'NaN'::double precision,
                '-Infinity'::double precision,
                'Infinity'::double precision
            )
        )
        OR (
            entry_status = 'SKIPPED_NO_TRADE'
            AND intent_status = 'NO_TRADE'
            AND decision = 'NO_TRADE'
            AND quantity_shares = 0
            AND blocking_entry_id IS NULL
            AND quote_id IS NULL
            AND quote_hash IS NULL
            AND quote_source_spec IS NULL
            AND quote_event_ns IS NULL
            AND quote_accepted_at IS NULL
            AND entry_price IS NULL
        )
        OR (
            entry_status = 'SKIPPED_UNAVAILABLE'
            AND intent_status = 'UNAVAILABLE'
            AND decision = 'NO_TRADE'
            AND quantity_shares = 0
            AND blocking_entry_id IS NULL
            AND quote_id IS NULL
            AND quote_hash IS NULL
            AND quote_source_spec IS NULL
            AND quote_event_ns IS NULL
            AND quote_accepted_at IS NULL
            AND entry_price IS NULL
        )
        OR (
            entry_status = 'SKIPPED_POSITION_OPEN'
            AND intent_status = 'ACTIONABLE'
            AND decision IN ('LONG', 'SHORT')
            AND quantity_shares = 0
            AND blocking_entry_id IS NOT NULL
            AND quote_id IS NULL
            AND quote_hash IS NULL
            AND quote_source_spec IS NULL
            AND quote_event_ns IS NULL
            AND quote_accepted_at IS NULL
            AND entry_price IS NULL
        )
        OR (
            entry_status IN (
                'SKIPPED_WINDOW_EXPIRED',
                'SKIPPED_RESTART_GAP'
            )
            AND intent_status = 'ACTIONABLE'
            AND decision IN ('LONG', 'SHORT')
            AND quantity_shares = 0
            AND blocking_entry_id IS NULL
            AND quote_id IS NULL
            AND quote_hash IS NULL
            AND quote_source_spec IS NULL
            AND quote_event_ns IS NULL
            AND quote_accepted_at IS NULL
            AND entry_price IS NULL
        )
    )
);

CREATE INDEX atom_v9_sim_entries_lookup_idx
ON public.atom_v9_sim_entries
    (symbol, horizon, entry_status, publication_at, entry_id);

CREATE TABLE public.atom_v9_sim4_reconciliation_checkpoint (
    checkpoint_key text PRIMARY KEY CHECK (
        checkpoint_key = 'ATOM_TRUE_V9_SIM4_RECONCILIATION_1'
    ),
    last_completed_publication_seq bigint NOT NULL CHECK (
        last_completed_publication_seq >= 0
    ),
    checkpoint_version bigint NOT NULL CHECK (checkpoint_version >= 0),
    runtime_started_at timestamptz NULL CHECK (
        runtime_started_at IS NULL
        OR runtime_started_at NOT IN (
            '-infinity'::timestamptz,
            'infinity'::timestamptz
        )
    ),
    updated_at timestamptz NOT NULL CHECK (
        updated_at NOT IN ('-infinity'::timestamptz, 'infinity'::timestamptz)
    )
);

INSERT INTO public.atom_v9_sim4_reconciliation_checkpoint (
    checkpoint_key,
    last_completed_publication_seq,
    checkpoint_version,
    runtime_started_at,
    updated_at
)
VALUES (
    'ATOM_TRUE_V9_SIM4_RECONCILIATION_1',
    0,
    0,
    NULL,
    pg_catalog.transaction_timestamp()
);

CREATE FUNCTION public.atom_v9_sim_reject_mutation() RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $atom_v9_sim_reject_mutation$
BEGIN
    RAISE EXCEPTION USING
        ERRCODE = '55000',
        MESSAGE = 'SIM evidence is append-only';
END
$atom_v9_sim_reject_mutation$;

CREATE FUNCTION public.atom_v9_sim4_lock_intent_admission_before()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $atom_v9_sim4_lock_intent_admission_before$
BEGIN
    PERFORM pg_catalog.pg_advisory_xact_lock_shared(
        1158704842749668574::bigint
    );
    RETURN NEW;
END
$atom_v9_sim4_lock_intent_admission_before$;

CREATE FUNCTION public.atom_v9_sim4_publish_intent_after()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $atom_v9_sim4_publish_intent_after$
DECLARE
    mapped_horizon_order smallint;
    next_publication_seq bigint;
BEGIN
    mapped_horizon_order := CASE NEW.horizon
        WHEN '30S' THEN 1
        WHEN '1M' THEN 2
        WHEN '5M' THEN 3
        WHEN '15M' THEN 4
        WHEN '30M' THEN 5
        WHEN '1H' THEN 6
        ELSE NULL
    END;

    IF mapped_horizon_order IS NULL THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'invalid simulator horizon for publication';
    END IF;

    next_publication_seq := pg_catalog.nextval(
        'public.atom_v9_sim4_intent_admission_seq'::pg_catalog.regclass
    );

    INSERT INTO public.atom_v9_sim_intent_publications (
        publication_seq,
        intent_id,
        publication_at,
        horizon_order
    )
    VALUES (
        next_publication_seq,
        NEW.intent_id,
        NEW.eligible_at,
        mapped_horizon_order
    );

    RETURN NEW;
END
$atom_v9_sim4_publish_intent_after$;

CREATE FUNCTION public.atom_v9_sim4_read_intent_admission_fence()
RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $atom_v9_sim4_read_intent_admission_fence$
DECLARE
    current_fence bigint;
BEGIN
    IF SESSION_USER::text <> 'atom_v9_sim_entry_runtime' THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'SIM-4 admission-fence reader requires the entry runtime session role';
    END IF;

    SELECT CASE WHEN sequence_state.is_called
                THEN sequence_state.last_value
                ELSE 0::bigint
           END
      INTO STRICT current_fence
      FROM public.atom_v9_sim4_intent_admission_seq AS sequence_state;

    RETURN current_fence;
END
$atom_v9_sim4_read_intent_admission_fence$;

CREATE FUNCTION public.atom_v9_sim4_compare_and_advance_checkpoint(
    expected_last_completed_publication_seq bigint,
    expected_checkpoint_version bigint,
    new_last_completed_publication_seq bigint,
    capture_kind text,
    captured_publication_fence bigint,
    runtime_started_at timestamptz
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $atom_v9_sim4_compare_and_advance_checkpoint$
DECLARE
    handoff_lock_acquired boolean;
    current_publication_fence bigint;
    current_last_completed bigint;
    current_checkpoint_version bigint;
    checkpoint_updated boolean := false;
BEGIN
    IF SESSION_USER::text <> 'atom_v9_sim_entry_runtime' THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'SIM-4 checkpoint advance requires the entry runtime session role';
    END IF;

    SELECT pg_catalog.pg_try_advisory_xact_lock(
        1158704842749668574::bigint
    )
      INTO STRICT handoff_lock_acquired;

    IF handoff_lock_acquired IS DISTINCT FROM true THEN
        RETURN false;
    END IF;

    SELECT CASE WHEN sequence_state.is_called
                THEN sequence_state.last_value
                ELSE 0::bigint
           END
      INTO STRICT current_publication_fence
      FROM public.atom_v9_sim4_intent_admission_seq AS sequence_state;

    IF $1 IS NULL
       OR $2 IS NULL
       OR $3 IS NULL
       OR $4 IS NULL
       OR $5 IS NULL
       OR $6 IS NULL
       OR $1 < 0
       OR $2 < 0
       OR $3 < $1
       OR $3 <> $5
       OR $5 < 0
       OR $5 > current_publication_fence
       OR $4 NOT IN ('ACTIVATION', 'RECONCILIATION')
       OR $6 IN ('-infinity'::timestamptz, 'infinity'::timestamptz) THEN
        RETURN false;
    END IF;

    SELECT cp.last_completed_publication_seq,
           cp.checkpoint_version
      INTO current_last_completed,
           current_checkpoint_version
      FROM public.atom_v9_sim4_reconciliation_checkpoint AS cp
     WHERE cp.checkpoint_key =
           'ATOM_TRUE_V9_SIM4_RECONCILIATION_1'
     FOR UPDATE;

    IF NOT FOUND
       OR current_last_completed <> $1
       OR current_checkpoint_version <> $2 THEN
        RETURN false;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM public.atom_v9_sim_intent_publications AS pub
        LEFT JOIN public.atom_v9_sim_entries AS ent
          ON ent.intent_id = pub.intent_id
        WHERE pub.publication_seq > $1
          AND pub.publication_seq <= $3
          AND (
              ent.intent_id IS NULL
              OR ent.entry_status NOT IN (
                  'ENTERED',
                  'SKIPPED_NO_TRADE',
                  'SKIPPED_UNAVAILABLE',
                  'SKIPPED_POSITION_OPEN',
                  'SKIPPED_WINDOW_EXPIRED',
                  'SKIPPED_RESTART_GAP'
              )
          )
    ) THEN
        RETURN false;
    END IF;

    UPDATE public.atom_v9_sim4_reconciliation_checkpoint AS cp
       SET last_completed_publication_seq = $3,
           checkpoint_version = cp.checkpoint_version + 1,
           runtime_started_at = $6,
           updated_at = pg_catalog.transaction_timestamp()
     WHERE cp.checkpoint_key =
           'ATOM_TRUE_V9_SIM4_RECONCILIATION_1'
       AND cp.last_completed_publication_seq = $1
       AND cp.checkpoint_version = $2
    RETURNING true INTO checkpoint_updated;

    RETURN COALESCE(checkpoint_updated, false);
END
$atom_v9_sim4_compare_and_advance_checkpoint$;

CREATE TRIGGER atom_v9_sim_installation_reject_insert_update_delete
BEFORE INSERT OR UPDATE OR DELETE ON public.atom_v9_sim_installation
FOR EACH STATEMENT EXECUTE FUNCTION public.atom_v9_sim_reject_mutation();
CREATE TRIGGER atom_v9_sim_installation_reject_truncate
BEFORE TRUNCATE ON public.atom_v9_sim_installation
FOR EACH STATEMENT EXECUTE FUNCTION public.atom_v9_sim_reject_mutation();

CREATE TRIGGER atom_v9_sim_intents_publication_before
BEFORE INSERT ON public.atom_v9_sim_intents
FOR EACH ROW EXECUTE FUNCTION public.atom_v9_sim4_lock_intent_admission_before();
CREATE TRIGGER atom_v9_sim_intents_publication_after
AFTER INSERT ON public.atom_v9_sim_intents
FOR EACH ROW EXECUTE FUNCTION public.atom_v9_sim4_publish_intent_after();
CREATE TRIGGER atom_v9_sim_intents_reject_update_delete
BEFORE UPDATE OR DELETE ON public.atom_v9_sim_intents
FOR EACH ROW EXECUTE FUNCTION public.atom_v9_sim_reject_mutation();
CREATE TRIGGER atom_v9_sim_intents_reject_truncate
BEFORE TRUNCATE ON public.atom_v9_sim_intents
FOR EACH STATEMENT EXECUTE FUNCTION public.atom_v9_sim_reject_mutation();

CREATE TRIGGER atom_v9_sim_intent_publications_reject_update_delete
BEFORE UPDATE OR DELETE ON public.atom_v9_sim_intent_publications
FOR EACH ROW EXECUTE FUNCTION public.atom_v9_sim_reject_mutation();
CREATE TRIGGER atom_v9_sim_intent_publications_reject_truncate
BEFORE TRUNCATE ON public.atom_v9_sim_intent_publications
FOR EACH STATEMENT EXECUTE FUNCTION public.atom_v9_sim_reject_mutation();

CREATE TRIGGER atom_v9_sim_entries_reject_update_delete
BEFORE UPDATE OR DELETE ON public.atom_v9_sim_entries
FOR EACH ROW EXECUTE FUNCTION public.atom_v9_sim_reject_mutation();
CREATE TRIGGER atom_v9_sim_entries_reject_truncate
BEFORE TRUNCATE ON public.atom_v9_sim_entries
FOR EACH STATEMENT EXECUTE FUNCTION public.atom_v9_sim_reject_mutation();

CREATE TRIGGER atom_v9_sim4_checkpoint_reject_insert_delete
BEFORE INSERT OR DELETE ON public.atom_v9_sim4_reconciliation_checkpoint
FOR EACH STATEMENT EXECUTE FUNCTION public.atom_v9_sim_reject_mutation();
CREATE TRIGGER atom_v9_sim4_checkpoint_reject_truncate
BEFORE TRUNCATE ON public.atom_v9_sim4_reconciliation_checkpoint
FOR EACH STATEMENT EXECUTE FUNCTION public.atom_v9_sim_reject_mutation();

ALTER TABLE public.atom_v9_sim_installation ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.atom_v9_sim_installation FORCE ROW LEVEL SECURITY;
ALTER TABLE public.atom_v9_sim_intents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.atom_v9_sim_intents FORCE ROW LEVEL SECURITY;
ALTER TABLE public.atom_v9_sim_intent_publications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.atom_v9_sim_intent_publications FORCE ROW LEVEL SECURITY;
ALTER TABLE public.atom_v9_sim_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.atom_v9_sim_entries FORCE ROW LEVEL SECURITY;
ALTER TABLE public.atom_v9_sim4_reconciliation_checkpoint ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.atom_v9_sim4_reconciliation_checkpoint FORCE ROW LEVEL SECURITY;

CREATE POLICY atom_v9_sim_installation_runtime_select
ON public.atom_v9_sim_installation
FOR SELECT TO atom_v9_sim_runtime USING (true);
CREATE POLICY atom_v9_sim_installation_entry_runtime_select
ON public.atom_v9_sim_installation
FOR SELECT TO atom_v9_sim_entry_runtime USING (true);

CREATE POLICY atom_v9_sim_intents_runtime_select
ON public.atom_v9_sim_intents
FOR SELECT TO atom_v9_sim_runtime USING (true);
CREATE POLICY atom_v9_sim_intents_runtime_insert
ON public.atom_v9_sim_intents
FOR INSERT TO atom_v9_sim_runtime WITH CHECK (true);
CREATE POLICY atom_v9_sim_intents_entry_runtime_select
ON public.atom_v9_sim_intents
FOR SELECT TO atom_v9_sim_entry_runtime USING (true);

CREATE POLICY atom_v9_sim_intent_publications_entry_runtime_select
ON public.atom_v9_sim_intent_publications
FOR SELECT TO atom_v9_sim_entry_runtime USING (true);
CREATE POLICY atom_v9_sim_intent_publications_owner_insert
ON public.atom_v9_sim_intent_publications
FOR INSERT TO atom_v9_sim_owner WITH CHECK (true);
CREATE POLICY atom_v9_sim_intent_publications_owner_select
ON public.atom_v9_sim_intent_publications
FOR SELECT TO atom_v9_sim_owner USING (true);

CREATE POLICY atom_v9_sim_entries_entry_runtime_select
ON public.atom_v9_sim_entries
FOR SELECT TO atom_v9_sim_entry_runtime USING (true);
CREATE POLICY atom_v9_sim_entries_entry_runtime_insert
ON public.atom_v9_sim_entries
FOR INSERT TO atom_v9_sim_entry_runtime WITH CHECK (true);
CREATE POLICY atom_v9_sim_entries_owner_select
ON public.atom_v9_sim_entries
FOR SELECT TO atom_v9_sim_owner USING (true);

CREATE POLICY atom_v9_sim4_checkpoint_entry_runtime_select
ON public.atom_v9_sim4_reconciliation_checkpoint
FOR SELECT TO atom_v9_sim_entry_runtime USING (true);
CREATE POLICY atom_v9_sim4_checkpoint_owner_select
ON public.atom_v9_sim4_reconciliation_checkpoint
FOR SELECT TO atom_v9_sim_owner USING (
    checkpoint_key = 'ATOM_TRUE_V9_SIM4_RECONCILIATION_1'
);
CREATE POLICY atom_v9_sim4_checkpoint_owner_update
ON public.atom_v9_sim4_reconciliation_checkpoint
FOR UPDATE TO atom_v9_sim_owner
USING (checkpoint_key = 'ATOM_TRUE_V9_SIM4_RECONCILIATION_1')
WITH CHECK (checkpoint_key = 'ATOM_TRUE_V9_SIM4_RECONCILIATION_1');

REVOKE ALL PRIVILEGES ON TABLE
    public.atom_v9_sim_installation,
    public.atom_v9_sim_intents,
    public.atom_v9_sim_intent_publications,
    public.atom_v9_sim_entries,
    public.atom_v9_sim4_reconciliation_checkpoint
FROM PUBLIC, atom_v9_sim_runtime, atom_v9_sim_entry_runtime;

GRANT SELECT ON TABLE public.atom_v9_sim_installation
TO atom_v9_sim_runtime, atom_v9_sim_entry_runtime;
GRANT SELECT, INSERT ON TABLE public.atom_v9_sim_intents
TO atom_v9_sim_runtime;
GRANT SELECT ON TABLE public.atom_v9_sim_intents
TO atom_v9_sim_entry_runtime;
GRANT SELECT ON TABLE public.atom_v9_sim_intent_publications
TO atom_v9_sim_entry_runtime;
GRANT SELECT, INSERT ON TABLE public.atom_v9_sim_entries
TO atom_v9_sim_entry_runtime;
GRANT SELECT ON TABLE public.atom_v9_sim4_reconciliation_checkpoint
TO atom_v9_sim_entry_runtime;

REVOKE ALL PRIVILEGES ON SEQUENCE
    public.atom_v9_sim4_intent_admission_seq
FROM PUBLIC, atom_v9_sim_runtime, atom_v9_sim_entry_runtime;

REVOKE ALL PRIVILEGES ON FUNCTION
    public.atom_v9_sim_reject_mutation(),
    public.atom_v9_sim4_lock_intent_admission_before(),
    public.atom_v9_sim4_publish_intent_after(),
    public.atom_v9_sim4_read_intent_admission_fence(),
    public.atom_v9_sim4_compare_and_advance_checkpoint(
        bigint, bigint, bigint, text, bigint, timestamptz
    )
FROM PUBLIC, atom_v9_sim_runtime, atom_v9_sim_entry_runtime;

GRANT EXECUTE ON FUNCTION
    public.atom_v9_sim4_read_intent_admission_fence(),
    public.atom_v9_sim4_compare_and_advance_checkpoint(
        bigint, bigint, bigint, text, bigint, timestamptz
    )
TO atom_v9_sim_entry_runtime;

-- Supabase normally supplies these API roles.  Vanilla PostgreSQL test
-- clusters may not, so revoke them only when present.
DO $atom_v9_sim_revoke_optional_roles$
DECLARE
    role_name text;
BEGIN
    FOREACH role_name IN ARRAY ARRAY[
        'anon',
        'authenticated',
        'service_role',
        'atom_v9_v4_runtime'
    ]
    LOOP
        IF EXISTS (
            SELECT 1
            FROM pg_catalog.pg_roles AS db_role
            WHERE db_role.rolname = role_name
        ) THEN
            EXECUTE pg_catalog.format(
                'REVOKE ALL PRIVILEGES ON TABLE public.atom_v9_sim_installation, public.atom_v9_sim_intents, public.atom_v9_sim_intent_publications, public.atom_v9_sim_entries, public.atom_v9_sim4_reconciliation_checkpoint FROM %I',
                role_name
            );
            EXECUTE pg_catalog.format(
                'REVOKE ALL PRIVILEGES ON SEQUENCE public.atom_v9_sim4_intent_admission_seq FROM %I',
                role_name
            );
            EXECUTE pg_catalog.format(
                'REVOKE ALL PRIVILEGES ON FUNCTION public.atom_v9_sim_reject_mutation(), public.atom_v9_sim4_lock_intent_admission_before(), public.atom_v9_sim4_publish_intent_after(), public.atom_v9_sim4_read_intent_admission_fence(), public.atom_v9_sim4_compare_and_advance_checkpoint(bigint, bigint, bigint, text, bigint, timestamptz) FROM %I',
                role_name
            );
        END IF;
    END LOOP;
END
$atom_v9_sim_revoke_optional_roles$;

ALTER TABLE public.atom_v9_sim_installation OWNER TO atom_v9_sim_owner;
ALTER TABLE public.atom_v9_sim_intents OWNER TO atom_v9_sim_owner;
ALTER SEQUENCE public.atom_v9_sim4_intent_admission_seq
OWNER TO atom_v9_sim_owner;
ALTER TABLE public.atom_v9_sim_intent_publications
OWNER TO atom_v9_sim_owner;
ALTER TABLE public.atom_v9_sim_entries OWNER TO atom_v9_sim_owner;
ALTER TABLE public.atom_v9_sim4_reconciliation_checkpoint
OWNER TO atom_v9_sim_owner;

ALTER FUNCTION public.atom_v9_sim_reject_mutation()
OWNER TO atom_v9_sim_owner;
ALTER FUNCTION public.atom_v9_sim4_lock_intent_admission_before()
OWNER TO atom_v9_sim_owner;
ALTER FUNCTION public.atom_v9_sim4_publish_intent_after()
OWNER TO atom_v9_sim_owner;
ALTER FUNCTION public.atom_v9_sim4_read_intent_admission_fence()
OWNER TO atom_v9_sim_owner;
ALTER FUNCTION public.atom_v9_sim4_compare_and_advance_checkpoint(
    bigint, bigint, bigint, text, bigint, timestamptz
)
OWNER TO atom_v9_sim_owner;

REVOKE CREATE ON SCHEMA public FROM atom_v9_sim_owner;

DO $atom_v9_sim_revoke_bootstrap_owner$
BEGIN
    EXECUTE pg_catalog.format(
        'REVOKE atom_v9_sim_owner FROM %I',
        CURRENT_USER
    );
END
$atom_v9_sim_revoke_bootstrap_owner$;

DO $atom_v9_sim_verify_final_authority$
DECLARE
    owner_oid oid;
    publisher_oid oid;
    entry_runtime_oid oid;
    executor_oid oid;
    server_version_number integer;
BEGIN
    server_version_number :=
        pg_catalog.current_setting('server_version_num')::integer;

    SELECT db_role.oid
      INTO STRICT owner_oid
      FROM pg_catalog.pg_roles AS db_role
     WHERE db_role.rolname = 'atom_v9_sim_owner'
       AND NOT db_role.rolcanlogin
       AND NOT db_role.rolinherit
       AND NOT db_role.rolsuper
       AND NOT db_role.rolcreatedb
       AND NOT db_role.rolcreaterole
       AND NOT db_role.rolreplication
       AND NOT db_role.rolbypassrls;

    SELECT db_role.oid
      INTO STRICT publisher_oid
      FROM pg_catalog.pg_roles AS db_role
     WHERE db_role.rolname = 'atom_v9_sim_runtime'
       AND db_role.rolcanlogin
       AND NOT db_role.rolinherit
       AND NOT db_role.rolsuper
       AND NOT db_role.rolcreatedb
       AND NOT db_role.rolcreaterole
       AND NOT db_role.rolreplication
       AND NOT db_role.rolbypassrls;

    SELECT db_role.oid
      INTO STRICT entry_runtime_oid
      FROM pg_catalog.pg_roles AS db_role
     WHERE db_role.rolname = 'atom_v9_sim_entry_runtime'
       AND db_role.rolcanlogin
       AND NOT db_role.rolinherit
       AND NOT db_role.rolsuper
       AND NOT db_role.rolcreatedb
       AND NOT db_role.rolcreaterole
       AND NOT db_role.rolreplication
       AND NOT db_role.rolbypassrls;

    SELECT db_role.oid
      INTO STRICT executor_oid
      FROM pg_catalog.pg_roles AS db_role
     WHERE db_role.rolname = CURRENT_USER;

    -- PostgreSQL catalog columns for SET/INHERIT membership options vary by
    -- server major.  Row-to-JSON lookup keeps this statement parseable on
    -- PostgreSQL 16; a missing key cannot satisfy the PG17-only exception.
    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_auth_members AS membership
        LEFT JOIN pg_catalog.pg_roles AS grantor_role
          ON grantor_role.oid = membership.grantor
        WHERE (
            membership.roleid IN (
                owner_oid,
                publisher_oid,
                entry_runtime_oid
            )
            OR membership.member IN (
                owner_oid,
                publisher_oid,
                entry_runtime_oid
            )
        )
          AND (
              server_version_number >= 170000
              AND server_version_number < 180000
              AND membership.roleid IN (
                  owner_oid,
                  publisher_oid,
                  entry_runtime_oid
              )
              AND membership.member = executor_oid
              AND COALESCE(grantor_role.rolname, '') = 'supabase_admin'
              AND membership.admin_option IS TRUE
              AND COALESCE(
                  pg_catalog.to_jsonb(membership) ->> 'inherit_option',
                  ''
              ) = 'false'
              AND COALESCE(
                  pg_catalog.to_jsonb(membership) ->> 'set_option',
                  ''
              ) = 'false'
           ) IS NOT TRUE
    )
       OR pg_catalog.has_schema_privilege(
           'atom_v9_sim_owner', 'public', 'CREATE'
       )
       OR pg_catalog.has_schema_privilege(
           'atom_v9_sim_runtime', 'public', 'CREATE'
       )
       OR pg_catalog.has_schema_privilege(
           'atom_v9_sim_entry_runtime', 'public', 'CREATE'
       ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'simulator role membership or schema authority is broader than frozen';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class AS rel
        WHERE rel.relname ~ '^atom_v9_sim'
          AND rel.relowner <> owner_oid
    )
       OR EXISTS (
        SELECT 1
        FROM pg_catalog.pg_proc AS proc
        WHERE proc.proname ~ '^atom_v9_sim'
          AND proc.proowner <> owner_oid
    )
       OR (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_proc AS proc
        WHERE proc.proname ~ '^atom_v9_sim'
          AND proc.prosecdef
       ) <> 3 THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'simulator ownership or definer-function count is not frozen';
    END IF;
END
$atom_v9_sim_verify_final_authority$;
