"""Command-line interface."""

from __future__ import annotations

import argparse
import json
import sys

from .audit import SchemaError, audit_csv, load_schema


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="csv-audit", description="Audit UTF-8 CSV/TSV files without external dependencies"
    )
    parser.add_argument("file", help="Local CSV or TSV path")
    parser.add_argument("--schema", help="Path to a JSON validation schema")
    parser.add_argument("--delimiter", choices=["comma", "semicolon", "tab"],
                        help="Override automatic delimiter detection")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--fail-on", choices=["error", "warning", "never"], default="error")
    args = parser.parse_args(argv)

    sep = {"comma": ",", "semicolon": ";", "tab": "\t"}.get(args.delimiter)
    try:
        schema = load_schema(args.schema) if args.schema else None
        report = audit_csv(args.file, schema=schema, delimiter=sep)
    except (OSError, ValueError, SchemaError) as exc:
        print(f"csv-audit: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"File: {report.file}")
        print(f"SHA-256: {report.sha256}")
        print(f"Rows: {report.rows} | Errors: {report.errors} | Warnings: {report.warnings}")
        for issue in report.issues:
            at = f"line {issue.line}" + (f", {issue.column}" if issue.column else "")
            print(f"{issue.severity.upper()}: {issue.code} ({at}): {issue.message}")

    if args.fail_on == "never":
        return 0
    if args.fail_on == "warning":
        return int(bool(report.errors or report.warnings))
    return int(bool(report.errors))


if __name__ == "__main__":
    raise SystemExit(main())
