"""
Tabular file validator (TSV / CSV).

Validates tabular data files produced by BioFetch or any other source.

Checks performed:
  - File is parseable
  - Expected columns are present
  - No completely empty rows
  - Null / empty value rate per column
  - Row count is within expected range (optional)
  - TCGA sample ID format (optional, when column is detected)

Built-in profiles for common BioFetch outputs:
  - gtex      : tissueSiteDetailId, median, unit, geneSymbol
  - hpa       : gene, uniprot, ...
  - string    : stringId_A, stringId_B, preferredName_A, preferredName_B, score
  - gdc       : file_id, file_name, data_type, data_format, file_size

Usage:
    from biocheck.core.tabular import TabularValidator

    # Auto-detect columns
    report = TabularValidator().validate("gtex_expression.tsv")

    # Use a built-in profile
    report = TabularValidator().validate("gtex.tsv", profile="gtex")

    # Custom required columns
    report = TabularValidator().validate(
        "my_data.tsv",
        required_columns=["gene", "tissue", "value"],
        min_rows=1,
        max_rows=10000,
    )
    print(report.to_text())
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from biocheck.core.report import ValidationReport


# Built-in column profiles for known BioFetch outputs
_PROFILES: dict[str, list[str]] = {
    "gtex":   ["tissueSiteDetailId", "median", "unit", "geneSymbol"],
    "hpa":    ["gene", "uniprot"],
    "string": ["preferredName_A", "preferredName_B", "score"],
    "gdc":    ["file_id", "file_name", "data_type", "data_format"],
}

# TCGA barcode pattern: TCGA-XX-XXXX-XXX
_TCGA_PATTERN = re.compile(r"^TCGA-[A-Z0-9]{2}-[A-Z0-9]{4}-[A-Z0-9]{3}", re.IGNORECASE)

# Columns that likely contain TCGA barcodes
_TCGA_COLUMN_HINTS = {"sample_id", "case_id", "barcode", "submitter_id", "sample"}

# Threshold for flagging high null rate
_NULL_WARN_THRESHOLD = 0.2


class TabularValidator:
    """Validate TSV or CSV files."""

    def validate(
        self,
        file: str | Path,
        profile: str | None = None,
        required_columns: list[str] | None = None,
        min_rows: int | None = None,
        max_rows: int | None = None,
    ) -> ValidationReport:
        """Validate a tabular file.

        Args:
            file:             Path to a .tsv or .csv file.
            profile:          Built-in profile name: "gtex", "hpa", "string", "gdc".
            required_columns: Custom list of column names that must be present.
            min_rows:         Minimum expected number of data rows.
            max_rows:         Maximum expected number of data rows.

        Returns:
            A ValidationReport with statistics and any issues found.
        """
        path = Path(file)
        delimiter = "\t" if path.suffix.lower() in (".tsv", ".tab") else ","
        report = ValidationReport(file=str(path), file_type="TSV" if delimiter == "\t" else "CSV")

        # --- 1. Parse ---
        try:
            with open(path, newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh, delimiter=delimiter)
                try:
                    rows = list(reader)
                    columns = list(reader.fieldnames or [])
                except Exception as exc:
                    report.error("PARSE_ERROR", f"Could not read rows: {exc}")
                    return report
        except Exception as exc:
            report.error("PARSE_ERROR", f"Could not open file: {exc}")
            return report

        if not columns:
            report.error("NO_HEADER", "File has no header row or could not be parsed.")
            return report

        # --- 2. Statistics ---
        report.stats = {
            "rows":      len(rows),
            "columns":   len(columns),
            "column_names": ", ".join(columns),
        }

        if len(rows) == 0:
            report.error("EMPTY_FILE", "File has a header but no data rows.")
            return report

        # --- 3. Required columns ---
        expected = required_columns or _PROFILES.get(profile or "", [])
        for col in expected:
            if col not in columns:
                report.error(
                    "MISSING_COLUMN",
                    f"Required column '{col}' not found.",
                    location=f"profile={profile or 'custom'}",
                )

        # --- 4. Row count bounds ---
        if min_rows is not None and len(rows) < min_rows:
            report.error(
                "TOO_FEW_ROWS",
                f"Expected at least {min_rows} rows, found {len(rows)}.",
            )
        if max_rows is not None and len(rows) > max_rows:
            report.warning(
                "TOO_MANY_ROWS",
                f"Expected at most {max_rows} rows, found {len(rows)}.",
            )

        # --- 5. Null / empty values per column ---
        for col in columns:
            null_count = sum(
                1 for row in rows
                if row.get(col, "").strip() in ("", "None", "NA", "N/A", "null", "nan")
            )
            null_rate = null_count / len(rows)
            report.stats[f"null_rate_{col}"] = f"{null_rate:.1%}"
            if null_rate == 1.0:
                report.error(
                    "ALL_NULL_COLUMN",
                    f"Column '{col}' is entirely empty.",
                    location=col,
                )
            elif null_rate >= _NULL_WARN_THRESHOLD:
                report.warning(
                    "HIGH_NULL_RATE",
                    f"Column '{col}' has {null_rate:.0%} empty values ({null_count}/{len(rows)}).",
                    location=col,
                )

        # --- 6. Completely empty rows ---
        empty_rows = [
            i + 2  # +1 for header, +1 for 1-based
            for i, row in enumerate(rows)
            if all(v.strip() == "" for v in row.values())
        ]
        if empty_rows:
            report.warning(
                "EMPTY_ROWS",
                f"{len(empty_rows)} completely empty row(s) at lines: "
                + ", ".join(str(r) for r in empty_rows[:10])
                + (" ..." if len(empty_rows) > 10 else ""),
            )

        # --- 7. TCGA barcode validation (auto-detect) ---
        for col in columns:
            if col.lower() in _TCGA_COLUMN_HINTS:
                invalid = [
                    row[col] for row in rows
                    if row.get(col) and not _TCGA_PATTERN.match(row[col])
                ]
                if invalid:
                    sample = invalid[:3]
                    report.warning(
                        "INVALID_TCGA_BARCODE",
                        f"{len(invalid)} value(s) in '{col}' don't match TCGA barcode format "
                        f"(e.g. {sample}).",
                        location=col,
                    )
                break

        return report
