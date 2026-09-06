-- SIM-5W: dedicated least-privilege reader for the read-only simulation web
-- card.  Authority: docs/sim-5w-read-only-sim-web-card-freeze.md, section 2.
--
-- Runs only against the already-bootstrapped isolated ATOM TRUE V9
-- simulator project (migrations 027 and 031).  This migration creates
-- exactly one login role, grants it exactly schema USAGE plus SELECT on
-- public.atom_v9_sim_resolutions, and adds exactly one SELECT row-level
-- security policy scoped to that role.  It creates no table, function,
-- sequence, or membership, contains no password, and does not alter any
-- existing role, grant, policy, table, or function.  The Owner sets the
-- role's password out of band.  This migration intentionally contains no
-- transaction-control statement.

DO $atom_v9_sim5w_preflight$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM public.atom_v9_sim_installation
        WHERE installation_id = 'ATOM_TRUE_V9_SIM_INSTALLATION_1'
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '55000',
            MESSAGE = 'SIM-5W requires the already-bootstrapped isolated simulator installation';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'atom_v9_sim_owner'
    ) OR NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'atom_v9_sim_runtime'
    ) OR NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'atom_v9_sim_entry_runtime'
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '55000',
            MESSAGE = 'SIM-5W requires the existing simulator roles';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class AS rel
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = rel.relnamespace
        WHERE namespace.nspname = 'public'
          AND rel.relname = 'atom_v9_sim_resolutions'
          AND rel.relkind = 'r'
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '55000',
            MESSAGE = 'SIM-5W requires the existing atom_v9_sim_resolutions table';
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'atom_v9_sim_web_reader'
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '42710',
            MESSAGE = 'atom_v9_sim_web_reader already exists; refusing to adopt it';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_policy AS pol
        WHERE pol.polrelid = 'public.atom_v9_sim_resolutions'::regclass
          AND pol.polname = 'atom_v9_sim_resolutions_web_reader_select'
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '42710',
            MESSAGE = 'atom_v9_sim_resolutions_web_reader_select already exists; refusing to redefine it';
    END IF;
END
$atom_v9_sim5w_preflight$;

-- Exactly the frozen role attributes.  No password: the Owner sets it out of
-- band after the migration is applied.
CREATE ROLE atom_v9_sim_web_reader WITH
    LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOREPLICATION NOBYPASSRLS;

-- Granting on a table owned by the NOLOGIN simulator owner and creating a
-- policy on it require owner authority.  As in migrations 027 and 031, the
-- executor borrows that membership only inside this operator-owned
-- transaction and drops it below, leaving the owner role exactly as found.
DO $atom_v9_sim5w_grant_bootstrap_owner$
BEGIN
    EXECUTE pg_catalog.format(
        'GRANT atom_v9_sim_owner TO %I',
        CURRENT_USER
    );
END
$atom_v9_sim5w_grant_bootstrap_owner$;

-- Exactly the two frozen grants (freeze section 2).
GRANT USAGE ON SCHEMA public TO atom_v9_sim_web_reader;
GRANT SELECT ON TABLE public.atom_v9_sim_resolutions TO atom_v9_sim_web_reader;

-- Exactly one minimum SELECT policy scoped to the reader; the table already
-- enables and forces row-level security (migration 031).
CREATE POLICY atom_v9_sim_resolutions_web_reader_select
ON public.atom_v9_sim_resolutions
FOR SELECT TO atom_v9_sim_web_reader USING (true);

DO $atom_v9_sim5w_revoke_bootstrap_owner$
BEGIN
    EXECUTE pg_catalog.format(
        'REVOKE atom_v9_sim_owner FROM %I',
        CURRENT_USER
    );
END
$atom_v9_sim5w_revoke_bootstrap_owner$;

DO $atom_v9_sim5w_verify_final_authority$
DECLARE
    reader_oid oid;
    owner_oid oid;
    publisher_oid oid;
    entry_runtime_oid oid;
    executor_oid oid;
    server_version_number integer;
    reader_privs record;
    entry_runtime_privs record;
    owner_privs record;
    other_relation text;
    other_function text;
BEGIN
    server_version_number :=
        pg_catalog.current_setting('server_version_num')::integer;

    -- Exact reader attributes.
    SELECT db_role.oid
      INTO STRICT reader_oid
      FROM pg_catalog.pg_roles AS db_role
     WHERE db_role.rolname = 'atom_v9_sim_web_reader'
       AND db_role.rolcanlogin
       AND NOT db_role.rolinherit
       AND NOT db_role.rolsuper
       AND NOT db_role.rolcreatedb
       AND NOT db_role.rolcreaterole
       AND NOT db_role.rolreplication
       AND NOT db_role.rolbypassrls;

    SELECT db_role.oid INTO STRICT owner_oid
      FROM pg_catalog.pg_roles AS db_role WHERE db_role.rolname = 'atom_v9_sim_owner';
    SELECT db_role.oid INTO STRICT publisher_oid
      FROM pg_catalog.pg_roles AS db_role WHERE db_role.rolname = 'atom_v9_sim_runtime';
    SELECT db_role.oid INTO STRICT entry_runtime_oid
      FROM pg_catalog.pg_roles AS db_role WHERE db_role.rolname = 'atom_v9_sim_entry_runtime';
    SELECT db_role.oid INTO STRICT executor_oid
      FROM pg_catalog.pg_roles AS db_role WHERE db_role.rolname = CURRENT_USER;

    -- Zero role membership in either direction.  Supabase PostgreSQL 17
    -- retains one platform-managed, ADMIN-only catalog grant from
    -- supabase_admin for each role created by its postgres executor; that
    -- exact inert artifact is the only permitted row (as in migration 027).
    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_auth_members AS membership
        LEFT JOIN pg_catalog.pg_roles AS grantor_role
          ON grantor_role.oid = membership.grantor
        WHERE (membership.roleid = reader_oid OR membership.member = reader_oid)
          AND (
              server_version_number >= 170000
              AND server_version_number < 180000
              AND membership.roleid = reader_oid
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
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'atom_v9_sim_web_reader must hold and receive no role membership';
    END IF;

    -- The temporary owner membership must be gone again.
    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_auth_members AS membership
        WHERE membership.roleid = owner_oid
          AND membership.member = executor_oid
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'bootstrap membership in atom_v9_sim_owner was not revoked';
    END IF;

    -- Exactly schema USAGE; never schema CREATE.
    IF NOT pg_catalog.has_schema_privilege(reader_oid, 'public', 'USAGE')
       OR pg_catalog.has_schema_privilege(reader_oid, 'public', 'CREATE') THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'atom_v9_sim_web_reader schema authority is not exactly USAGE';
    END IF;

    -- Exactly SELECT on the resolution table.
    SELECT
        pg_catalog.has_table_privilege(reader_oid,
            'public.atom_v9_sim_resolutions', 'SELECT') AS can_select,
        pg_catalog.has_table_privilege(reader_oid,
            'public.atom_v9_sim_resolutions', 'INSERT') AS can_insert,
        pg_catalog.has_table_privilege(reader_oid,
            'public.atom_v9_sim_resolutions', 'UPDATE') AS can_update,
        pg_catalog.has_table_privilege(reader_oid,
            'public.atom_v9_sim_resolutions', 'DELETE') AS can_delete,
        pg_catalog.has_table_privilege(reader_oid,
            'public.atom_v9_sim_resolutions', 'TRUNCATE') AS can_truncate,
        pg_catalog.has_table_privilege(reader_oid,
            'public.atom_v9_sim_resolutions', 'REFERENCES') AS can_reference,
        pg_catalog.has_table_privilege(reader_oid,
            'public.atom_v9_sim_resolutions', 'TRIGGER') AS can_trigger
    INTO STRICT reader_privs;

    IF NOT reader_privs.can_select
       OR reader_privs.can_insert
       OR reader_privs.can_update
       OR reader_privs.can_delete
       OR reader_privs.can_truncate
       OR reader_privs.can_reference
       OR reader_privs.can_trigger THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'atom_v9_sim_web_reader authority on atom_v9_sim_resolutions is not exactly SELECT';
    END IF;

    -- No privilege of any kind on any other simulator relation, including
    -- atom_v9_sim_entries.
    FOR other_relation IN
        SELECT namespace.nspname || '.' || rel.relname
        FROM pg_catalog.pg_class AS rel
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = rel.relnamespace
        WHERE namespace.nspname = 'public'
          AND rel.relkind IN ('r', 'p', 'v', 'm', 'f')
          AND rel.relname <> 'atom_v9_sim_resolutions'
    LOOP
        IF pg_catalog.has_table_privilege(reader_oid, other_relation, 'SELECT')
           OR pg_catalog.has_table_privilege(reader_oid, other_relation, 'INSERT')
           OR pg_catalog.has_table_privilege(reader_oid, other_relation, 'UPDATE')
           OR pg_catalog.has_table_privilege(reader_oid, other_relation, 'DELETE')
           OR pg_catalog.has_table_privilege(reader_oid, other_relation, 'TRUNCATE')
           OR pg_catalog.has_table_privilege(reader_oid, other_relation, 'REFERENCES')
           OR pg_catalog.has_table_privilege(reader_oid, other_relation, 'TRIGGER') THEN
            RAISE EXCEPTION USING
                ERRCODE = '42501',
                MESSAGE = 'atom_v9_sim_web_reader must hold no privilege on ' || other_relation;
        END IF;
    END LOOP;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class AS rel
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = rel.relnamespace
        WHERE namespace.nspname = 'public'
          AND rel.relname = 'atom_v9_sim_entries'
          AND rel.relkind = 'r'
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '55000',
            MESSAGE = 'SIM-5W verification requires the existing atom_v9_sim_entries table';
    END IF;

    -- No sequence privilege.
    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class AS rel
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = rel.relnamespace
        WHERE namespace.nspname = 'public'
          AND rel.relkind = 'S'
          AND (
              pg_catalog.has_sequence_privilege(reader_oid, rel.oid, 'USAGE')
              OR pg_catalog.has_sequence_privilege(reader_oid, rel.oid, 'SELECT')
              OR pg_catalog.has_sequence_privilege(reader_oid, rel.oid, 'UPDATE')
          )
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'atom_v9_sim_web_reader must hold no sequence privilege';
    END IF;

    -- No function EXECUTE on any simulator function (the exact set migration
    -- 027 created and withheld from PUBLIC).
    FOREACH other_function IN ARRAY ARRAY[
        'public.atom_v9_sim_reject_mutation()',
        'public.atom_v9_sim4_lock_intent_admission_before()',
        'public.atom_v9_sim4_publish_intent_after()',
        'public.atom_v9_sim4_read_intent_admission_fence()',
        'public.atom_v9_sim4_compare_and_advance_checkpoint(bigint, bigint, bigint, text, bigint, timestamptz)'
    ]
    LOOP
        IF pg_catalog.has_function_privilege(reader_oid, other_function, 'EXECUTE') THEN
            RAISE EXCEPTION USING
                ERRCODE = '42501',
                MESSAGE = 'atom_v9_sim_web_reader must hold no EXECUTE on ' || other_function;
        END IF;
    END LOOP;

    -- Exactly one policy names the reader anywhere, and it is the SELECT
    -- policy on the resolution table.
    IF (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_policy AS pol
        WHERE pol.polroles @> ARRAY[reader_oid]
    ) <> 1
       OR NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_policy AS pol
        WHERE pol.polrelid = 'public.atom_v9_sim_resolutions'::regclass
          AND pol.polname = 'atom_v9_sim_resolutions_web_reader_select'
          AND pol.polcmd = 'r'
          AND pol.polpermissive
          AND pol.polroles = ARRAY[reader_oid]
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'atom_v9_sim_web_reader must be scoped by exactly one SELECT policy on atom_v9_sim_resolutions';
    END IF;

    -- Row-level security on the resolution table remains enabled and forced.
    IF NOT (
        SELECT rel.relrowsecurity AND rel.relforcerowsecurity
        FROM pg_catalog.pg_class AS rel
        WHERE rel.oid = 'public.atom_v9_sim_resolutions'::regclass
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'atom_v9_sim_resolutions row-level security is not enabled and forced';
    END IF;

    -- The three pre-existing policies on the resolution table are intact and
    -- no other policy was added.
    IF (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_policy AS pol
        WHERE pol.polrelid = 'public.atom_v9_sim_resolutions'::regclass
    ) <> 4
       OR (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.pg_policy AS pol
        WHERE pol.polrelid = 'public.atom_v9_sim_resolutions'::regclass
          AND pol.polname IN (
              'atom_v9_sim_resolutions_entry_runtime_select',
              'atom_v9_sim_resolutions_entry_runtime_insert',
              'atom_v9_sim_resolutions_owner_select'
          )
    ) <> 3 THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'pre-existing atom_v9_sim_resolutions policies changed';
    END IF;

    -- Pre-existing role authority on the resolution table is unchanged
    -- (migration 031's final state): entry runtime exactly SELECT/INSERT,
    -- publisher nothing, owner exactly SELECT.
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
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'atom_v9_sim_entry_runtime authority on atom_v9_sim_resolutions changed';
    END IF;

    IF pg_catalog.has_table_privilege(publisher_oid,
           'public.atom_v9_sim_resolutions', 'SELECT')
       OR pg_catalog.has_table_privilege(publisher_oid,
           'public.atom_v9_sim_resolutions', 'INSERT')
       OR pg_catalog.has_table_privilege(publisher_oid,
           'public.atom_v9_sim_resolutions', 'UPDATE')
       OR pg_catalog.has_table_privilege(publisher_oid,
           'public.atom_v9_sim_resolutions', 'DELETE') THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'atom_v9_sim_runtime authority on atom_v9_sim_resolutions changed';
    END IF;

    SELECT
        pg_catalog.has_table_privilege(owner_oid,
            'public.atom_v9_sim_resolutions', 'SELECT') AS can_select,
        pg_catalog.has_table_privilege(owner_oid,
            'public.atom_v9_sim_resolutions', 'INSERT') AS can_insert,
        pg_catalog.has_table_privilege(owner_oid,
            'public.atom_v9_sim_resolutions', 'UPDATE') AS can_update,
        pg_catalog.has_table_privilege(owner_oid,
            'public.atom_v9_sim_resolutions', 'DELETE') AS can_delete
    INTO STRICT owner_privs;

    IF NOT owner_privs.can_select
       OR owner_privs.can_insert
       OR owner_privs.can_update
       OR owner_privs.can_delete THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'atom_v9_sim_owner authority on atom_v9_sim_resolutions changed';
    END IF;

    IF (SELECT rel.relowner FROM pg_catalog.pg_class AS rel
         WHERE rel.oid = 'public.atom_v9_sim_resolutions'::regclass) <> owner_oid
       OR pg_catalog.has_schema_privilege(owner_oid, 'public', 'CREATE') THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'atom_v9_sim_resolutions ownership or owner schema authority changed';
    END IF;
END
$atom_v9_sim5w_verify_final_authority$;
