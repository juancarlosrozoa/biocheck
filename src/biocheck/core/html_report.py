"""
HTML report generator.

Renders one or more ValidationReport objects as a single self-contained
HTML file — no external dependencies, works offline.

Usage:
    from biocheck.core.html_report import render_html

    reports = [report1, report2, report3]
    render_html(reports, "validation_report.html")
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from biocheck.core.report import ValidationReport, Severity


# ── Colour tokens ──────────────────────────────────────────────────────────

_PASS_COLOR    = "#22c55e"   # green
_WARN_COLOR    = "#f59e0b"   # amber
_FAIL_COLOR    = "#ef4444"   # red
_INFO_COLOR    = "#60a5fa"   # blue


def _status(report: ValidationReport) -> tuple[str, str]:
    """Return (label, colour) for a report."""
    if not report.is_valid:
        return "FAIL", _FAIL_COLOR
    if report.warnings:
        return "WARN", _WARN_COLOR
    return "PASS", _PASS_COLOR


def _severity_color(sev: Severity) -> str:
    return {
        Severity.ERROR:   _FAIL_COLOR,
        Severity.WARNING: _WARN_COLOR,
        Severity.INFO:    _INFO_COLOR,
    }.get(sev, "#9ca3af")


def _issue_rows(report: ValidationReport) -> str:
    if not report.issues:
        return '<tr><td colspan="4" style="color:#6b7280;font-style:italic">No issues found</td></tr>'
    rows = []
    for issue in report.issues:
        color = _severity_color(issue.severity)
        rows.append(f"""
        <tr>
          <td><span style="color:{color};font-weight:600">{issue.severity.value}</span></td>
          <td><code>{issue.code}</code></td>
          <td style="color:#9ca3af">{issue.location or "—"}</td>
          <td>{issue.message}</td>
        </tr>""")
    return "\n".join(rows)


def _stat_rows(report: ValidationReport) -> str:
    rows = []
    for k, v in report.stats.items():
        # Skip per-column null rates in the summary — too verbose
        if k.startswith("null_rate_") and len(report.stats) > 8:
            continue
        rows.append(f'<tr><td style="color:#9ca3af">{k}</td><td>{v}</td></tr>')
    return "\n".join(rows)


def _card(report: ValidationReport, idx: int) -> str:
    label, color = _status(report)
    filename = Path(report.file).name
    n_errors   = len(report.errors)
    n_warnings = len(report.warnings)

    badge_parts = []
    if n_errors:
        badge_parts.append(f'<span style="color:{_FAIL_COLOR}">{n_errors} error{"s" if n_errors>1 else ""}</span>')
    if n_warnings:
        badge_parts.append(f'<span style="color:{_WARN_COLOR}">{n_warnings} warning{"s" if n_warnings>1 else ""}</span>')
    if not badge_parts:
        badge_parts.append(f'<span style="color:{_PASS_COLOR}">No issues</span>')
    badges = " &nbsp;·&nbsp; ".join(badge_parts)

    detail_id = f"detail-{idx}"

    return f"""
  <div class="card">
    <div class="card-header" onclick="toggle('{detail_id}')">
      <span class="status-dot" style="background:{color}"></span>
      <span class="filename">{filename}</span>
      <span class="file-type">{report.file_type}</span>
      <span class="badges">{badges}</span>
      <span class="chevron" id="chev-{detail_id}">▶</span>
    </div>
    <div class="card-body" id="{detail_id}">
      <p style="color:#6b7280;font-size:0.85rem;margin:0 0 1rem">{report.file}</p>
      <div class="two-col">
        <div>
          <h4>Statistics</h4>
          <table class="inner-table">
            {_stat_rows(report)}
          </table>
        </div>
        <div>
          <h4>Issues</h4>
          <table class="inner-table">
            <thead>
              <tr>
                <th>Severity</th><th>Code</th><th>Location</th><th>Message</th>
              </tr>
            </thead>
            <tbody>
              {_issue_rows(report)}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>"""


def render_html(reports: list[ValidationReport], output: str | Path) -> Path:
    """Render a list of ValidationReport objects as a single HTML file.

    Args:
        reports: List of ValidationReport objects.
        output:  Destination .html file path.

    Returns:
        Resolved Path of the written file.
    """
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)

    n_pass = sum(1 for r in reports if r.is_valid and not r.warnings)
    n_warn = sum(1 for r in reports if r.is_valid and r.warnings)
    n_fail = sum(1 for r in reports if not r.is_valid)
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cards_html = "\n".join(_card(r, i) for i, r in enumerate(reports))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>BioCheck Validation Report</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #0f172a;
      color: #e2e8f0;
      min-height: 100vh;
      padding: 2rem;
    }}
    h1 {{ font-size: 1.6rem; font-weight: 700; margin-bottom: 0.25rem; }}
    h4 {{ font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em;
          color: #64748b; margin-bottom: 0.75rem; }}
    .subtitle {{ color: #64748b; font-size: 0.9rem; margin-bottom: 2rem; }}

    /* Summary bar */
    .summary {{
      display: flex; gap: 1.5rem; margin-bottom: 2rem; flex-wrap: wrap;
    }}
    .summary-pill {{
      padding: 0.5rem 1.25rem; border-radius: 9999px;
      font-weight: 600; font-size: 0.9rem;
    }}

    /* Cards */
    .card {{
      background: #1e293b; border-radius: 0.75rem;
      margin-bottom: 0.75rem; overflow: hidden;
      border: 1px solid #334155;
    }}
    .card-header {{
      display: flex; align-items: center; gap: 0.75rem;
      padding: 0.9rem 1.25rem; cursor: pointer;
      user-select: none;
    }}
    .card-header:hover {{ background: #263347; }}
    .status-dot {{
      width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0;
    }}
    .filename {{ font-weight: 600; font-size: 0.95rem; }}
    .file-type {{
      background: #334155; color: #94a3b8;
      font-size: 0.75rem; padding: 0.15rem 0.5rem; border-radius: 4px;
    }}
    .badges {{ margin-left: auto; font-size: 0.85rem; }}
    .chevron {{ color: #64748b; font-size: 0.75rem; transition: transform 0.2s; }}
    .chevron.open {{ transform: rotate(90deg); }}

    /* Card body */
    .card-body {{ display: none; padding: 1.25rem; border-top: 1px solid #334155; }}
    .card-body.open {{ display: block; }}
    .two-col {{
      display: grid; grid-template-columns: 1fr 2fr; gap: 1.5rem;
    }}
    @media (max-width: 700px) {{ .two-col {{ grid-template-columns: 1fr; }} }}

    /* Inner tables */
    .inner-table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
    .inner-table th {{
      text-align: left; color: #64748b; font-weight: 500;
      padding: 0.3rem 0.5rem; border-bottom: 1px solid #334155;
    }}
    .inner-table td {{ padding: 0.3rem 0.5rem; vertical-align: top; }}
    .inner-table tr:hover td {{ background: #263347; }}
    code {{ background: #334155; padding: 0.1rem 0.35rem; border-radius: 3px;
             font-size: 0.8rem; }}

    footer {{ text-align: center; color: #475569; font-size: 0.8rem; margin-top: 2rem; }}
  </style>
</head>
<body>
  <h1>BioCheck Validation Report</h1>
  <p class="subtitle">Generated {generated} &nbsp;·&nbsp; {len(reports)} file{"s" if len(reports) != 1 else ""} validated</p>

  <div class="summary">
    <div class="summary-pill" style="background:#166534;color:#bbf7d0">
      ✓ &nbsp;{n_pass} PASS
    </div>
    <div class="summary-pill" style="background:#78350f;color:#fde68a">
      ⚠ &nbsp;{n_warn} WARN
    </div>
    <div class="summary-pill" style="background:#7f1d1d;color:#fecaca">
      ✕ &nbsp;{n_fail} FAIL
    </div>
  </div>

  {cards_html}

  <footer>BioCheck &nbsp;·&nbsp; MIT License</footer>

  <script>
    function toggle(id) {{
      const body = document.getElementById(id);
      const chev = document.getElementById('chev-' + id);
      body.classList.toggle('open');
      chev.classList.toggle('open');
    }}
  </script>
</body>
</html>"""

    out.write_text(html, encoding="utf-8")
    print(f"HTML report saved to {out}")
    return out.resolve()
