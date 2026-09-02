-- 030: authorize E-1 scorecard reads for the dedicated role
--      atom_e1_scorecard_reader.
--
-- Controlling law: docs/e-1-evidence-scorecard-freeze.md (E-1C), section
-- "Authorized privilege exception", "Migration 030". This file contains
-- only that authorization and replaces the never-applied E-1B text. Apply
-- as ONE transaction (Supabase MCP apply_migration, or psql with an explicit
-- BEGIN/COMMIT around the whole file), only while the evidence writer is
-- idle (00:00-08:00 UTC). Every assertion RAISEs; a raised exception rolls
-- back everything.
--
-- Net membership change: none. One role is created with no password; the
-- owner sets the password afterwards. No BYPASSRLS. No existing policy is
-- altered. atom_historical_score_reader is not touched.

-- 1. Assert the exact starting state.
DO $e1c_assert_start$
DECLARE
    membership_rows integer;
    matching_rows integer;
    ro_executable integer;
    owners_ok integer;
    hsr_select text[];
BEGIN
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'atom_e1_scorecard_reader') THEN
        RAISE EXCEPTION USING ERRCODE = '42710',
            MESSAGE = 'E-1C precondition failed: atom_e1_scorecard_reader already exists; refusing to adopt it';
    END IF;

    SELECT count(*) INTO owners_ok
      FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_roles o ON o.oid = c.relowner
     WHERE c.relnamespace = 'public'::regnamespace
       AND c.relname IN ('forecasts', 'forecast_outcomes', 'atom_v9_v4_forecasts', 'atom_v9_v4_outcomes')
       AND o.rolname = 'postgres';
    IF owners_ok <> 4 OR NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_namespace n JOIN pg_catalog.pg_roles o ON o.oid = n.nspowner
         WHERE n.nspname = 'atom_v9_internal' AND o.rolname = 'postgres'
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '42501',
            MESSAGE = 'E-1C precondition failed: evidence tables and atom_v9_internal must be owned by postgres';
    END IF;

    SELECT count(*) INTO membership_rows
      FROM pg_catalog.pg_auth_members m
      JOIN pg_catalog.pg_roles r ON r.oid = m.member
      JOIN pg_catalog.pg_roles t ON t.oid = m.roleid
     WHERE r.rolname = 'postgres' AND t.rolname = 'atom_v9_proof_owner';
    SELECT count(*) INTO matching_rows
      FROM pg_catalog.pg_auth_members m
      JOIN pg_catalog.pg_roles r ON r.oid = m.member
      JOIN pg_catalog.pg_roles t ON t.oid = m.roleid
      LEFT JOIN pg_catalog.pg_roles g ON g.oid = m.grantor
     WHERE r.rolname = 'postgres' AND t.rolname = 'atom_v9_proof_owner'
       AND g.rolname = 'supabase_admin'
       AND m.admin_option IS TRUE AND m.inherit_option IS FALSE AND m.set_option IS FALSE;
    IF membership_rows <> 1 OR matching_rows <> 1 THEN
        RAISE EXCEPTION USING ERRCODE = '42501',
            MESSAGE = format('E-1C precondition failed: postgres membership in atom_v9_proof_owner is not the single supabase_admin row (found %s rows, %s matching)', membership_rows, matching_rows);
    END IF;

    SELECT count(*) INTO ro_executable
      FROM pg_catalog.pg_proc p
      JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'atom_v9_internal'
       AND pg_catalog.has_function_privilege('supabase_read_only_user', p.oid, 'EXECUTE');
    IF ro_executable <> 2
       OR NOT pg_catalog.has_function_privilege('supabase_read_only_user',
              'atom_v9_internal.read_forecast_commit_proof(text)', 'EXECUTE')
       OR NOT pg_catalog.has_function_privilege('supabase_read_only_user',
              'atom_v9_internal.read_legacy_evidence_publications_for_records(text, timestamptz, bigint[])', 'EXECUTE') THEN
        RAISE EXCEPTION USING ERRCODE = '42501',
            MESSAGE = 'E-1C precondition failed: supabase_read_only_user must hold exactly the two 029 EXECUTE grants';
    END IF;

    SELECT coalesce(array_agg(table_schema || '.' || table_name ORDER BY table_schema, table_name), '{}')
      INTO hsr_select
      FROM information_schema.role_table_grants
     WHERE grantee = 'atom_historical_score_reader' AND privilege_type = 'SELECT';
    IF hsr_select <> ARRAY['public.atom_historical_replay_forecasts',
                           'public.atom_historical_replay_outcomes',
                           'public.atom_historical_replay_runs']
       OR pg_catalog.has_schema_privilege('atom_historical_score_reader', 'atom_v9_internal', 'USAGE')
       OR EXISTS (
            SELECT 1 FROM pg_catalog.pg_proc p
              JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
             WHERE n.nspname = 'atom_v9_internal'
               AND pg_catalog.has_function_privilege('atom_historical_score_reader', p.oid, 'EXECUTE'))
       OR EXISTS (
            SELECT 1 FROM pg_catalog.pg_policies
             WHERE schemaname = 'public'
               AND tablename IN ('forecasts', 'forecast_outcomes', 'atom_v9_v4_forecasts', 'atom_v9_v4_outcomes')
               AND 'atom_historical_score_reader' = ANY(roles)) THEN
        RAISE EXCEPTION USING ERRCODE = '42501',
            MESSAGE = 'E-1C precondition failed: atom_historical_score_reader is not in its expected untouched state';
    END IF;
END
$e1c_assert_start$;

-- 2. The dedicated role, with no password (owner sets it afterwards).
CREATE ROLE atom_e1_scorecard_reader WITH LOGIN NOINHERIT NOSUPERUSER
  NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

-- 3. Schema usage and table reads (postgres owns these; no handoff).
GRANT USAGE ON SCHEMA atom_v9_internal TO atom_e1_scorecard_reader;
GRANT SELECT ON public.forecasts, public.forecast_outcomes,
                public.atom_v9_v4_forecasts, public.atom_v9_v4_outcomes
TO atom_e1_scorecard_reader;

-- 4. One permissive full-read SELECT policy per evidence table.
CREATE POLICY forecasts_e1_scorecard_select
  ON public.forecasts FOR SELECT TO atom_e1_scorecard_reader USING (true);
CREATE POLICY forecast_outcomes_e1_scorecard_select
  ON public.forecast_outcomes FOR SELECT TO atom_e1_scorecard_reader USING (true);
CREATE POLICY atom_v9_v4_forecasts_e1_scorecard_select
  ON public.atom_v9_v4_forecasts FOR SELECT TO atom_e1_scorecard_reader USING (true);
CREATE POLICY atom_v9_v4_outcomes_e1_scorecard_select
  ON public.atom_v9_v4_outcomes FOR SELECT TO atom_e1_scorecard_reader USING (true);

-- 5. Temporary handoff for the proof-owner functions (as 029 step 2).
GRANT atom_v9_proof_owner TO postgres WITH INHERIT TRUE, SET FALSE;

-- 6. Move the two EXECUTE grants from the superseded credential.
GRANT EXECUTE ON FUNCTION
  atom_v9_internal.read_forecast_commit_proof(text)
TO atom_e1_scorecard_reader;
GRANT EXECUTE ON FUNCTION
  atom_v9_internal.read_legacy_evidence_publications_for_records(
    text, timestamptz, bigint[]
  )
TO atom_e1_scorecard_reader;
REVOKE EXECUTE ON FUNCTION
  atom_v9_internal.read_forecast_commit_proof(text)
FROM supabase_read_only_user;
REVOKE EXECUTE ON FUNCTION
  atom_v9_internal.read_legacy_evidence_publications_for_records(
    text, timestamptz, bigint[]
  )
FROM supabase_read_only_user;

-- 7. Remove only the temporary row (as 029 step 4).
REVOKE atom_v9_proof_owner FROM postgres GRANTED BY postgres;

-- 8. Assert the exact final state.
DO $e1c_assert_end$
DECLARE
    membership_rows integer;
    matching_rows integer;
    select_tables text[];
    write_grants integer;
    e1_executable integer;
    ro_executable integer;
    policy_total integer;
    preexisting integer;
    new_policies integer;
    hsr_select text[];
    role_name text;
BEGIN
    SELECT count(*) INTO membership_rows
      FROM pg_catalog.pg_auth_members m
      JOIN pg_catalog.pg_roles r ON r.oid = m.member
      JOIN pg_catalog.pg_roles t ON t.oid = m.roleid
     WHERE r.rolname = 'postgres' AND t.rolname = 'atom_v9_proof_owner';
    SELECT count(*) INTO matching_rows
      FROM pg_catalog.pg_auth_members m
      JOIN pg_catalog.pg_roles r ON r.oid = m.member
      JOIN pg_catalog.pg_roles t ON t.oid = m.roleid
      LEFT JOIN pg_catalog.pg_roles g ON g.oid = m.grantor
     WHERE r.rolname = 'postgres' AND t.rolname = 'atom_v9_proof_owner'
       AND g.rolname = 'supabase_admin'
       AND m.admin_option IS TRUE AND m.inherit_option IS FALSE AND m.set_option IS FALSE;
    IF membership_rows <> 1 OR matching_rows <> 1 THEN
        RAISE EXCEPTION USING ERRCODE = '42501',
            MESSAGE = format('E-1C final-state assertion failed: postgres membership in atom_v9_proof_owner changed (found %s rows, %s matching)', membership_rows, matching_rows);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_authid
         WHERE rolname = 'atom_e1_scorecard_reader'
           AND rolcanlogin AND NOT rolinherit AND NOT rolsuper AND NOT rolcreatedb
           AND NOT rolcreaterole AND NOT rolreplication AND NOT rolbypassrls
           AND rolpassword IS NULL
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '42501',
            MESSAGE = 'E-1C final-state assertion failed: atom_e1_scorecard_reader attributes are not exactly LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS with no password';
    END IF;

    SELECT coalesce(array_agg(table_schema || '.' || table_name ORDER BY table_schema, table_name), '{}')
      INTO select_tables
      FROM information_schema.role_table_grants
     WHERE grantee = 'atom_e1_scorecard_reader' AND privilege_type = 'SELECT';
    IF select_tables <> ARRAY['public.atom_v9_v4_forecasts',
                              'public.atom_v9_v4_outcomes',
                              'public.forecast_outcomes',
                              'public.forecasts'] THEN
        RAISE EXCEPTION USING ERRCODE = '42501',
            MESSAGE = format('E-1C final-state assertion failed: SELECT grants for atom_e1_scorecard_reader are %s', select_tables);
    END IF;

    SELECT count(*) INTO write_grants
      FROM information_schema.role_table_grants
     WHERE grantee = 'atom_e1_scorecard_reader'
       AND privilege_type IN ('INSERT', 'UPDATE', 'DELETE', 'TRUNCATE');
    IF write_grants <> 0 THEN
        RAISE EXCEPTION USING ERRCODE = '42501',
            MESSAGE = 'E-1C final-state assertion failed: atom_e1_scorecard_reader holds a write grant';
    END IF;

    IF NOT pg_catalog.has_schema_privilege('atom_e1_scorecard_reader', 'atom_v9_internal', 'USAGE') THEN
        RAISE EXCEPTION USING ERRCODE = '42501',
            MESSAGE = 'E-1C final-state assertion failed: atom_e1_scorecard_reader lacks USAGE on atom_v9_internal';
    END IF;

    SELECT count(*) INTO e1_executable
      FROM pg_catalog.pg_proc p
      JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'atom_v9_internal'
       AND pg_catalog.has_function_privilege('atom_e1_scorecard_reader', p.oid, 'EXECUTE');
    IF e1_executable <> 2
       OR NOT pg_catalog.has_function_privilege('atom_e1_scorecard_reader',
              'atom_v9_internal.read_forecast_commit_proof(text)', 'EXECUTE')
       OR NOT pg_catalog.has_function_privilege('atom_e1_scorecard_reader',
              'atom_v9_internal.read_legacy_evidence_publications_for_records(text, timestamptz, bigint[])', 'EXECUTE') THEN
        RAISE EXCEPTION USING ERRCODE = '42501',
            MESSAGE = format('E-1C final-state assertion failed: atom_e1_scorecard_reader can execute %s functions in atom_v9_internal; exactly the two authorized are required', e1_executable);
    END IF;

    SELECT count(*) INTO ro_executable
      FROM pg_catalog.pg_proc p
      JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'atom_v9_internal'
       AND pg_catalog.has_function_privilege('supabase_read_only_user', p.oid, 'EXECUTE');
    IF ro_executable <> 0 THEN
        RAISE EXCEPTION USING ERRCODE = '42501',
            MESSAGE = format('E-1C final-state assertion failed: supabase_read_only_user can still execute %s functions in atom_v9_internal', ro_executable);
    END IF;

    SELECT coalesce(array_agg(table_schema || '.' || table_name ORDER BY table_schema, table_name), '{}')
      INTO hsr_select
      FROM information_schema.role_table_grants
     WHERE grantee = 'atom_historical_score_reader' AND privilege_type = 'SELECT';
    IF hsr_select <> ARRAY['public.atom_historical_replay_forecasts',
                           'public.atom_historical_replay_outcomes',
                           'public.atom_historical_replay_runs']
       OR pg_catalog.has_schema_privilege('atom_historical_score_reader', 'atom_v9_internal', 'USAGE')
       OR EXISTS (
            SELECT 1 FROM pg_catalog.pg_proc p
              JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
             WHERE n.nspname = 'atom_v9_internal'
               AND pg_catalog.has_function_privilege('atom_historical_score_reader', p.oid, 'EXECUTE'))
       OR EXISTS (
            SELECT 1 FROM pg_catalog.pg_policies
             WHERE schemaname = 'public'
               AND tablename IN ('forecasts', 'forecast_outcomes', 'atom_v9_v4_forecasts', 'atom_v9_v4_outcomes')
               AND 'atom_historical_score_reader' = ANY(roles)) THEN
        RAISE EXCEPTION USING ERRCODE = '42501',
            MESSAGE = 'E-1C final-state assertion failed: atom_historical_score_reader changed';
    END IF;

    SELECT count(*) INTO new_policies
      FROM pg_catalog.pg_policies
     WHERE schemaname = 'public'
       AND (tablename, policyname) IN (
           ('forecasts', 'forecasts_e1_scorecard_select'),
           ('forecast_outcomes', 'forecast_outcomes_e1_scorecard_select'),
           ('atom_v9_v4_forecasts', 'atom_v9_v4_forecasts_e1_scorecard_select'),
           ('atom_v9_v4_outcomes', 'atom_v9_v4_outcomes_e1_scorecard_select'))
       AND cmd = 'SELECT' AND permissive = 'PERMISSIVE'
       AND roles = ARRAY['atom_e1_scorecard_reader']::name[]
       AND qual = 'true';
    IF new_policies <> 4 THEN
        RAISE EXCEPTION USING ERRCODE = '42501',
            MESSAGE = format('E-1C final-state assertion failed: expected 4 permissive full-read policies, found %s', new_policies);
    END IF;

    SELECT count(*) INTO preexisting
      FROM pg_catalog.pg_policies
     WHERE schemaname = 'public'
       AND (tablename, policyname, cmd, roles::text[]) IN (
           ('forecasts', 'forecasts_proof_owner_select', 'SELECT', ARRAY['atom_v9_proof_owner']),
           ('forecasts', 'forecasts_runtime_insert', 'INSERT', ARRAY['atom_v9_v4_runtime']),
           ('forecasts', 'forecasts_runtime_select', 'SELECT', ARRAY['atom_v9_v4_runtime']),
           ('forecast_outcomes', 'forecast_outcomes_proof_owner_select', 'SELECT', ARRAY['atom_v9_proof_owner']),
           ('forecast_outcomes', 'forecast_outcomes_runtime_insert', 'INSERT', ARRAY['atom_v9_v4_runtime']),
           ('forecast_outcomes', 'forecast_outcomes_runtime_select', 'SELECT', ARRAY['atom_v9_v4_runtime']),
           ('atom_v9_v4_forecasts', 'atom_v9_v4_forecasts_proof_owner_select', 'SELECT', ARRAY['atom_v9_proof_owner']),
           ('atom_v9_v4_forecasts', 'atom_v9_v4_forecasts_runtime_insert', 'INSERT', ARRAY['atom_v9_v4_runtime']),
           ('atom_v9_v4_forecasts', 'atom_v9_v4_forecasts_runtime_select', 'SELECT', ARRAY['atom_v9_v4_runtime']),
           ('atom_v9_v4_outcomes', 'atom_v9_v4_outcomes_runtime_insert', 'INSERT', ARRAY['atom_v9_v4_runtime']),
           ('atom_v9_v4_outcomes', 'atom_v9_v4_outcomes_runtime_select', 'SELECT', ARRAY['atom_v9_v4_runtime']));
    SELECT count(*) INTO policy_total
      FROM pg_catalog.pg_policies
     WHERE schemaname = 'public'
       AND tablename IN ('forecasts', 'forecast_outcomes', 'atom_v9_v4_forecasts', 'atom_v9_v4_outcomes');
    IF preexisting <> 11 OR policy_total <> 15 THEN
        RAISE EXCEPTION USING ERRCODE = '42501',
            MESSAGE = format('E-1C final-state assertion failed: pre-existing policies %s of 11, total %s of 15', preexisting, policy_total);
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_proc p
          JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
          CROSS JOIN LATERAL pg_catalog.aclexplode(p.proacl) a
         WHERE n.nspname = 'atom_v9_internal' AND a.grantee = 0 AND a.privilege_type = 'EXECUTE'
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '42501',
            MESSAGE = 'E-1C final-state assertion failed: PUBLIC can execute a function in atom_v9_internal';
    END IF;

    FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated', 'service_role']
    LOOP
        IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = role_name) AND (
            EXISTS (
                SELECT 1 FROM pg_catalog.pg_proc p
                  JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
                 WHERE n.nspname = 'atom_v9_internal'
                   AND p.proname IN ('read_forecast_commit_proof', 'read_legacy_evidence_publications_for_records')
                   AND pg_catalog.has_function_privilege(role_name, p.oid, 'EXECUTE'))
            OR pg_catalog.has_table_privilege(role_name, 'public.forecasts', 'SELECT')
            OR pg_catalog.has_table_privilege(role_name, 'public.forecast_outcomes', 'SELECT')
            OR pg_catalog.has_table_privilege(role_name, 'public.atom_v9_v4_forecasts', 'SELECT')
            OR pg_catalog.has_table_privilege(role_name, 'public.atom_v9_v4_outcomes', 'SELECT')
        ) THEN
            RAISE EXCEPTION USING ERRCODE = '42501',
                MESSAGE = format('E-1C final-state assertion failed: %s gained access', role_name);
        END IF;
    END LOOP;
END
$e1c_assert_end$;
