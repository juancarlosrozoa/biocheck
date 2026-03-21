"""BioCheck CLI."""

import click
from pathlib import Path

from biocheck.core.fasta import FastaValidator
from biocheck.core.structure import StructureValidator
from biocheck.core.tabular import TabularValidator
from biocheck.core.html_report import render_html


@click.group()
@click.version_option(package_name="biocheck")
def cli():
    """BioCheck — validate biological sequence and structure files."""


# ── fasta ──────────────────────────────────────────────────────────────────

@cli.command("fasta")
@click.argument("file", type=click.Path(exists=True, dir_okay=False))
@click.option("--output", "-o", default=None, help="Save report to file.")
@click.option("--format", "fmt", default="text",
              type=click.Choice(["text", "json", "tsv"]),
              help="Report format (default: text).")
def validate_fasta(file, output, fmt):
    """Validate a FASTA sequence file."""
    report = FastaValidator().validate(file)
    _print_and_save(report, output, fmt)


# ── structure ──────────────────────────────────────────────────────────────

@cli.command("structure")
@click.argument("file", type=click.Path(exists=True, dir_okay=False))
@click.option("--output", "-o", default=None, help="Save report to file.")
@click.option("--format", "fmt", default="text",
              type=click.Choice(["text", "json", "tsv"]),
              help="Report format (default: text).")
def validate_structure(file, output, fmt):
    """Validate a PDB or mmCIF structure file."""
    report = StructureValidator().validate(file)
    _print_and_save(report, output, fmt)


# ── table ──────────────────────────────────────────────────────────────────

@cli.command("table")
@click.argument("file", type=click.Path(exists=True, dir_okay=False))
@click.option("--profile", "-p", default=None,
              type=click.Choice(["gtex", "hpa", "string", "gdc"]),
              help="Built-in column profile to validate against.")
@click.option("--columns", "-c", default=None,
              help="Comma-separated list of required column names.")
@click.option("--min-rows", default=None, type=int, help="Minimum expected rows.")
@click.option("--max-rows", default=None, type=int, help="Maximum expected rows.")
@click.option("--output", "-o", default=None, help="Save report to file.")
@click.option("--format", "fmt", default="text",
              type=click.Choice(["text", "json", "tsv"]),
              help="Report format (default: text).")
def validate_table(file, profile, columns, min_rows, max_rows, output, fmt):
    """Validate a TSV or CSV tabular file."""
    required = [c.strip() for c in columns.split(",")] if columns else None
    report = TabularValidator().validate(
        file,
        profile=profile,
        required_columns=required,
        min_rows=min_rows,
        max_rows=max_rows,
    )
    _print_and_save(report, output, fmt)


# ── report ─────────────────────────────────────────────────────────────────

@cli.command("report")
@click.argument("files", nargs=-1, required=True,
                type=click.Path(exists=True, dir_okay=False))
@click.option("--output", "-o", default="biocheck_report.html",
              help="Output HTML file (default: biocheck_report.html).")
@click.option("--profile", "-p", default=None,
              type=click.Choice(["gtex", "hpa", "string", "gdc"]),
              help="TSV profile applied to all tabular files.")
def batch_report(files, output, profile):
    """Validate multiple files and generate a combined HTML report.

    Auto-detects file type by extension:
    .fasta / .fa / .faa / .ffn → FASTA validator
    .pdb / .cif / .mmcif       → Structure validator
    .tsv / .csv / .tab         → Tabular validator
    """
    _FASTA_EXT     = {".fasta", ".fa", ".faa", ".ffn", ".fna"}
    _STRUCTURE_EXT = {".pdb", ".cif", ".mmcif"}
    _TABULAR_EXT   = {".tsv", ".csv", ".tab"}

    reports = []
    for f in files:
        path = Path(f)
        ext  = path.suffix.lower()
        if ext in _FASTA_EXT:
            reports.append(FastaValidator().validate(path))
        elif ext in _STRUCTURE_EXT:
            reports.append(StructureValidator().validate(path))
        elif ext in _TABULAR_EXT:
            reports.append(TabularValidator().validate(path, profile=profile))
        else:
            click.echo(f"[SKIP] Unknown extension for {path.name} — skipping.")
            continue
        label, _ = ("FAIL", None) if not reports[-1].is_valid else ("PASS", None)
        click.echo(f"  {'FAIL' if not reports[-1].is_valid else 'WARN' if reports[-1].warnings else 'PASS'}  {path.name}")

    if reports:
        render_html(reports, output)
        click.echo(f"\nReport: {output}")


# ── gui ────────────────────────────────────────────────────────────────────

@cli.command("gui")
def launch_gui():
    """Launch the graphical interface."""
    from biocheck.gui.app import main
    main()


# ── helpers ────────────────────────────────────────────────────────────────

def _print_and_save(report, output, fmt):
    renderers = {"text": report.to_text, "json": report.to_json, "tsv": report.to_tsv}
    text = renderers[fmt]()
    click.echo(text)
    if output:
        report.save(output, fmt)
        click.echo(f"\nReport saved to {output}")
    raise SystemExit(0 if report.is_valid else 1)
