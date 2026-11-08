from __future__ import annotations

from html import escape
from pathlib import Path

from verifierguard.scanner import ScanReport

CSS = (
    "body{font-family:system-ui,sans-serif;max-width:860px;margin:2rem auto;padding:0 1rem;color:#1b1f23}"
    "h1{margin-bottom:0}table{border-collapse:collapse;width:100%;margin:.5rem 0 1.5rem}"
    "th,td{border:1px solid #d0d7de;padding:.4rem .6rem;text-align:left;vertical-align:top}"
    "th{background:#f6f8fa}.weak,.broken{color:#b42318}.solid{color:#067647}"
    "pre{background:#f6f8fa;padding:.75rem;overflow:auto}"
)


def render_html(report: ScanReport) -> str:
    parts = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        f"<title>VerifierGuard report: {escape(report.task)}</title><style>{CSS}</style></head><body>",
        f"<h1>VerifierGuard report: {escape(report.task)}</h1>",
        f"<p>Verdict: <b class='{escape(report.verdict)}'>{escape(report.verdict.upper())}</b>"
        f" &middot; score {report.score}/100</p>",
    ]
    if not report.dynamic:
        parts.append("<p><i>Static checks only: no container was run.</i></p>")
    elif report.oracle_passed is not None:
        parts.append(f"<p>Correct solution passes: <b>{'yes' if report.oracle_passed else 'NO'}</b></p>")

    if report.cheaters:
        parts.append(
            "<h2>Cheater agents</h2><table><tr><th>Cheater</th><th>Result</th>"
            "<th>Meaning / evidence</th></tr>"
        )
        for c in report.cheaters:
            result = "PASSED (gap)" if c.succeeded else "blocked"
            extra = f"{escape(c.meaning)}<br><small>{escape(c.evidence)}</small>" if c.succeeded else ""
            parts.append(f"<tr><td>{escape(c.name)}</td><td>{result}</td><td>{extra}</td></tr>")
        parts.append("</table>")

    if report.findings:
        parts.append("<h2>Static findings</h2><table><tr><th>Code</th><th>Severity</th><th>Finding</th></tr>")
        for f in report.findings:
            where = f" ({escape(f.file)})" if f.file else ""
            parts.append(
                f"<tr><td>{f.code}</td><td>{f.severity}</td>"
                f"<td><b>{escape(f.title)}</b>{where}<br>{escape(f.detail)}</td></tr>"
            )
        parts.append("</table>")

    if report.fixes:
        parts.append("<h2>Suggested fixes</h2>")
        for o in report.fixes:
            parts.append(
                f"<h3>{escape(o.fix.cheater)} &mdash; {escape(o.proof.status.replace('_', ' '))}</h3>"
                f"<p><b>Gap:</b> {escape(o.fix.gap)}<br><b>Fix:</b> {escape(o.fix.suggestion)}<br>"
                f"<b>Proof:</b> {escape(o.proof.reason)}</p>"
            )
            if o.proof.diff:
                parts.append(f"<pre>{escape(o.proof.diff)}</pre>")

    parts.append("<p><small>A clean scan means no known gap, not no gap.</small></p></body></html>")
    return "".join(parts)


def write_html(report: ScanReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(report), encoding="utf-8")
