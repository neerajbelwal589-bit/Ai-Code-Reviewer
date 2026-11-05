import html
import streamlit as st

CATEGORIES = [
    ("security", "Security"),
    ("best_practices", "Best practices"),
    ("maintainability", "Maintainability"),
    ("error_handling", "Error handling"),
    ("performance", "Performance"),
]


def _color(value):
    if value >= 70:
        return "#34d399"   # green
    if value >= 40:
        return "#fbbf24"   # amber
    return "#f87171"       # red


def _clamp(value):
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return 0


def _bug_text(bug):
    if isinstance(bug, dict):
        line = html.escape(str(bug.get("line", "N/A")))
        sev = html.escape(str(bug.get("severity", "info")).title())
        desc = html.escape(str(bug.get("description", "")))
        return f"Line {line} · {sev}", desc
    return "Code issue", html.escape(str(bug))


def render_dashboard(result, complexity=None):
    """Top-of-results dashboard: overall score, category bars, summary, critical issues."""
    score10 = result.get("overall_score", 0) or 0
    overall = _clamp(float(score10) * 10)
    color = _color(overall)
    bugs = result.get("bugs", [])
    improvements = result.get("improvements", [])
    rating = complexity["rating"] if complexity else "N/A"

    parts = []

    # --- Overall score ---
    parts.append(
        f'<div class="dash-head">'
        f'<div class="score-ring" style="--pct:{overall};--c:{color}">'
        f'<div class="score-inner"><span class="score-num">{overall}</span>'
        f'<span class="score-of">/100</span></div></div>'
        f'<div class="dash-head-text"><h2>Overall score</h2>'
        f'<p>{len(bugs)} bugs · {len(improvements)} improvements · complexity {html.escape(str(rating))}</p>'
        f'</div></div>'
    )

    # --- Category bars ---
    cats = result.get("category_scores") or {}
    cells = []
    for key, label in CATEGORIES:
        if key not in cats:
            continue
        v = _clamp(cats[key])
        c = _color(v)
        cells.append(
            f'<div class="cat" style="--c:{c}">'
            f'<div class="cat-row"><span>{label}</span><span>{v}/100</span></div>'
            f'<div class="bar"><div class="bar-fill" style="width:{v}%"></div></div>'
            f'</div>'
        )
    if cells:
        parts.append('<div class="cat-grid">' + "".join(cells) + "</div>")

    # --- Summary ---
    if result.get("summary"):
        parts.append(
            '<div class="summary-card"><h4>Summary</h4>'
            f'<p>{html.escape(str(result["summary"]))}</p></div>'
        )

    # --- Critical issues ---
    critical = [
        b for b in bugs
        if isinstance(b, dict) and str(b.get("severity", "")).lower() in ("critical", "high")
    ]
    parts.append('<h4 class="issues-title">Critical issues</h4>')
    if critical:
        for b in critical:
            title, desc = _bug_text(b)
            parts.append(
                f'<div class="issue"><div class="issue-title">{title}</div>'
                f'<div class="issue-desc">{desc}</div></div>'
            )
    else:
        parts.append('<div class="issue ok">No critical issues found.</div>')

    st.markdown('<div class="dash">' + "".join(parts) + "</div>", unsafe_allow_html=True)
