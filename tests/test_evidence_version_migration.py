import re
import unittest
from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "006_add_evidence_source_versions.sql"
)


class EvidenceVersionMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = MIGRATION.read_text(encoding="utf-8")

    def test_adds_both_required_non_null_version_fields(self):
        for field in ("data_schema_version", "source_spec_version"):
            with self.subTest(field=field):
                self.assertRegex(
                    self.sql,
                    rf"(?is)ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+{field}"
                    rf"\s+text\s+NOT\s+NULL\s+DEFAULT\s+'legacy-unversioned'",
                )

    def test_preserves_all_existing_evidence(self):
        for forbidden in ("UPDATE", "DELETE", "DROP", "TRUNCATE"):
            with self.subTest(statement=forbidden):
                self.assertIsNone(re.search(rf"(?i)\b{forbidden}\b", self.sql))


if __name__ == "__main__":
    unittest.main()
