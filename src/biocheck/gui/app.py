"""
BioCheck GUI — drag-and-drop biological file validator.
"""

from __future__ import annotations

import re
import tempfile
import threading
import webbrowser
from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog
from tkinterdnd2 import TkinterDnD, DND_FILES

from biocheck.core.fasta import FastaValidator
from biocheck.core.structure import StructureValidator
from biocheck.core.tabular import TabularValidator
from biocheck.core.html_report import render_html
from biocheck.core.report import ValidationReport, Severity


# ── File type detection ────────────────────────────────────────────────────

_FASTA_EXT     = {".fasta", ".fa", ".faa", ".ffn", ".fna"}
_STRUCTURE_EXT = {".pdb", ".cif", ".mmcif"}
_TABULAR_EXT   = {".tsv", ".csv", ".tab"}
_ALL_EXT       = _FASTA_EXT | _STRUCTURE_EXT | _TABULAR_EXT

_PROFILES = ["auto", "gtex", "hpa", "string", "gdc"]

_STATUS_COLORS = {
    "PASS": "#22c55e",
    "WARN": "#f59e0b",
    "FAIL": "#ef4444",
    "..."  : "#60a5fa",
}


def _detect_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in _FASTA_EXT:     return "FASTA"
    if ext in _STRUCTURE_EXT: return "Structure"
    if ext in _TABULAR_EXT:   return "Tabular"
    return "Unknown"


def _validate(path: Path, profile: str | None) -> ValidationReport:
    ext = path.suffix.lower()
    if ext in _FASTA_EXT:
        return FastaValidator().validate(path)
    if ext in _STRUCTURE_EXT:
        return StructureValidator().validate(path)
    if ext in _TABULAR_EXT:
        return TabularValidator().validate(path, profile=profile or None)
    r = ValidationReport(file=str(path), file_type="Unknown")
    r.error("UNKNOWN_TYPE", f"Unsupported extension '{path.suffix}'.")
    return r


# ── File row widget ────────────────────────────────────────────────────────

class FileRow(ctk.CTkFrame):
    """One row in the file list — shows filename, type, status, issue count."""

    def __init__(self, master, path: Path, **kwargs):
        super().__init__(master, fg_color="#1e293b", corner_radius=8, **kwargs)
        self.path = path

        self.columnconfigure(1, weight=1)

        # Status dot
        self._dot = ctk.CTkLabel(self, text="●", text_color="#60a5fa",
                                  font=ctk.CTkFont(size=14), width=24)
        self._dot.grid(row=0, column=0, padx=(10, 4), pady=8)

        # Filename
        self._name = ctk.CTkLabel(self, text=path.name, anchor="w",
                                   font=ctk.CTkFont(size=13, weight="bold"))
        self._name.grid(row=0, column=1, padx=4, pady=8, sticky="w")

        # Type badge
        self._type = ctk.CTkLabel(self, text=_detect_type(path),
                                   text_color="#94a3b8",
                                   font=ctk.CTkFont(size=11))
        self._type.grid(row=0, column=2, padx=8, pady=8)

        # Status label
        self._status = ctk.CTkLabel(self, text="pending",
                                     text_color="#60a5fa",
                                     font=ctk.CTkFont(size=12))
        self._status.grid(row=0, column=3, padx=(4, 14), pady=8)

        self.report: ValidationReport | None = None

    def set_validating(self):
        self._dot.configure(text_color="#60a5fa")
        self._status.configure(text="validating…", text_color="#60a5fa")

    def set_result(self, report: ValidationReport):
        self.report = report
        if not report.is_valid:
            label, color = "FAIL", _STATUS_COLORS["FAIL"]
            detail = f"{len(report.errors)} error(s)"
        elif report.warnings:
            label, color = "WARN", _STATUS_COLORS["WARN"]
            detail = f"{len(report.warnings)} warning(s)"
        else:
            label, color = "PASS", _STATUS_COLORS["PASS"]
            detail = "No issues"
        self._dot.configure(text_color=color)
        self._status.configure(text=f"{label} — {detail}", text_color=color)


# ── Main application ───────────────────────────────────────────────────────

class BioCheckApp(TkinterDnD.Tk):

    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("BioCheck")
        self.geometry("760x600")
        self.minsize(600, 480)
        self.resizable(True, True)

        self._rows: dict[str, FileRow] = {}   # path → FileRow
        self._reports: list[ValidationReport] = []
        self._html_path: str | None = None

        self._build_ui()

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # ── Top bar ──
        top = ctk.CTkFrame(self, fg_color="#0f172a", corner_radius=0)
        top.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        top.columnconfigure(3, weight=1)

        ctk.CTkLabel(top, text="BioCheck",
                     font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, padx=16, pady=12, sticky="w")

        ctk.CTkLabel(top, text="Profile:", text_color="#64748b").grid(
            row=0, column=1, padx=(16, 4), pady=12)

        self._profile_var = ctk.StringVar(value="auto")
        ctk.CTkOptionMenu(top, values=_PROFILES, variable=self._profile_var,
                          width=100).grid(row=0, column=2, padx=4, pady=12)

        # ── Drop zone ──
        drop = ctk.CTkFrame(self, fg_color="#1e293b", corner_radius=12,
                             border_width=2, border_color="#334155")
        drop.grid(row=1, column=0, sticky="nsew", padx=16, pady=(12, 8))
        drop.columnconfigure(0, weight=1)
        drop.rowconfigure(0, weight=1)

        self._drop_label = ctk.CTkLabel(
            drop,
            text="Drop files here\nor click Browse to add files",
            text_color="#475569",
            font=ctk.CTkFont(size=14),
        )
        self._drop_label.grid(row=0, column=0, pady=40)

        # Register drag & drop on the frame and the label
        for widget in (drop, self._drop_label):
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self._on_drop)
            widget.dnd_bind("<<DragEnter>>", lambda e: drop.configure(border_color="#3b82f6"))
            widget.dnd_bind("<<DragLeave>>", lambda e: drop.configure(border_color="#334155"))

        self._drop_frame = drop

        # Scrollable file list (hidden until files added)
        self._scroll = ctk.CTkScrollableFrame(drop, fg_color="transparent")
        self._scroll.drop_target_register(DND_FILES)
        self._scroll.dnd_bind("<<Drop>>", self._on_drop)

        # ── Bottom bar ──
        bot = ctk.CTkFrame(self, fg_color="#1e293b", corner_radius=0,
                           border_width=1, border_color="#334155")
        bot.grid(row=2, column=0, sticky="ew", padx=0, pady=(8, 0))
        bot.columnconfigure(2, weight=1)

        ctk.CTkButton(bot, text="Browse…", width=110, height=36,
                      command=self._browse).grid(
            row=0, column=0, padx=(16, 4), pady=12)

        ctk.CTkButton(bot, text="Clear", width=90, height=36,
                      fg_color="#334155", hover_color="#475569",
                      command=self._clear).grid(
            row=0, column=1, padx=4, pady=12)

        self._validate_btn = ctk.CTkButton(
            bot, text="Validate", width=120, height=36,
            command=self._run_validation)
        self._validate_btn.grid(row=0, column=3, padx=4, pady=12)

        self._html_btn = ctk.CTkButton(
            bot, text="Open HTML Report", width=160, height=36,
            fg_color="#1d4ed8", hover_color="#1e40af",
            state="disabled", command=self._open_html)
        self._html_btn.grid(row=0, column=4, padx=(4, 16), pady=12)

        # ── Log ──
        self._log = ctk.CTkTextbox(self, height=110, state="disabled",
                                    font=ctk.CTkFont(family="Courier", size=11),
                                    fg_color="#0f172a", corner_radius=0)
        self._log.grid(row=3, column=0, sticky="ew", padx=0, pady=0)

    # ── File management ────────────────────────────────────────────────────

    def _on_drop(self, event):
        # tkinterdnd2 returns paths as a space-separated string;
        # paths with spaces are wrapped in braces: {C:/my folder/file.fasta}
        raw = event.data
        paths = re.findall(r"\{([^}]+)\}|(\S+)", raw)
        for braced, plain in paths:
            p = Path(braced or plain)
            if p.is_file():
                self._add_file(p)
        self._drop_frame.configure(border_color="#334155")

    def _browse(self):
        paths = filedialog.askopenfilenames(
            title="Select files to validate",
            filetypes=[
                ("All supported", "*.fasta *.fa *.faa *.ffn *.fna *.pdb *.cif *.mmcif *.tsv *.csv *.tab"),
                ("FASTA",      "*.fasta *.fa *.faa *.ffn *.fna"),
                ("Structure",  "*.pdb *.cif *.mmcif"),
                ("Tabular",    "*.tsv *.csv *.tab"),
                ("All files",  "*.*"),
            ],
        )
        for p in paths:
            self._add_file(Path(p))

    def _add_file(self, path: Path):
        key = str(path)
        if key in self._rows:
            return
        self._drop_label.grid_forget()
        self._scroll.grid(row=0, column=0, sticky="nsew",
                           padx=8, pady=8)
        row = FileRow(self._scroll, path)
        row.pack(fill="x", pady=3)
        self._rows[key] = row

    def _clear(self):
        for row in self._rows.values():
            row.destroy()
        self._rows.clear()
        self._reports.clear()
        self._html_path = None
        self._html_btn.configure(state="disabled")
        self._scroll.grid_forget()
        self._drop_label.grid(row=0, column=0, pady=40)
        self._log_clear()

    # ── Validation ────────────────────────────────────────────────────────

    def _run_validation(self):
        if not self._rows:
            self._log_write("No files to validate. Click Browse to add files.\n")
            return
        self._validate_btn.configure(state="disabled")
        self._html_btn.configure(state="disabled")
        self._reports.clear()
        threading.Thread(target=self._validate_all, daemon=True).start()

    def _validate_all(self):
        profile_val = self._profile_var.get()
        profile = None if profile_val == "auto" else profile_val

        for key, row in self._rows.items():
            self.after(0, row.set_validating)
            try:
                report = _validate(row.path, profile)
            except Exception as exc:
                report = ValidationReport(file=key, file_type="Error")
                report.error("UNEXPECTED_ERROR", str(exc))
            self._reports.append(report)
            self.after(0, row.set_result, report)
            self._log_result(report)

        # Generate HTML
        tmp = tempfile.NamedTemporaryFile(
            suffix=".html", prefix="biocheck_", delete=False)
        tmp.close()
        self._html_path = tmp.name
        render_html(self._reports, self._html_path)

        self.after(0, self._on_done)

    def _on_done(self):
        self._validate_btn.configure(state="normal")
        self._html_btn.configure(state="normal")
        n_fail = sum(1 for r in self._reports if not r.is_valid)
        n_warn = sum(1 for r in self._reports if r.is_valid and r.warnings)
        n_pass = len(self._reports) - n_fail - n_warn
        self._log_write(
            f"\nDone — {n_pass} PASS  {n_warn} WARN  {n_fail} FAIL\n"
        )

    # ── HTML report ───────────────────────────────────────────────────────

    def _open_html(self):
        if self._html_path:
            webbrowser.open(f"file:///{self._html_path}")

    # ── Log helpers ───────────────────────────────────────────────────────

    def _log_result(self, report: ValidationReport):
        name = Path(report.file).name
        if not report.is_valid:
            msg = f"FAIL  {name} — {len(report.errors)} error(s)\n"
        elif report.warnings:
            msg = f"WARN  {name} — {len(report.warnings)} warning(s)\n"
        else:
            msg = f"PASS  {name}\n"
        self.after(0, self._log_write, msg)

    def _log_write(self, text: str):
        self._log.configure(state="normal")
        self._log.insert("end", text)
        self._log.see("end")
        self._log.configure(state="disabled")

    def _log_clear(self):
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")


def main():
    app = BioCheckApp()
    app.mainloop()


if __name__ == "__main__":
    main()
