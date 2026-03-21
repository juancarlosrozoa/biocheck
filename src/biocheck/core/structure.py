"""
Structure file validator.

Validates PDB and mmCIF structure files.

Checks performed:
  - File is parseable by Biopython
  - Number of models, chains, residues, atoms
  - Presence of HETATM records (ligands/water)
  - Missing residues detection (gaps in residue numbering)
  - Alternate conformations (altloc)
  - Warns on very low atom counts

Usage:
    from biocheck.core.structure import StructureValidator

    validator = StructureValidator()
    report = validator.validate("structure.cif")
    print(report.to_text())
"""

from __future__ import annotations

from pathlib import Path

from Bio.PDB import MMCIFParser, PDBParser
from Bio.PDB.PDBExceptions import PDBConstructionWarning

import warnings

from biocheck.core.report import ValidationReport


def _parser_for(path: Path):
    ext = path.suffix.lower()
    if ext in (".cif", ".mmcif"):
        return MMCIFParser(QUIET=True), "mmCIF"
    return PDBParser(QUIET=True), "PDB"


class StructureValidator:
    """Validate PDB or mmCIF structure files."""

    def validate(self, file: str | Path) -> ValidationReport:
        """Run all checks on a structure file.

        Args:
            file: Path to a .pdb or .cif file.

        Returns:
            A ValidationReport with statistics and any issues found.
        """
        path = Path(file)
        parser, fmt = _parser_for(path)
        report = ValidationReport(file=str(path), file_type=fmt)

        # --- 1. Parse ---
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", PDBConstructionWarning)
            try:
                structure = parser.get_structure(path.stem, path)
            except Exception as exc:
                report.error("PARSE_ERROR", f"Could not parse file: {exc}")
                return report
            for w in caught:
                report.warning("PARSE_WARNING", str(w.message))

        models  = list(structure.get_models())
        chains  = list(structure.get_chains())
        residues = [r for r in structure.get_residues() if r.id[0] == " "]
        hetatms  = [r for r in structure.get_residues() if r.id[0] != " " and r.id[0] != "W"]
        waters   = [r for r in structure.get_residues() if r.id[0] == "W"]
        atoms    = list(structure.get_atoms())

        # --- 2. Statistics ---
        report.stats = {
            "models":           len(models),
            "chains":           len(chains),
            "residues":         len(residues),
            "hetatm_ligands":   len(hetatms),
            "water_molecules":  len(waters),
            "atoms":            len(atoms),
            "chain_ids":        ", ".join(c.id for c in chains),
        }

        # --- 3. Checks ---
        if len(atoms) == 0:
            report.error("NO_ATOMS", "Structure contains no atoms.")
            return report

        if len(atoms) < 10:
            report.warning("FEW_ATOMS", f"Unusually low atom count: {len(atoms)}")

        if len(models) > 1:
            report.info("MULTI_MODEL", f"Structure has {len(models)} models (NMR ensemble or trajectory).")

        # Alternate conformations
        altloc_atoms = [a for a in atoms if a.altloc not in (" ", "A", "")]
        if altloc_atoms:
            report.warning(
                "ALTLOC",
                f"{len(altloc_atoms)} atoms have alternate conformations (altloc). "
                "Only the first conformation is typically used.",
            )

        # Missing residues per chain (gaps in numbering)
        for chain in chains:
            std_residues = [r for r in chain.get_residues() if r.id[0] == " "]
            if len(std_residues) < 2:
                continue
            seq_nums = [r.id[1] for r in std_residues]
            gaps = [
                (seq_nums[i], seq_nums[i + 1])
                for i in range(len(seq_nums) - 1)
                if seq_nums[i + 1] - seq_nums[i] > 1
            ]
            if gaps:
                gap_str = ", ".join(f"{a}→{b}" for a, b in gaps[:5])
                if len(gaps) > 5:
                    gap_str += f" ... ({len(gaps)} total)"
                report.warning(
                    "MISSING_RESIDUES",
                    f"Gaps in residue numbering suggest missing residues: {gap_str}",
                    location=f"chain {chain.id}",
                )

        return report
