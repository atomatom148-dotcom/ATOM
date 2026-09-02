-- 029: authorize E-1 scorecard proof reads.
--
-- Controlling law: docs/e-1-evidence-scorecard-freeze.md (E-1A), section
-- "Authorized privilege exception". This file contains only that
-- authorization. It must be applied as ONE transaction (Supabase MCP
-- apply_migration, or psql with an explicit BEGIN/COMMIT around the whole
-- file). Every assertion RAISEs; a raised exception rolls back everything.
--
-- Net membership change: none. A temporary postgres-grantor membership row
-- exists only inside this transaction and is proven absent before commit.
-- The platform-managed supabase_admin row is never touched.

-- 1. Assert the exact starting state.
DO $e1a_assert_start$
DECLARE
    membership_rows integer;
    matching_rows integer;
    target_functions integer;
BEGIN
    SELECT count(*)
      INTO membership_rows
      FROM pg_catalog.pg_auth_members AS m
      JOIN pg_catalog.pg_roles AS member_role ON member_role.oid = m.member
      JOIN pg_catalog.pg_roles AS target_role ON target_role.oid = m.roleid
     WHERE member_role.rolname = 'postgres'
       AND target_role.rolname = 'atom_v9_proof_owner';

    SELECT count(*)
      INTO matching_rows
      FROM pg_catalog.pg_auth_members AS m
      JOIN pg_catalog.pg_roles AS member_role ON member_role.oid = m.member
      JOIN pg_catalog.pg_roles AS target_role ON target_role.oid = m.roleid
      LEFT JOIN pg_catalog.pg_roles AS grantor_role ON grantor_role.oid = m.grantor
     WHERE member_role.rolname = 'postgres'
       AND target_role.rolname = 'atom_v9_proof_owner'
       AND grantor_role.rolname = 'supabase_admin'
       AND m.admin_option IS TRUE
       AND m.inherit_option IS FALSE
       AND m.set_option IS FALSE;

    IF membership_rows <> 1 OR matching_rows <> 1 THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = format(
                'E-1A precondition failed: expected exactly one postgres membership row in atom_v9_proof_owner (grantor supabase_admin, admin true, inherit false, set false); found %s rows, %s matching',
                membership_rows, matching_rows);
    END IF;

    IF NOT pg_catalog.has_schema_privilege(
        'supabase_read_only_user', 'atom_v9_internal', 'USAGE') THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'E-1A precondition failed: supabase_read_only_user lacks USAGE on atom_v9_internal';
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM pg_catalog.pg_roles
         WHERE rolname = 'supabase_read_only_user'
           AND rolbypassrls
           AND rolcanlogin
           AND NOT rolsuper
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'E-1A precondition failed: supabase_read_only_user must exist with BYPASSRLS, LOGIN, and no superuser';
    END IF;

    SELECT count(*)
      INTO target_functions
      FROM pg_catalog.pg_proc AS p
      JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace
      JOIN pg_catalog.pg_roles AS o ON o.oid = p.proowner
     WHERE n.nspname = 'atom_v9_internal'
       AND o.rolname = 'atom_v9_proof_owner'
       AND p.prosecdef
       AND (
            (p.proname = 'read_forecast_commit_proof'
             AND pg_catalog.pg_get_function_identity_arguments(p.oid) = 'p_id text')
         OR (p.proname = 'read_legacy_evidence_publications_for_records'
             AND pg_catalog.pg_get_function_identity_arguments(p.oid)
                 = 'p_kind text, p_as_of timestamp with time zone, p_record_ids bigint[]')
       );

    IF target_functions <> 2 THEN
        RAISE EXCEPTION USING
            ERRCODE = '42883',
            MESSAGE = format(
                'E-1A precondition failed: expected both proof readers as SECURITY DEFINER functions owned by atom_v9_proof_owner; found %s',
                target_functions);
    END IF;

    IF EXISTS (
        SELECT 1
          FROM pg_catalog.pg_proc AS p
          JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace
         WHERE n.nspname = 'atom_v9_internal'
           AND pg_catalog.has_function_privilege(
               'supabase_read_only_user', p.oid, 'EXECUTE')
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'E-1A precondition failed: supabase_read_only_user can already execute a function in atom_v9_internal';
    END IF;
END
$e1a_assert_start$;

-- 2. Temporary handoff: a second, postgres-grantor membership row.
GRANT atom_v9_proof_owner TO postgres WITH INHERIT TRUE, SET FALSE;

-- 3. The two authorized grants, exactly.
GRANT EXECUTE ON FUNCTION
    atom_v9_internal.read_forecast_commit_proof(text)
TO supabase_read_only_user;

GRANT EXECUTE ON FUNCTION
    atom_v9_internal.read_legacy_evidence_publications_for_records(
        text, timestamptz, bigint[]
    )
TO supabase_read_only_user;

-- 4. Remove only the temporary row; the supabase_admin row is untouched.
REVOKE atom_v9_proof_owner FROM postgres GRANTED BY postgres;

-- 5 and 6. Assert the exact final state.
DO $e1a_assert_end$
DECLARE
    membership_rows integer;
    matching_rows integer;
    ro_executable integer;
    role_name text;
BEGIN
    SELECT count(*)
      INTO membership_rows
      FROM pg_catalog.pg_auth_members AS m
      JOIN pg_catalog.pg_roles AS member_role ON member_role.oid = m.member
      JOIN pg_catalog.pg_roles AS target_role ON target_role.oid = m.roleid
     WHERE member_role.rolname = 'postgres'
       AND target_role.rolname = 'atom_v9_proof_owner';

    SELECT count(*)
      INTO matching_rows
      FROM pg_catalog.pg_auth_members AS m
      JOIN pg_catalog.pg_roles AS member_role ON member_role.oid = m.member
      JOIN pg_catalog.pg_roles AS target_role ON target_role.oid = m.roleid
      LEFT JOIN pg_catalog.pg_roles AS grantor_role ON grantor_role.oid = m.grantor
     WHERE member_role.rolname = 'postgres'
       AND target_role.rolname = 'atom_v9_proof_owner'
       AND grantor_role.rolname = 'supabase_admin'
       AND m.admin_option IS TRUE
       AND m.inherit_option IS FALSE
       AND m.set_option IS FALSE;

    IF membership_rows <> 1 OR matching_rows <> 1 THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = format(
                'E-1A final-state assertion failed: postgres membership in atom_v9_proof_owner is not exactly the original single supabase_admin row; found %s rows, %s matching',
                membership_rows, matching_rows);
    END IF;

    IF NOT pg_catalog.has_function_privilege(
        'supabase_read_only_user',
        'atom_v9_internal.read_forecast_commit_proof(text)', 'EXECUTE')
       OR NOT pg_catalog.has_function_privilege(
        'supabase_read_only_user',
        'atom_v9_internal.read_legacy_evidence_publications_for_records(text, timestamptz, bigint[])',
        'EXECUTE') THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'E-1A final-state assertion failed: supabase_read_only_user cannot execute both authorized proof readers';
    END IF;

    SELECT count(*)
      INTO ro_executable
      FROM pg_catalog.pg_proc AS p
      JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace
     WHERE n.nspname = 'atom_v9_internal'
       AND pg_catalog.has_function_privilege(
           'supabase_read_only_user', p.oid, 'EXECUTE');

    IF ro_executable <> 2 THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = format(
                'E-1A final-state assertion failed: supabase_read_only_user can execute %s functions in atom_v9_internal; exactly 2 are authorized',
                ro_executable);
    END IF;

    IF EXISTS (
        SELECT 1
          FROM pg_catalog.pg_proc AS p
          JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace
          CROSS JOIN LATERAL pg_catalog.aclexplode(p.proacl) AS acl
         WHERE n.nspname = 'atom_v9_internal'
           AND acl.grantee = 0
           AND acl.privilege_type = 'EXECUTE'
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'E-1A final-state assertion failed: PUBLIC can execute a function in atom_v9_internal';
    END IF;

    FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated', 'service_role']
    LOOP
        IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = role_name)
           AND EXISTS (
            SELECT 1
              FROM pg_catalog.pg_proc AS p
              JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace
             WHERE n.nspname = 'atom_v9_internal'
               AND p.proname IN (
                   'read_forecast_commit_proof',
                   'read_legacy_evidence_publications_for_records')
               AND pg_catalog.has_function_privilege(role_name, p.oid, 'EXECUTE')
        ) THEN
            RAISE EXCEPTION USING
                ERRCODE = '42501',
                MESSAGE = format(
                    'E-1A final-state assertion failed: %s can execute an authorized proof reader',
                    role_name);
        END IF;
    END LOOP;
END
$e1a_assert_end$;
