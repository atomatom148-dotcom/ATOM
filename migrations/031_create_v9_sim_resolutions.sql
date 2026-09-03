-- SIM-5: append-only terminal-resolution ledger for durable SIM-4 `ENTERED`
-- positions.  Authority: docs/sim-4a-exact-sim5-resolution-freeze.md,
-- section 8.
--
-- Runs only against the already-bootstrapped isolated ATOM TRUE V9
-- simulator project (migration 027).  This migration adds exactly one new
-- table, its minimum supporting lookup index, immutable-mutation triggers
-- (reusing the existing append-only rejection function), row-level security
-- policies, and the minimum additional grant to the existing SIM-4 entry
-- runtime role.  It creates no new role, no new function, and does not
-- alter any existing object.

DO $atom_v9_sim5_preflight$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM public.atom_v9_sim_installation
        WHERE installation_id = 'ATOM_TRUE_V9_SIM_INSTALLATION_1'
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '55000',
            MESSAGE = 'SIM-5 requires the already-bootstrapped isolated simulator installation';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'atom_v9_sim_owner'
    ) OR NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'atom_v9_sim_entry_runtime'
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '55000',
            MESSAGE = 'SIM-5 requires the existing SIM-4 simulator roles';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class AS rel
        WHERE rel.relname = 'atom_v9_sim_entries'
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '55000',
            MESSAGE = 'SIM-5 requires the existing atom_v9_sim_entries table';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class AS rel
        WHERE rel.relname = 'atom_v9_sim_resolutions'
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '42710',
            MESSAGE = 'atom_v9_sim_resolutions already exists; refusing to redefine it';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_proc AS proc
        WHERE proc.proname = 'atom_v9_sim_reject_mutation'
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '55000',
            MESSAGE = 'SIM-5 requires the existing append-only rejection function';
    END IF;
END
$atom_v9_sim5_preflight$;

DO $atom_v9_sim5_grant_bootstrap_owner$
BEGIN
    EXECUTE pg_catalog.format(
        'GRANT atom_v9_sim_owner TO %I',
        CURRENT_USER
    );
END
$atom_v9_sim5_grant_bootstrap_owner$;

CREATE TABLE public.atom_v9_sim_resolutions (
    resolution_id text PRIMARY KEY,
    resolution_hash text UNIQUE NOT NULL,
    contract_version text NOT NULL,
    canonicalization_version text NOT NULL,
    simulator_version text NOT NULL,
    mode text NOT NULL,
    symbol text NOT NULL,
    instrument text NOT NULL,
    entry_id text UNIQUE NOT NULL
        REFERENCES public.atom_v9_sim_entries (entry_id) ON DELETE RESTRICT,
    entry_hash text NOT NULL,
    source_cycle_id text NOT NULL,
    cutoff_at timestamptz NOT NULL,
    horizon text NOT NULL,
    horizon_seconds integer NOT NULL,
    decision text NOT NULL,
    entry_quote_id text NOT NULL,
    entry_quote_hash text NOT NULL,
    entry_price double precision NOT NULL,
    resolution_target_at timestamptz NOT NULL,
    resolution_deadline_at timestamptz NOT NULL,
    resolution_status text NOT NULL,
    exit_quote_id text NULL,
    exit_quote_hash text NULL,
    exit_quote_source_spec text NULL,
    exit_quote_event_ns bigint NULL,
    exit_quote_accepted_at timestamptz NULL,
    exit_price double precision NULL,
    return_bps double precision NULL,
    record_json jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT atom_v9_sim_resolutions_identity_check CHECK (
        resolution_hash ~ '^[0-9a-f]{64}$'
        AND resolution_id = 'v9simresolution:' || resolution_hash
    ),
    CONSTRAINT atom_v9_sim_resolutions_contract_check CHECK (
        contract_version = 'ATOM_TRUE_V9_SIM5_RESOLUTION_1'
        AND canonicalization_version = 'ATOM_TRUE_V9_SIM_CANONICAL_V4A_1'
        AND simulator_version = 'ATOM_TRUE_V9_SIM_1'
        AND mode = 'PAPER_ONLY'
        AND symbol = 'COIN'
        AND instrument = 'COIN_SHARE'
    ),
    CONSTRAINT atom_v9_sim_resolutions_entry_identity_check CHECK (
        entry_hash ~ '^[0-9a-f]{64}$'
        AND entry_id = 'v9simentry:' || entry_hash
    ),
    CONSTRAINT atom_v9_sim_resolutions_horizon_check CHECK (
        (horizon, horizon_seconds) IN
        (('30S', 30), ('1M', 60), ('5M', 300), ('15M', 900),
         ('30M', 1800), ('1H', 3600))
    ),
    CONSTRAINT atom_v9_sim_resolutions_decision_check CHECK (
        decision IN ('LONG', 'SHORT')
    ),
    CONSTRAINT atom_v9_sim_resolutions_entry_quote_identity_check CHECK (
        entry_quote_hash ~ '^[0-9a-f]{64}$'
        AND entry_quote_id = 'v9simquote:' || entry_quote_hash
    ),
    CONSTRAINT atom_v9_sim_resolutions_entry_price_check CHECK (
        entry_price > 0
        AND entry_price NOT IN ('NaN'::double precision,
                                 '-Infinity'::double precision,
                                 'Infinity'::double precision)
    ),
    CONSTRAINT atom_v9_sim_resolutions_cutoff_check CHECK (
        cutoff_at NOT IN ('-infinity'::timestamptz, 'infinity'::timestamptz)
    ),
    CONSTRAINT atom_v9_sim_resolutions_window_check CHECK (
        resolution_target_at = cutoff_at + make_interval(secs => horizon_seconds)
        AND resolution_deadline_at = resolution_target_at + interval '2 seconds'
    ),
    CONSTRAINT atom_v9_sim_resolutions_status_check CHECK (
        resolution_status IN (
            'RESOLVED',
            'UNRESOLVED_WINDOW_EXPIRED',
            'UNRESOLVED_OBSERVATION_GAP'
        )
    ),
    CONSTRAINT atom_v9_sim_resolutions_resolved_fields_check CHECK (
        (
            resolution_status = 'RESOLVED'
            AND exit_quote_id IS NOT NULL
            AND exit_quote_hash ~ '^[0-9a-f]{64}$'
            AND exit_quote_id = 'v9simquote:' || exit_quote_hash
            AND exit_quote_source_spec = 'ATOM_TRUE_V9_SIM4_ALPACA_SIP_QUOTE_1'
            AND exit_quote_event_ns IS NOT NULL
            AND exit_quote_event_ns >= 0
            AND exit_quote_event_ns BETWEEN
                (((EXTRACT(EPOCH FROM resolution_target_at) * 1000000)::bigint) * 1000)
                AND (((EXTRACT(EPOCH FROM resolution_deadline_at) * 1000000)::bigint) * 1000)
            AND exit_quote_accepted_at IS NOT NULL
            AND exit_quote_accepted_at NOT IN (
                '-infinity'::timestamptz, 'infinity'::timestamptz
            )
            AND exit_quote_accepted_at BETWEEN resolution_target_at
                AND resolution_deadline_at
            AND exit_price IS NOT NULL
            AND exit_price > 0
            AND exit_price NOT IN ('NaN'::double precision,
                                    '-Infinity'::double precision,
                                    'Infinity'::double precision)
            AND return_bps IS NOT NULL
            AND return_bps NOT IN ('NaN'::double precision,
                                    '-Infinity'::double precision,
                                    'Infinity'::double precision)
        )
        OR (
            resolution_status IN (
                'UNRESOLVED_WINDOW_EXPIRED', 'UNRESOLVED_OBSERVATION_GAP'
            )
            AND exit_quote_id IS NULL
            AND exit_quote_hash IS NULL
            AND exit_quote_source_spec IS NULL
            AND exit_quote_event_ns IS NULL
            AND exit_quote_accepted_at IS NULL
            AND exit_price IS NULL
            AND return_bps IS NULL
        )
    ),
    CONSTRAINT atom_v9_sim_resolutions_record_json_check CHECK (
        jsonb_typeof(record_json) = 'object'
        AND jsonb_array_length(jsonb_path_query_array(record_json, '$.*')) = 24
        AND record_json ?& ARRAY[
            'contract_version', 'canonicalization_version',
            'simulator_version', 'resolution_id', 'resolution_hash', 'mode',
            'symbol', 'instrument', 'entry_id', 'entry_hash',
            'source_cycle_id', 'cutoff_at', 'horizon', 'horizon_seconds',
            'decision', 'entry_quote_id', 'entry_quote_hash', 'entry_price',
            'resolution_target_at', 'resolution_deadline_at',
            'resolution_status', 'exit_quote', 'exit_price', 'return_bps'
        ]
        AND record_json ->> 'contract_version' = contract_version
        AND record_json ->> 'canonicalization_version' = canonicalization_version
        AND record_json ->> 'simulator_version' = simulator_version
        AND record_json ->> 'resolution_id' = resolution_id
        AND record_json ->> 'resolution_hash' = resolution_hash
        AND record_json ->> 'mode' = mode
        AND record_json ->> 'symbol' = symbol
        AND record_json ->> 'instrument' = instrument
        AND record_json ->> 'entry_id' = entry_id
        AND record_json ->> 'entry_hash' = entry_hash
        AND record_json ->> 'source_cycle_id' = source_cycle_id
        AND record_json #>> '{cutoff_at,$timestamp_utc}' =
            to_char(cutoff_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
        AND record_json ->> 'horizon' = horizon
        AND record_json ->> 'horizon_seconds' = horizon_seconds::text
        AND record_json ->> 'decision' = decision
        AND record_json ->> 'entry_quote_id' = entry_quote_id
        AND record_json ->> 'entry_quote_hash' = entry_quote_hash
        AND record_json #>> '{resolution_target_at,$timestamp_utc}' =
            to_char(
                resolution_target_at AT TIME ZONE 'UTC',
                'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
            )
        AND record_json #>> '{resolution_deadline_at,$timestamp_utc}' =
            to_char(
                resolution_deadline_at AT TIME ZONE 'UTC',
                'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
            )
        AND record_json ->> 'resolution_status' = resolution_status
        AND (
            (
                resolution_status = 'RESOLVED'
                AND jsonb_typeof(record_json -> 'exit_quote') = 'object'
                AND record_json #>> '{exit_quote,quote_id}' = exit_quote_id
                AND record_json #>> '{exit_quote,quote_hash}' = exit_quote_hash
                AND record_json #>> '{exit_quote,source_spec}' = exit_quote_source_spec
                AND record_json #>> '{exit_quote,provider_event_ns}' = exit_quote_event_ns::text
                AND record_json #>> '{exit_quote,accepted_at,$timestamp_utc}' =
                    to_char(
                        exit_quote_accepted_at AT TIME ZONE 'UTC',
                        'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
                    )
            )
            OR (
                resolution_status IN (
                    'UNRESOLVED_WINDOW_EXPIRED', 'UNRESOLVED_OBSERVATION_GAP'
                )
                AND record_json -> 'exit_quote' = 'null'::jsonb
                AND record_json -> 'exit_price' = 'null'::jsonb
                AND record_json -> 'return_bps' = 'null'::jsonb
            )
        )
    )
);

-- Minimum index required for this contract: the acceptance receipt
-- (freeze section 13) reports open/terminal counts by horizon and status,
-- and the SIM-4 entry occupancy check needs a fast anti-join on entry_id.
-- entry_id and resolution_hash already carry unique indexes from their
-- column constraints above; this is the one additional index needed.
CREATE INDEX atom_v9_sim_resolutions_lookup_idx
ON public.atom_v9_sim_resolutions (horizon, resolution_status, entry_id);

-- Ownership transfers before the REVOKE/GRANT block below.  ALTER TABLE
-- OWNER TO resets a table's ACL and grants the new owner implicit full
-- privileges, discarding any prior explicit grant to that role; only a
-- REVOKE/GRANT issued after ownership transfer persists as the owner's
-- actual authority.
ALTER TABLE public.atom_v9_sim_resolutions OWNER TO atom_v9_sim_owner;

CREATE TRIGGER atom_v9_sim_resolutions_reject_update_delete
BEFORE UPDATE OR DELETE ON public.atom_v9_sim_resolutions
FOR EACH ROW EXECUTE FUNCTION public.atom_v9_sim_reject_mutation();
CREATE TRIGGER atom_v9_sim_resolutions_reject_truncate
BEFORE TRUNCATE ON public.atom_v9_sim_resolutions
FOR EACH STATEMENT EXECUTE FUNCTION public.atom_v9_sim_reject_mutation();

ALTER TABLE public.atom_v9_sim_resolutions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.atom_v9_sim_resolutions FORCE ROW LEVEL SECURITY;

CREATE POLICY atom_v9_sim_resolutions_entry_runtime_select
ON public.atom_v9_sim_resolutions
FOR SELECT TO atom_v9_sim_entry_runtime USING (true);
CREATE POLICY atom_v9_sim_resolutions_entry_runtime_insert
ON public.atom_v9_sim_resolutions
FOR INSERT TO atom_v9_sim_entry_runtime WITH CHECK (true);
CREATE POLICY atom_v9_sim_resolutions_owner_select
ON public.atom_v9_sim_resolutions
FOR SELECT TO atom_v9_sim_owner USING (true);

-- atom_v9_sim_owner is included here (unlike migration 027's sibling
-- REVOKE) because this table's final-authority verification below holds
-- the owner to exactly SELECT.  A table owner otherwise keeps implicit
-- full privileges even when never explicitly granted them; only an
-- explicit REVOKE naming the owner actually strips that implicit grant.
REVOKE ALL PRIVILEGES ON TABLE public.atom_v9_sim_resolutions
FROM PUBLIC, atom_v9_sim_runtime, atom_v9_sim_entry_runtime, atom_v9_sim_owner;

-- Exactly the minimum additional authority the freeze grants: SELECT and
-- INSERT only.  No UPDATE, DELETE, TRUNCATE, or schema authority.
GRANT SELECT, INSERT ON TABLE public.atom_v9_sim_resolutions
TO atom_v9_sim_entry_runtime;
GRANT SELECT ON TABLE public.atom_v9_sim_resolutions
TO atom_v9_sim_owner;

-- Supabase normally supplies these API roles.  Vanilla PostgreSQL test
-- clusters may not, so revoke them only when present (matches migration
-- 027's optional-role handling).
DO $atom_v9_sim5_revoke_optional_roles$
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
                'REVOKE ALL PRIVILEGES ON TABLE public.atom_v9_sim_resolutions FROM %I',
                role_name
            );
        END IF;
    END LOOP;
END
$atom_v9_sim5_revoke_optional_roles$;

DO $atom_v9_sim5_revoke_bootstrap_owner$
BEGIN
    EXECUTE pg_catalog.format(
        'REVOKE atom_v9_sim_owner FROM %I',
        CURRENT_USER
    );
END
$atom_v9_sim5_revoke_bootstrap_owner$;

DO $atom_v9_sim5_verify_final_authority$
DECLARE
    owner_oid oid;
    entry_runtime_oid oid;
    runtime_oid oid;
    entry_runtime_privs record;
    runtime_privs record;
    owner_privs record;
BEGIN
    SELECT db_role.oid INTO STRICT owner_oid
      FROM pg_catalog.pg_roles AS db_role WHERE db_role.rolname = 'atom_v9_sim_owner';
    SELECT db_role.oid INTO STRICT entry_runtime_oid
      FROM pg_catalog.pg_roles AS db_role WHERE db_role.rolname = 'atom_v9_sim_entry_runtime';
    SELECT db_role.oid INTO STRICT runtime_oid
      FROM pg_catalog.pg_roles AS db_role WHERE db_role.rolname = 'atom_v9_sim_runtime';

    IF (SELECT rel.relowner FROM pg_catalog.pg_class AS rel
         WHERE rel.oid = 'public.atom_v9_sim_resolutions'::regclass) <> owner_oid THEN
        RAISE EXCEPTION USING ERRCODE = '42501',
            MESSAGE = 'atom_v9_sim_resolutions is not owned by atom_v9_sim_owner';
    END IF;

    IF NOT (
        SELECT rel.relrowsecurity AND rel.relforcerowsecurity
        FROM pg_catalog.pg_class AS rel
        WHERE rel.oid = 'public.atom_v9_sim_resolutions'::regclass
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '42501',
            MESSAGE = 'atom_v9_sim_resolutions row-level security is not enabled and forced';
    END IF;

    IF (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_trigger AS trg
        WHERE trg.tgrelid = 'public.atom_v9_sim_resolutions'::regclass
          AND NOT trg.tgisinternal
          AND trg.tgfoid = 'public.atom_v9_sim_reject_mutation()'::regprocedure
    ) <> 2 THEN
        RAISE EXCEPTION USING ERRCODE = '42501',
            MESSAGE = 'atom_v9_sim_resolutions is missing its append-only triggers';
    END IF;

    SELECT
        pg_catalog.has_table_privilege(entry_runtime_oid,
            'public.atom_v9_sim_resolutions', 'SELECT') AS can_select,
        pg_catalog.has_table_privilege(entry_runtime_oid,
            'public.atom_v9_sim_resolutions', 'INSERT') AS can_insert,
        pg_catalog.has_table_privilege(entry_runtime_oid,
            'public.atom_v9_sim_resolutions', 'UPDATE') AS can_update,
        pg_catalog.has_table_privilege(entry_runtime_oid,
            'public.atom_v9_sim_resolutions', 'DELETE') AS can_delete,
        pg_catalog.has_table_privilege(entry_runtime_oid,
            'public.atom_v9_sim_resolutions', 'TRUNCATE') AS can_truncate
    INTO STRICT entry_runtime_privs;

    IF NOT entry_runtime_privs.can_select
       OR NOT entry_runtime_privs.can_insert
       OR entry_runtime_privs.can_update
       OR entry_runtime_privs.can_delete
       OR entry_runtime_privs.can_truncate THEN
        RAISE EXCEPTION USING ERRCODE = '42501',
            MESSAGE = 'atom_v9_sim_entry_runtime authority on atom_v9_sim_resolutions is not exactly SELECT/INSERT';
    END IF;

    IF pg_catalog.has_table_privilege(runtime_oid,
           'public.atom_v9_sim_resolutions', 'SELECT')
       OR pg_catalog.has_table_privilege(runtime_oid,
           'public.atom_v9_sim_resolutions', 'INSERT')
       OR pg_catalog.has_table_privilege(runtime_oid,
           'public.atom_v9_sim_resolutions', 'UPDATE')
       OR pg_catalog.has_table_privilege(runtime_oid,
           'public.atom_v9_sim_resolutions', 'DELETE') THEN
        RAISE EXCEPTION USING ERRCODE = '42501',
            MESSAGE = 'atom_v9_sim_runtime must not gain any authority over atom_v9_sim_resolutions';
    END IF;

    IF NOT pg_catalog.has_table_privilege(owner_oid,
           'public.atom_v9_sim_resolutions', 'SELECT')
       OR pg_catalog.has_table_privilege(owner_oid,
           'public.atom_v9_sim_resolutions', 'INSERT')
       OR pg_catalog.has_table_privilege(owner_oid,
           'public.atom_v9_sim_resolutions', 'UPDATE')
       OR pg_catalog.has_table_privilege(owner_oid,
           'public.atom_v9_sim_resolutions', 'DELETE') THEN
        RAISE EXCEPTION USING ERRCODE = '42501',
            MESSAGE = 'atom_v9_sim_owner authority on atom_v9_sim_resolutions is not exactly SELECT';
    END IF;

    IF (
        SELECT conname FROM pg_catalog.pg_constraint
        WHERE conrelid = 'public.atom_v9_sim_resolutions'::regclass
          AND contype = 'f'
          AND confrelid = 'public.atom_v9_sim_entries'::regclass
          AND confdeltype = 'r'
    ) IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = '42501',
            MESSAGE = 'atom_v9_sim_resolutions is missing its RESTRICT foreign key to atom_v9_sim_entries';
    END IF;
END
$atom_v9_sim5_verify_final_authority$;