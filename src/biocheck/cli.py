"""BioCheck CLI."""

import click
from pathlib import Path

from biocheck.core.fasta import FastaValidator
from biocheck.core.structure import StructureValidator
from biocheck.core.tabular import TabularValidator


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


# ── helpers ────────────────────────────────────────────────────────────────

def _print_and_save(report, output, fmt):
    renderers = {"text": report.to_text, "json": report.to_json, "tsv": report.to_tsv}
    text = renderers[fmt]()
    click.echo(text)
    if output:
        report.save(output, fmt)
        click.echo(f"\nReport saved to {output}")
    raise SystemExit(0 if report.is_valid else 1)
