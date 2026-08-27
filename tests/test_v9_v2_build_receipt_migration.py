from pathlib import Path


SQL = Path("migrations/022_create_v9_v2_build_receipts.sql").read_text()


def test_receipt_migration_is_additive_append_only_and_least_privilege():
    assert "CREATE TABLE public.atom_v9_v2_build_receipts" in SQL
    assert "DEFERRABLE INITIALLY DEFERRED" in SQL
    assert "reject_update_delete" in SQL and "reject_truncate" in SQL
    assert "ENABLE ROW LEVEL SECURITY" in SQL
    assert "FORCE ROW LEVEL SECURITY" in SQL
    assert "GRANT SELECT, INSERT" in SQL
