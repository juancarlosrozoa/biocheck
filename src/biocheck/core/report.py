"""
Validation report dataclasses.

A ValidationReport collects issues and statistics from one or more
validators and renders them as plain text, JSON, or TSV.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Severity(str, Enum):
    ERROR   = "ERROR"
    WARNING = "WARNING"
    INFO    = "INFO"


@dataclass
class Issue:
    severity: Severity
    code: str
    message: str
    location: str = ""   # e.g. sequence ID, line number, chain ID


@dataclass
class ValidationReport:
    """Collects issues and statistics from validation runs."""

    file: str = ""
    file_type: str = ""
    stats: dict = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Building
    # ------------------------------------------------------------------

    def add(self, severity: Severity, code: str, message: str, location: str = "") -> None:
        self.issues.append(Issue(severity, code, message, location))

    def error(self, code: str, message: str, location: str = "") -> None:
        self.add(Severity.ERROR, code, message, location)

    def warning(self, code: str, message: str, location: str = "") -> None:
        self.add(Severity.WARNING, code, message, location)

    def info(self, code: str, message: str, location: str = "") -> None:
        self.add(Severity.INFO, code, message, location)

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    @property
    def is_valid(self) -> bool:
        return not any(i.severity == Severity.ERROR for i in self.issues)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == Severity.WARNING]

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def to_text(self) -> str:
        lines = [
            f"File     : {self.file}",
            f"Type     : {self.file_type}",
            f"Result   : {'PASS' if self.is_valid else 'FAIL'}",
            "",
            "--- Statistics ---",
        ]
        for k, v in self.stats.items():
            lines.append(f"  {k:<30} {v}")
        if self.issues:
            lines += ["", "--- Issues ---"]
            for issue in self.issues:
                loc = f" [{issue.location}]" if issue.location else ""
                lines.append(f"  [{issue.severity.value}] {issue.code}{loc}: {issue.message}")
        else:
            lines += ["", "No issues found."]
        return "\n".join(lines)

    def to_json(self) -> str:
        return json.dumps({
            "file": self.file,
            "file_type": self.file_type,
            "valid": self.is_valid,
            "stats": self.stats,
            "issues": [
                {"severity": i.severity.value, "code": i.code,
                 "location": i.location, "message": i.message}
                for i in self.issues
            ],
        }, indent=2)

    def to_tsv(self) -> str:
        lines = ["severity\tcode\tlocation\tmessage"]
        for i in self.issues:
            lines.append(f"{i.severity.value}\t{i.code}\t{i.location}\t{i.message}")
        return "\n".join(lines)

    def save(self, output: str | Path, fmt: str = "text") -> Path:
        out = Path(output)
        out.parent.mkdir(parents=True, exist_ok=True)
        renderers = {"text": self.to_text, "json": self.to_json, "tsv": self.to_tsv}
        if fmt not in renderers:
            raise ValueError(f"Unknown format '{fmt}'. Choose from: text, json, tsv")
        out.write_text(renderers[fmt](), encoding="utf-8")
        return out.resolve()
