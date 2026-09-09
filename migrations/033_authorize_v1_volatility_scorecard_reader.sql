-- 033: authorize the existing V-1B reader to read the two existing
--      FAMILY volatility evidence tables.
--
-- Controlling law: docs/v-1a-volatility-first-freeze.md, section 15.2,
-- as amended by docs/v-1a-amendment-1-tls-trust-anchor.md and
-- docs/v-1a-amendment-2a-tiered-readiness-boundaries.md.
--
-- The Owner-controlled executor must complete the section 15.2 external
-- project-binding preflight for Supabase project afyiydxbjgzaiswnbcyj and
-- database postgres before transmitting any byte of this file. Apply the
-- file as one transaction. This migration creates no role, password,
-- membership, function, table, default privilege, or database privilege.

-- Fail before every GRANT or POLICY mutation unless the SQL runtime identity
-- is exact. This check deliberately cannot substitute for the required
-- external project-binding preflight.
DO $v1b033_runtime_identity$
BEGIN
    IF current_user <> 'postgres' THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = format(
                'V-1B migration 033 refused: current_user is %L, expected postgres',
                current_user);
    END IF;

    IF current_database() <> 'postgres' THEN
        RAISE EXCEPTION USING
            ERRCODE = '3D000',
            MESSAGE = format(
                'V-1B migration 033 refused: current_database is %L, expected postgres',
                current_database());
    END IF;
END
$v1b033_runtime_identity$;

SET LOCAL lock_timeout = '500ms';
SET LOCAL statement_timeout = '15s';

-- Prove the expected one-time starting state before taking either authorized
-- action. Any drift requires review rather than adoption or repair here.
DO $v1b033_assert_start$
DECLARE
    database_owner text;
    membership_count integer;
    policy_count integer;
    recognized_policy_count integer;
    reader_oid oid;
    select_tables text[];
    target_table_count integer;
BEGIN
    SELECT r.oid
      INTO reader_oid
      FROM pg_catalog.pg_roles AS r
     WHERE r.rolname = 'atom_e1_scorecard_reader'
       AND r.rolcanlogin
       AND NOT r.rolinherit
       AND NOT r.rolsuper
       AND NOT r.rolcreatedb
       AND NOT r.rolcreaterole
       AND NOT r.rolreplication
       AND NOT r.rolbypassrls;

    IF reader_oid IS NULL THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'V-1B migration 033 precondition failed: existing reader attributes are not exact';
    END IF;

    SELECT count(*)
      INTO membership_count
      FROM pg_catalog.pg_auth_members AS m
     WHERE m.member = reader_oid;

    IF membership_count <> 0 THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = format(
                'V-1B migration 033 precondition failed: reader has %s role memberships',
                membership_count);
    END IF;

    SELECT pg_catalog.pg_get_userbyid(d.datdba)
      INTO STRICT database_owner
      FROM pg_catalog.pg_database AS d
     WHERE d.datname = current_database();

    IF database_owner = 'atom_e1_scorecard_reader'
       OR pg_catalog.has_database_privilege(
            'atom_e1_scorecard_reader', current_database(), 'CREATE')
       OR NOT pg_catalog.has_database_privilege(
            'atom_e1_scorecard_reader', current_database(), 'TEMPORARY')
       OR NOT EXISTS (
            SELECT 1
              FROM pg_catalog.pg_database AS d
              CROSS JOIN LATERAL pg_catalog.aclexplode(
                  COALESCE(d.datacl, pg_catalog.acldefault('d', d.datdba))
              ) AS a
             WHERE d.datname = current_database()
               AND a.grantee = 0
               AND a.privilege_type = 'TEMPORARY')
       OR EXISTS (
            SELECT 1
              FROM pg_catalog.pg_database AS d
              CROSS JOIN LATERAL pg_catalog.aclexplode(
                  COALESCE(d.datacl, pg_catalog.acldefault('d', d.datdba))
              ) AS a
             WHERE d.datname = current_database()
               AND a.grantee = reader_oid
               AND a.privilege_type = 'TEMPORARY') THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'V-1B migration 033 precondition failed: database owner/CREATE/public-only TEMPORARY state drifted';
    END IF;

    IF NOT pg_catalog.has_schema_privilege(
            'atom_e1_scorecard_reader', 'public', 'USAGE')
       OR pg_catalog.has_schema_privilege(
            'atom_e1_scorecard_reader', 'public', 'CREATE')
       OR NOT pg_catalog.has_schema_privilege(
            'atom_e1_scorecard_reader', 'atom_v9_internal', 'USAGE') THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'V-1B migration 033 precondition failed: schema authority drifted';
    END IF;

    SELECT count(*)
      INTO target_table_count
      FROM pg_catalog.pg_class AS c
      JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
      JOIN pg_catalog.pg_roles AS o ON o.oid = c.relowner
     WHERE n.nspname = 'public'
       AND c.relname IN (
            'volatility_forecasts',
            'volatility_forecast_outcomes')
       AND c.relkind = 'r'
       AND c.relrowsecurity
       AND o.rolname = 'postgres';

    IF target_table_count <> 2 THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = format(
                'V-1B migration 033 precondition failed: expected two postgres-owned RLS volatility tables, found %s',
                target_table_count);
    END IF;

    SELECT COALESCE(
               array_agg(
                   g.table_schema || '.' || g.table_name
                   ORDER BY g.table_schema, g.table_name),
               ARRAY[]::text[])
      INTO select_tables
      FROM information_schema.role_table_grants AS g
     WHERE g.grantee = 'atom_e1_scorecard_reader'
       AND g.privilege_type = 'SELECT';

    IF select_tables <> ARRAY[
            'public.atom_v9_v4_forecasts',
            'public.atom_v9_v4_outcomes',
            'public.forecast_outcomes',
            'public.forecasts']::text[] THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = format(
                'V-1B migration 033 precondition failed: existing reader SELECT grants are %s',
                select_tables);
    END IF;

    IF pg_catalog.has_table_privilege(
            'atom_e1_scorecard_reader',
            'public.volatility_forecasts', 'SELECT')
       OR pg_catalog.has_table_privilege(
            'atom_e1_scorecard_reader',
            'public.volatility_forecast_outcomes', 'SELECT')
       OR pg_catalog.has_table_privilege(
            'atom_e1_scorecard_reader',
            'public.volatility_forecasts', 'INSERT,UPDATE,DELETE,TRUNCATE')
       OR pg_catalog.has_table_privilege(
            'atom_e1_scorecard_reader',
            'public.volatility_forecast_outcomes', 'INSERT,UPDATE,DELETE,TRUNCATE') THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'V-1B migration 033 precondition failed: volatility-table reader privilege state is not the proved absent state';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM pg_catalog.pg_policies AS p
         WHERE p.schemaname = 'public'
           AND p.tablename IN (
                'volatility_forecasts',
                'volatility_forecast_outcomes')
           AND (
                'public' = ANY(p.roles)
                OR 'atom_e1_scorecard_reader' = ANY(p.roles))) THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'V-1B migration 033 precondition failed: an applicable volatility-table reader policy already exists';
    END IF;

    SELECT count(*)
      INTO recognized_policy_count
      FROM pg_catalog.pg_policies AS p
     WHERE p.schemaname = 'public'
       AND (
            (p.tablename = 'volatility_forecasts'
             AND p.policyname = 'volatility_forecasts_runtime_select'
             AND p.cmd = 'SELECT'
             AND p.permissive = 'PERMISSIVE'
             AND p.roles = ARRAY['atom_v9_v4_runtime']::name[]
             AND p.qual = 'true'
             AND p.with_check IS NULL)
         OR (p.tablename = 'volatility_forecasts'
             AND p.policyname = 'volatility_forecasts_runtime_insert'
             AND p.cmd = 'INSERT'
             AND p.permissive = 'PERMISSIVE'
             AND p.roles = ARRAY['atom_v9_v4_runtime']::name[]
             AND p.qual IS NULL
             AND p.with_check = 'true')
         OR (p.tablename = 'volatility_forecasts'
             AND p.policyname = 'volatility_forecasts_proof_owner_select'
             AND p.cmd = 'SELECT'
             AND p.permissive = 'PERMISSIVE'
             AND p.roles = ARRAY['atom_v9_proof_owner']::name[]
             AND p.qual = 'true'
             AND p.with_check IS NULL)
         OR (p.tablename = 'volatility_forecast_outcomes'
             AND p.policyname = 'volatility_forecast_outcomes_runtime_select'
             AND p.cmd = 'SELECT'
             AND p.permissive = 'PERMISSIVE'
             AND p.roles = ARRAY['atom_v9_v4_runtime']::name[]
             AND p.qual = 'true'
             AND p.with_check IS NULL)
         OR (p.tablename = 'volatility_forecast_outcomes'
             AND p.policyname = 'volatility_forecast_outcomes_runtime_insert'
             AND p.cmd = 'INSERT'
             AND p.permissive = 'PERMISSIVE'
             AND p.roles = ARRAY['atom_v9_v4_runtime']::name[]
             AND p.qual IS NULL
             AND p.with_check = 'true')
         OR (p.tablename = 'volatility_forecast_outcomes'
             AND p.policyname = 'volatility_outcomes_proof_owner_select'
             AND p.cmd = 'SELECT'
             AND p.permissive = 'PERMISSIVE'
             AND p.roles = ARRAY['atom_v9_proof_owner']::name[]
             AND p.qual = 'true'
             AND p.with_check IS NULL));

    SELECT count(*)
      INTO policy_count
      FROM pg_catalog.pg_policies AS p
     WHERE p.schemaname = 'public'
       AND p.tablename IN (
            'volatility_forecasts',
            'volatility_forecast_outcomes');

    IF recognized_policy_count <> 6 OR policy_count <> 6 THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = format(
                'V-1B migration 033 precondition failed: recognized volatility policies %s of 6, total %s of 6',
                recognized_policy_count, policy_count);
    END IF;
END
$v1b033_assert_start$;

-- The only privilege mutation: direct SELECT on the exact two tables.
GRANT SELECT ON TABLE
    public.volatility_forecasts,
    public.volatility_forecast_outcomes
TO atom_e1_scorecard_reader;

-- The only RLS mutations: one permissive, role-specific, full-read SELECT
-- policy on each exact table.
CREATE POLICY volatility_forecasts_e1_scorecard_select
    ON public.volatility_forecasts
    AS PERMISSIVE
    FOR SELECT
    TO atom_e1_scorecard_reader
    USING (true);

CREATE POLICY volatility_forecast_outcomes_e1_scorecard_select
    ON public.volatility_forecast_outcomes
    AS PERMISSIVE
    FOR SELECT
    TO atom_e1_scorecard_reader
    USING (true);

-- Prove the complete least-privilege result. A failure rolls back the GRANT
-- and both policies with the enclosing migration transaction.
DO $v1b033_assert_end$
DECLARE
    membership_count integer;
    non_system_create_count integer;
    non_system_security_definer_count integer;
    non_system_write_count integer;
    policy_count integer;
    reader_policy_count integer;
    reader_oid oid;
    select_tables text[];
    six_table_count integer;
BEGIN
    IF current_user <> 'postgres' OR current_database() <> 'postgres' THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'V-1B migration 033 final-state assertion failed: SQL runtime identity changed';
    END IF;

    SELECT r.oid
      INTO reader_oid
      FROM pg_catalog.pg_roles AS r
     WHERE r.rolname = 'atom_e1_scorecard_reader'
       AND r.rolcanlogin
       AND NOT r.rolinherit
       AND NOT r.rolsuper
       AND NOT r.rolcreatedb
       AND NOT r.rolcreaterole
       AND NOT r.rolreplication
       AND NOT r.rolbypassrls;

    IF reader_oid IS NULL THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'V-1B migration 033 final-state assertion failed: reader attributes changed';
    END IF;

    SELECT count(*)
      INTO membership_count
      FROM pg_catalog.pg_auth_members AS m
     WHERE m.member = reader_oid;

    IF membership_count <> 0 THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'V-1B migration 033 final-state assertion failed: reader has a role membership';
    END IF;

    IF EXISTS (
            SELECT 1
              FROM pg_catalog.pg_database AS d
             WHERE d.datname = current_database()
               AND d.datdba = reader_oid)
       OR pg_catalog.has_database_privilege(
            'atom_e1_scorecard_reader', current_database(), 'CREATE')
       OR NOT pg_catalog.has_database_privilege(
            'atom_e1_scorecard_reader', current_database(), 'TEMPORARY')
       OR NOT EXISTS (
            SELECT 1
              FROM pg_catalog.pg_database AS d
              CROSS JOIN LATERAL pg_catalog.aclexplode(
                  COALESCE(d.datacl, pg_catalog.acldefault('d', d.datdba))
              ) AS a
             WHERE d.datname = current_database()
               AND a.grantee = 0
               AND a.privilege_type = 'TEMPORARY')
       OR EXISTS (
            SELECT 1
              FROM pg_catalog.pg_database AS d
              CROSS JOIN LATERAL pg_catalog.aclexplode(
                  COALESCE(d.datacl, pg_catalog.acldefault('d', d.datdba))
              ) AS a
             WHERE d.datname = current_database()
               AND a.grantee = reader_oid
               AND a.privilege_type = 'TEMPORARY') THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'V-1B migration 033 final-state assertion failed: database owner/CREATE/public-only TEMPORARY state changed';
    END IF;

    IF NOT pg_catalog.has_schema_privilege(
            'atom_e1_scorecard_reader', 'public', 'USAGE')
       OR pg_catalog.has_schema_privilege(
            'atom_e1_scorecard_reader', 'public', 'CREATE')
       OR NOT pg_catalog.has_schema_privilege(
            'atom_e1_scorecard_reader', 'atom_v9_internal', 'USAGE') THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'V-1B migration 033 final-state assertion failed: schema authority changed';
    END IF;

    SELECT count(*)
      INTO non_system_create_count
      FROM pg_catalog.pg_namespace AS n
     WHERE n.nspname <> 'pg_catalog'
       AND n.nspname <> 'information_schema'
       AND n.nspname NOT LIKE 'pg_toast%'
       AND n.nspname NOT LIKE 'pg_temp%'
       AND pg_catalog.has_schema_privilege(
            'atom_e1_scorecard_reader', n.oid, 'CREATE');

    IF non_system_create_count <> 0 THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = format(
                'V-1B migration 033 final-state assertion failed: reader can CREATE in %s non-system schemas',
                non_system_create_count);
    END IF;

    SELECT COALESCE(
               array_agg(
                   g.table_schema || '.' || g.table_name
                   ORDER BY g.table_schema, g.table_name),
               ARRAY[]::text[])
      INTO select_tables
      FROM information_schema.role_table_grants AS g
     WHERE g.grantee = 'atom_e1_scorecard_reader'
       AND g.privilege_type = 'SELECT';

    IF select_tables <> ARRAY[
            'public.atom_v9_v4_forecasts',
            'public.atom_v9_v4_outcomes',
            'public.forecast_outcomes',
            'public.forecasts',
            'public.volatility_forecast_outcomes',
            'public.volatility_forecasts']::text[] THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = format(
                'V-1B migration 033 final-state assertion failed: reader SELECT grants are %s',
                select_tables);
    END IF;

    SELECT count(*)
      INTO six_table_count
      FROM (VALUES
            ('public.forecasts'),
            ('public.forecast_outcomes'),
            ('public.atom_v9_v4_forecasts'),
            ('public.atom_v9_v4_outcomes'),
            ('public.volatility_forecasts'),
            ('public.volatility_forecast_outcomes')) AS expected(table_name)
     WHERE pg_catalog.has_table_privilege(
               'atom_e1_scorecard_reader', expected.table_name, 'SELECT')
       AND NOT pg_catalog.has_table_privilege(
               'atom_e1_scorecard_reader', expected.table_name,
               'INSERT,UPDATE,DELETE,TRUNCATE');

    IF six_table_count <> 6 THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = format(
                'V-1B migration 033 final-state assertion failed: %s of 6 tables have exact effective read/no-write authority',
                six_table_count);
    END IF;

    SELECT count(*)
      INTO non_system_write_count
      FROM pg_catalog.pg_class AS c
      JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
      CROSS JOIN (VALUES
            ('INSERT'), ('UPDATE'), ('DELETE'), ('TRUNCATE')) AS privilege(name)
     WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f')
       AND n.nspname <> 'pg_catalog'
       AND n.nspname <> 'information_schema'
       AND n.nspname NOT LIKE 'pg_toast%'
       AND n.nspname NOT LIKE 'pg_temp%'
       AND pg_catalog.has_table_privilege(
            'atom_e1_scorecard_reader', c.oid, privilege.name);

    IF non_system_write_count <> 0 THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = format(
                'V-1B migration 033 final-state assertion failed: reader has %s non-system relation write privileges',
                non_system_write_count);
    END IF;

    IF NOT pg_catalog.has_function_privilege(
            'atom_e1_scorecard_reader',
            'atom_v9_internal.read_forecast_commit_proof(text)', 'EXECUTE')
       OR NOT pg_catalog.has_function_privilege(
            'atom_e1_scorecard_reader',
            'atom_v9_internal.read_legacy_evidence_publications_for_records(text,timestamptz,bigint[])',
            'EXECUTE') THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'V-1B migration 033 final-state assertion failed: required proof-reader EXECUTE authority changed';
    END IF;

    SELECT count(*)
      INTO non_system_security_definer_count
      FROM pg_catalog.pg_proc AS p
      JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace
     WHERE p.prosecdef
       AND n.nspname <> 'pg_catalog'
       AND n.nspname <> 'information_schema'
       AND n.nspname NOT LIKE 'pg_toast%'
       AND n.nspname NOT LIKE 'pg_temp%'
       AND p.oid NOT IN (
            'atom_v9_internal.read_forecast_commit_proof(text)'::regprocedure,
            'atom_v9_internal.read_legacy_evidence_publications_for_records(text,timestamptz,bigint[])'::regprocedure)
       AND pg_catalog.has_function_privilege(
            'atom_e1_scorecard_reader', p.oid, 'EXECUTE');

    IF non_system_security_definer_count <> 0 THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = format(
                'V-1B migration 033 final-state assertion failed: reader can execute %s additional non-system SECURITY DEFINER routines',
                non_system_security_definer_count);
    END IF;

    SELECT count(*)
      INTO reader_policy_count
      FROM pg_catalog.pg_policies AS p
     WHERE p.schemaname = 'public'
       AND (
            (p.tablename = 'volatility_forecasts'
             AND p.policyname = 'volatility_forecasts_e1_scorecard_select')
         OR (p.tablename = 'volatility_forecast_outcomes'
             AND p.policyname = 'volatility_forecast_outcomes_e1_scorecard_select'))
       AND p.cmd = 'SELECT'
       AND p.permissive = 'PERMISSIVE'
       AND p.roles = ARRAY['atom_e1_scorecard_reader']::name[]
       AND p.qual = 'true'
       AND p.with_check IS NULL;

    SELECT count(*)
      INTO policy_count
      FROM pg_catalog.pg_policies AS p
     WHERE p.schemaname = 'public'
       AND p.tablename IN (
            'volatility_forecasts',
            'volatility_forecast_outcomes');

    IF reader_policy_count <> 2 OR policy_count <> 8 THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = format(
                'V-1B migration 033 final-state assertion failed: reader policies %s of 2, total volatility policies %s of 8',
                reader_policy_count, policy_count);
    END IF;

    IF EXISTS (
        SELECT 1
          FROM pg_catalog.pg_policies AS p
         WHERE p.schemaname = 'public'
           AND p.tablename IN (
                'forecasts',
                'forecast_outcomes',
                'atom_v9_v4_forecasts',
                'atom_v9_v4_outcomes',
                'volatility_forecasts',
                'volatility_forecast_outcomes')
           AND p.cmd = 'SELECT'
           AND p.permissive = 'RESTRICTIVE'
           AND (
                'public' = ANY(p.roles)
                OR 'atom_e1_scorecard_reader' = ANY(p.roles))) THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'V-1B migration 033 final-state assertion failed: an applicable restrictive SELECT policy exists';
    END IF;
END
$v1b033_assert_end$;
