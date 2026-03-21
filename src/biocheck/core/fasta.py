"""
FASTA validator.

Validates FASTA files containing DNA, RNA, or protein sequences.

Checks performed:
  - File is parseable as FASTA
  - No empty sequences
  - No duplicate sequence IDs
  - All characters are valid for the detected molecule type
  - Sequence length statistics (min, max, mean, total)
  - Warns if sequences seem unusually short

Usage:
    from biocheck.core.fasta import FastaValidator

    validator = FastaValidator()
    report = validator.validate("sequences.fasta")
    print(report.to_text())
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from statistics import mean

from Bio import SeqIO

from biocheck.core.report import ValidationReport


# Valid character sets (IUPAC)
_DNA_CHARS     = set("ACGTRYSWKMBDHVN-")
_RNA_CHARS     = set("ACGURYSWKMBDHVN-")
_PROTEIN_CHARS = set("ACDEFGHIKLMNPQRSTVWYBXZJUO*-")

# Ambiguous but biologically valid — warn, don't error
_DNA_AMBIGUOUS     = set("RYSWKMBDHVN")
_RNA_AMBIGUOUS     = set("RYSWKMBDHVN")
_PROTEIN_AMBIGUOUS = set("XBZJUO*")

_SHORT_SEQ_THRESHOLD = 10  # warn if shorter than this


def _detect_molecule(sequences: list[str]) -> str:
    """Detect molecule type from sequence content."""
    sample = "".join(sequences[:5]).upper()
    if not sample:
        return "unknown"
    u_ratio = sample.count("U") / len(sample)
    t_ratio = sample.count("T") / len(sample)
    if u_ratio > 0.01:
        return "rna"
    non_dna = set(sample) - _DNA_CHARS
    if non_dna:
        return "protein"
    return "dna"


class FastaValidator:
    """Validate FASTA sequence files."""

    def validate(self, file: str | Path) -> ValidationReport:
        """Run all checks on a FASTA file.

        Args:
            file: Path to the FASTA file.

        Returns:
            A ValidationReport with statistics and any issues found.
        """
        path = Path(file)
        report = ValidationReport(file=str(path), file_type="FASTA")

        # --- 1. Parse ---
        try:
            records = list(SeqIO.parse(path, "fasta"))
        except Exception as exc:
            report.error("PARSE_ERROR", f"Could not parse file: {exc}")
            return report

        if not records:
            report.error("EMPTY_FILE", "No sequences found in file.")
            return report

        sequences   = [str(r.seq).upper() for r in records]
        ids         = [r.id for r in records]
        lengths     = [len(s) for s in sequences]
        molecule    = _detect_molecule(sequences)

        # --- 2. Statistics ---
        report.file_type = f"FASTA ({molecule.upper()})"
        report.stats = {
            "sequences":        len(records),
            "molecule_type":    molecule,
            "min_length":       min(lengths),
            "max_length":       max(lengths),
            "mean_length":      round(mean(lengths), 1),
            "total_bases":      sum(lengths),
        }

        # --- 3. Duplicate IDs ---
        id_counts = Counter(ids)
        for seq_id, count in id_counts.items():
            if count > 1:
                report.error(
                    "DUPLICATE_ID",
                    f"ID appears {count} times.",
                    location=seq_id,
                )

        # --- 4. Per-sequence checks ---
        valid_chars = {"dna": _DNA_CHARS, "rna": _RNA_CHARS}.get(molecule, _PROTEIN_CHARS)

        for record, seq, length in zip(records, sequences, lengths):
            seq_id = record.id

            # Empty sequence
            if length == 0:
                report.error("EMPTY_SEQ", "Sequence is empty.", location=seq_id)
                continue

            # Short sequence warning
            if length < _SHORT_SEQ_THRESHOLD:
                report.warning(
                    "SHORT_SEQ",
                    f"Sequence is very short ({length} bp/aa).",
                    location=seq_id,
                )

            # Ambiguous characters — warn but don't fail
            ambiguous_chars = {"dna": _DNA_AMBIGUOUS, "rna": _RNA_AMBIGUOUS}.get(
                molecule, _PROTEIN_AMBIGUOUS
            )
            found_ambiguous = set(seq) & ambiguous_chars
            if found_ambiguous:
                count = sum(seq.count(c) for c in found_ambiguous)
                chars = ", ".join(sorted(found_ambiguous))
                report.warning(
                    "AMBIGUOUS_CHARS",
                    f"{count} ambiguous character(s) ({chars}) — sequence may be incomplete.",
                    location=seq_id,
                )

            # Truly invalid characters
            invalid = set(seq) - valid_chars
            if invalid:
                chars = ", ".join(sorted(invalid))
                report.error(
                    "INVALID_CHARS",
                    f"Invalid characters for {molecule.upper()}: {chars}",
                    location=seq_id,
                )

        return report
