-- Append-only proof that every published V2 state had one complete offline build.
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '15s';

CREATE TABLE public.atom_v9_v2_build_receipts (
    receipt_sha256 text PRIMARY KEY CHECK (receipt_sha256 ~ '^[0-9a-f]{64}$'),
    state_id text UNIQUE NOT NULL REFERENCES public.atom_v9_v2_states(state_id)
        DEFERRABLE INITIALLY DEFERRED,
    state_as_of double precision NOT NULL,
    receipt_json jsonb NOT NULL CHECK (jsonb_typeof(receipt_json) = 'object'),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER atom_v9_v2_build_receipts_reject_update_delete
BEFORE UPDATE OR DELETE ON public.atom_v9_v2_build_receipts
FOR EACH ROW EXECUTE FUNCTION public.atom_v9_v2_reject_mutation();
CREATE TRIGGER atom_v9_v2_build_receipts_reject_truncate
BEFORE TRUNCATE ON public.atom_v9_v2_build_receipts
FOR EACH STATEMENT EXECUTE FUNCTION public.atom_v9_v2_reject_mutation();

ALTER TABLE public.atom_v9_v2_build_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.atom_v9_v2_build_receipts FORCE ROW LEVEL SECURITY;
REVOKE ALL ON public.atom_v9_v2_build_receipts FROM PUBLIC, anon, authenticated,
    service_role, atom_v9_sim_runtime, atom_v9_proof_owner, atom_v9_v4_runtime;
GRANT SELECT, INSERT ON public.atom_v9_v2_build_receipts TO atom_v9_v4_runtime;
CREATE POLICY atom_v9_v2_build_receipts_runtime_select
ON public.atom_v9_v2_build_receipts FOR SELECT TO atom_v9_v4_runtime USING (true);
CREATE POLICY atom_v9_v2_build_receipts_runtime_insert
ON public.atom_v9_v2_build_receipts FOR INSERT TO atom_v9_v4_runtime WITH CHECK (true);
