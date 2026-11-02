# Open Data CSV Audit

A small, dependency-free Python command-line tool that checks CSV/TSV files for
common data-quality problems before they are published or used in automated
data workflows. Works offline, including in GitHub Actions.

**Status:** early version (`0.1.0`). This project does not claim existing users,
downloads, community adoption, or compliance certification.

## Why this exists

Open datasets can contain missing headers, malformed rows, duplicate identifiers,
or values inconsistent with an expected data type. These problems can silently
break downstream processing. A simple quality gate can catch them early.

## Quick start

Requires Python 3.10 or newer. No third-party runtime packages are required.

```bash
python -m pip install .
csv-audit examples/sample.csv --schema examples/schema.json
csv-audit examples/sample.csv --schema examples/schema.json --format json
```

Exit status: `0` for an audit passing the selected threshold, `1` for detected
issues at that threshold, `2` for invalid invocation or unreadable input.
The default threshold is `--fail-on error`; alternatives are `warning` and `never`.

Use `--delimiter comma`, `--delimiter semicolon`, or `--delimiter tab` to force
a separator. Without this option, the tool guesses among those delimiters from
the first 8 KiB and falls back to comma if detection is inconclusive.

## What it checks

- Empty or repeated headers and absent schema columns.
- Rows with inconsistent field counts and malformed CSV quoting.
- UTF-8 (including UTF-8 files with a BOM).
- Required values, integers, finite decimal numbers, ISO `YYYY-MM-DD` dates,
  booleans (`true`/`false`), and allowed string values.
- Duplicate key combinations defined in a local JSON schema.
- Optional rejection of columns not included in the schema.
- Deterministic JSON output including SHA-256 of the source file, without
  reproducing source cell values.

## Schema

See [`examples/schema.json`](examples/schema.json). The supported format is:

```json
{
  "columns": {
    "id": {"type": "integer", "required": true},
    "name": {"type": "string", "required": true},
    "created_at": {"type": "date"},
    "status": {"allowed_values": ["open", "closed"]}
  },
  "unique_by": ["id"],
  "additional_columns": false
}
```

Supported types are `string`, `integer`, `number`, `date`, and `boolean`.
Empty values are allowed unless `required` is true. Field values are trimmed
for type, required, and uniqueness checks. This is a project-specific schema,
**not** the full W3C CSVW metadata vocabulary.

## Design and limitations

- Reads UTF-8 files only; rejects undecodable bytes.
- Reports issue metadata but never copies field values into the report.
- Streams records through Python's CSV parser, but duplicate-key detection
  retains keys in memory. For very large files, memory use may grow.
- Does not perform CSV formula sanitization, network fetches, semantic checks,
  or complete W3C CSVW validation.
- Intended for public or authorized datasets; do not treat audit success as
  evidence that a dataset is safe to publish.

## Run tests

```bash
python -m pip install .
python -m unittest discover -s tests -v
```

## Open technical references

This project is an independent implementation informed by public documentation:

- [RFC 4180 — Common Format and MIME Type for CSV](https://www.rfc-editor.org/info/rfc4180/)
- [W3C — Model for Tabular Data and Metadata on the Web](https://www.w3.org/TR/tabular-data-model/)
- [W3C — CSV on the Web Primer](https://www.w3.org/TR/tabular-data-primer/)
- [Python `csv` library documentation](https://docs.python.org/3/library/csv.html)

The standards bodies do not endorse this project. See [CONTRIBUTING.md](CONTRIBUTING.md)
for ways to improve it. Licensed under [MIT](LICENSE).
