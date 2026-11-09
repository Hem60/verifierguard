from __future__ import annotations

from verifierguard.scanner import ScanReport


def render_text(report: ScanReport) -> str:
    out = [
        f"VerifierGuard scan: {report.task}",
        f"Verdict: {report.verdict.upper()}  Score: {report.score}/100",
    ]
    if not report.dynamic:
        out.append("(static checks only, no container was run)")
    elif report.oracle_passed is not None:
        out.append(f"Correct solution passes: {'yes' if report.oracle_passed else 'NO - task looks broken'}")
    for c in report.cheaters:
        mark = (
            "PASSED (gap)" if c.succeeded else "INCONCLUSIVE (infra errors)" if c.inconclusive else "blocked"
        )
        out.append(f"  cheater {c.name:<10} {mark}" + (f" - {c.evidence}" if c.evidence else ""))
    for f in report.findings:
        out.append(f"  [{f.severity}] {f.code} {f.title}" + (f" ({f.file})" if f.file else ""))
    for o in report.fixes:
        out.append(f"  fix for {o.fix.cheater} [{o.fix.source}]: {o.proof.status.upper()}")
        out.append(f"    gap: {o.fix.gap}")
        out.append(f"    fix: {o.fix.suggestion}")
        out.append(f"    proof: {o.proof.reason}")
        if o.proof.diff:
            out.append("    diff:")
            out.extend("      " + ln for ln in o.proof.diff.rstrip().splitlines())
    out.append("Note: a clean scan means no known gap, not no gap.")
    return "\n".join(out)
