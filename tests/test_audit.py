import json
import tempfile
import unittest
from pathlib import Path

from opendata_csv_audit.audit import SchemaError, audit_csv, load_schema
from opendata_csv_audit.cli import main


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def create(self, content: str, name="data.csv"):
        file = self.root / name
        file.write_text(content, encoding="utf-8")
        return file

    def schema(self, value):
        file = self.root / "schema.json"
        file.write_text(json.dumps(value), encoding="utf-8")
        return load_schema(file)

    def test_clean_file(self):
        file = self.create("id,name\n1,Ana\n2,Bia\n")
        report = audit_csv(file)
        self.assertEqual((report.rows, report.errors, report.warnings), (2, 0, 0))
        self.assertEqual(len(report.sha256), 64)

    def test_empty_file(self):
        report = audit_csv(self.create(""))
        self.assertEqual(report.issues[0].code, "empty_file")

    def test_duplicate_and_empty_headers(self):
        report = audit_csv(self.create("id,id,\n1,2,3\n"))
        self.assertEqual({issue.code for issue in report.issues},
                         {"duplicate_header", "empty_header"})

    def test_inconsistent_column_count(self):
        report = audit_csv(self.create("id,name\n1,Ana\n2\n"))
        self.assertEqual(report.issues[0].code, "column_count")

    def test_schema_validation(self):
        schema = self.schema({
            "columns": {
                "id": {"type": "integer", "required": True},
                "date": {"type": "date", "required": True},
                "active": {"type": "boolean"},
                "amount": {"type": "number"},
                "status": {"allowed_values": ["open", "closed"]},
            },
            "unique_by": ["id"],
            "additional_columns": False,
        })
        file = self.create("id,date,active,amount,status\n"
                           "1,2026-11-02,true,1.5,open\n"
                           "1,2026-13-45,no,nan,bad\n"
                           ",2026-11-02,false,2,closed\n")
        codes = [issue.code for issue in audit_csv(file, schema=schema).issues]
        self.assertEqual(codes.count("duplicate_key"), 1)
        self.assertIn("invalid_type", codes)
        self.assertIn("disallowed_value", codes)
        self.assertIn("required_value", codes)

    def test_missing_and_extra_columns(self):
        schema = self.schema({"columns": {"id": {"required": True}},
                              "additional_columns": False})
        report = audit_csv(self.create("name\nAna\n"), schema=schema)
        self.assertEqual({issue.code for issue in report.issues},
                         {"missing_column", "additional_column"})

    def test_delimiter_and_utf8_bom(self):
        file = self.create("\ufeffid;name\n1;Renée\n")
        report = audit_csv(file)
        self.assertEqual(report.columns, ["id", "name"])
        self.assertEqual(report.delimiter, ";")

    def test_invalid_utf8(self):
        file = self.root / "bad.csv"
        file.write_bytes(b"id,name\n1,\xff\n")
        self.assertEqual(audit_csv(file).issues[0].code, "invalid_utf8")

    def test_malformed_quoting(self):
        report = audit_csv(self.create('id,name\n1,"unfinished\n'))
        self.assertIn("malformed_csv", [item.code for item in report.issues])

    def test_bad_schema(self):
        file = self.root / "schema.json"
        file.write_text('{"columns":{"id":{"type":"uuid"}}}', encoding="utf-8")
        with self.assertRaises(SchemaError):
            load_schema(file)

    def test_cli_exit_codes(self):
        good = self.create("id\n1\n")
        bad = self.create("id\n1,2\n", "bad.csv")
        self.assertEqual(main([str(good), "--fail-on", "never"]), 0)
        self.assertEqual(main([str(bad), "--format", "json"]), 1)
        self.assertEqual(main([str(self.root / "missing.csv")]), 2)


if __name__ == "__main__":
    unittest.main()
