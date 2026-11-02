"""Dependency-free CSV audit engine.

Reports deliberately exclude cell values to avoid leaking source data in logs.
This is a pragmatic subset of checks, not a full W3C CSVW implementation.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


VALID_TYPES = {"string", "integer", "number", "date", "boolean"}
INT_PATTERN = re.compile(r"[+-]?[0-9]+\Z")


class SchemaError(ValueError):
    """The user-provided audit schema is invalid."""


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    line: int
    column: str | None
    message: str


@dataclass
class AuditReport:
    file: str
    sha256: str
    delimiter: str
    columns: list[str] = field(default_factory=list)
    rows: int = 0
    issues: list[Issue] = field(default_factory=list)

    def add(self, severity: str, code: str, line: int, message: str,
            column: str | None = None) -> None:
        self.issues.append(Issue(severity, code, line, column, message))

    @property
    def errors(self) -> int:
        return sum(item.severity == "error" for item in self.issues)

    @property
    def warnings(self) -> int:
        return sum(item.severity == "warning" for item in self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "sha256": self.sha256,
            "delimiter": "\\t" if self.delimiter == "\t" else self.delimiter,
            "columns": self.columns,
            "rows": self.rows,
            "errors": self.errors,
            "warnings": self.warnings,
            "issues": [asdict(issue) for issue in self.issues],
        }


def load_schema(path: str | Path) -> dict[str, Any]:
    """Load and validate the intentionally small project-specific JSON schema."""
    try:
        schema = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SchemaError(f"Cannot read schema: {exc}") from exc

    if not isinstance(schema, dict) or not isinstance(schema.get("columns"), dict):
        raise SchemaError("Schema requires a 'columns' object")
    if not schema["columns"]:
        raise SchemaError("Schema 'columns' cannot be empty")
    for name, spec in schema["columns"].items():
        if not isinstance(name, str) or not name.strip():
            raise SchemaError("Column names must be non-empty strings")
        if not isinstance(spec, dict) or spec.get("type", "string") not in VALID_TYPES:
            raise SchemaError(f"Invalid type for column '{name}'")
        if "required" in spec and not isinstance(spec["required"], bool):
            raise SchemaError(f"'required' must be boolean for '{name}'")
        if "allowed_values" in spec and (
            not isinstance(spec["allowed_values"], list)
            or not all(isinstance(value, str) for value in spec["allowed_values"])
        ):
            raise SchemaError(f"'allowed_values' must be a list of strings for '{name}'")
    keys = schema.get("unique_by", [])
    if not isinstance(keys, list) or not all(isinstance(key, str) for key in keys):
        raise SchemaError("'unique_by' must be an array of column names")
    if len(keys) != len(set(keys)) or any(key not in schema["columns"] for key in keys):
        raise SchemaError("'unique_by' contains unknown or repeated column names")
    if "additional_columns" in schema and not isinstance(schema["additional_columns"], bool):
        raise SchemaError("'additional_columns' must be boolean")
    return schema


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _detect_delimiter(sample: str) -> str:
    if not sample:
        return ","
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
    except csv.Error:
        # Fallback is explicit and documented: users can set --delimiter.
        return ","


def _type_is_valid(value: str, kind: str) -> bool:
    if kind == "string":
        return True
    if kind == "integer":
        return bool(INT_PATTERN.fullmatch(value))
    if kind == "number":
        try:
            return Decimal(value).is_finite()
        except InvalidOperation:
            return False
    if kind == "date":
        try:
            date.fromisoformat(value)
            return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))
        except ValueError:
            return False
    if kind == "boolean":
        return value.lower() in {"true", "false"}
    return False


def audit_csv(path: str | Path, *, schema: dict[str, Any] | None = None,
              delimiter: str | None = None) -> AuditReport:
    """Audit a UTF-8 CSV/TSV file. No source cell values are written to reports.

    The caller may pass a schema returned by ``load_schema``. ``delimiter``
    can be a comma, semicolon, or tab; otherwise it is inferred from a sample.
    """
    source = Path(path)
    if delimiter is not None and delimiter not in {",", ";", "\t"}:
        raise ValueError("delimiter must be comma, semicolon, or tab")
    if schema is not None and (
        not isinstance(schema, dict) or not isinstance(schema.get("columns"), dict)
    ):
        raise SchemaError("Pass a schema returned by load_schema")

    report = AuditReport(file=str(source), sha256=_sha256(source), delimiter=delimiter or ",")
    try:
        with source.open("r", encoding="utf-8-sig", newline="") as stream:
            sample = stream.read(8192)
            stream.seek(0)
            report.delimiter = delimiter or _detect_delimiter(sample)
            reader = csv.reader(stream, delimiter=report.delimiter, strict=True)
            try:
                raw_header = next(reader, None)
            except csv.Error as exc:
                report.add("error", "malformed_csv", reader.line_num, str(exc))
                return report
            if raw_header is None:
                report.add("error", "empty_file", 1, "CSV file has no header")
                return report

            report.columns = [name.strip() for name in raw_header]
            for index, name in enumerate(report.columns):
                if not name:
                    report.add("error", "empty_header", 1,
                               f"Header at position {index + 1} is empty")
                elif report.columns.count(name) > 1 and name not in report.columns[:index]:
                    report.add("error", "duplicate_header", 1,
                               "Column name occurs more than once", name)

            known = set(report.columns)
            if schema:
                for name in schema["columns"]:
                    if name not in known:
                        report.add("error", "missing_column", 1,
                                   "Schema column is absent", name)
                if schema.get("additional_columns", True) is False:
                    for name in report.columns:
                        if name not in schema["columns"]:
                            report.add("error", "additional_column", 1,
                                       "Column is not declared in schema", name)

            unique_indices: list[int] = []
            if schema and schema.get("unique_by"):
                if all(key in known for key in schema["unique_by"]):
                    unique_indices = [report.columns.index(key) for key in schema["unique_by"]]
            seen_keys: set[tuple[str, ...]] = set()

            try:
                for row in reader:
                    line = reader.line_num
                    report.rows += 1
                    if not row:
                        report.add("warning", "blank_row", line, "Blank row")
                        continue
                    if len(row) != len(report.columns):
                        report.add("error", "column_count", line,
                                   f"Expected {len(report.columns)} fields; got {len(row)}")
                        continue
                    if schema:
                        for index, name in enumerate(report.columns):
                            if name not in schema["columns"]:
                                continue
                            spec = schema["columns"][name]
                            value = row[index].strip()
                            if not value:
                                if spec.get("required", False):
                                    report.add("error", "required_value", line,
                                               "Required field is empty", name)
                                continue
                            if not _type_is_valid(value, spec.get("type", "string")):
                                report.add("error", "invalid_type", line,
                                           f"Expected {spec.get('type', 'string')}", name)
                            if "allowed_values" in spec and value not in spec["allowed_values"]:
                                report.add("error", "disallowed_value", line,
                                           "Value is not in allowed_values", name)
                    if unique_indices:
                        key = tuple(row[index].strip() for index in unique_indices)
                        if all(key):
                            if key in seen_keys:
                                report.add("error", "duplicate_key", line,
                                           "Repeated unique_by key")
                            seen_keys.add(key)
            except csv.Error as exc:
                report.add("error", "malformed_csv", reader.line_num, str(exc))
    except UnicodeError:
        report.add("error", "invalid_utf8", 0, "File is not valid UTF-8")
    return report
