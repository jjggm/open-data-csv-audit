"""Checks for common structural and data-quality problems in CSV files."""

from .audit import AuditReport, Issue, SchemaError, audit_csv, load_schema

__all__ = ["AuditReport", "Issue", "SchemaError", "audit_csv", "load_schema"]
__version__ = "0.1.0"
