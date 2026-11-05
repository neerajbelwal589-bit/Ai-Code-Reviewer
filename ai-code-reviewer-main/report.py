def build_report(result, complexity, code, language):
    """Return the whole review as one Markdown text (for copy / download)."""
    lines = []
    score10 = result.get("overall_score", 0) or 0
    lines.append("# AI Code Review Report")
    lines.append("")
    lines.append(f"**Language:** {language}")
    lines.append(f"**Overall score:** {round(float(score10) * 10)}/100")
    lines.append("")

    if result.get("summary"):
        lines += ["## Summary", result["summary"], ""]

    cats = result.get("category_scores") or {}
    if cats:
        lines.append("## Category scores")
        for key, value in cats.items():
            lines.append(f"- {key.replace('_', ' ').title()}: {value}/100")
        lines.append("")

    bugs = result.get("bugs", [])
    lines.append("## Bugs")
    if not bugs:
        lines.append("No bugs found.")
    for b in bugs:
        if isinstance(b, dict):
            lines.append(
                f"- Line {b.get('line', 'N/A')} ({b.get('severity', 'info')}): {b.get('description', '')}"
            )
        else:
            lines.append(f"- {b}")
    lines.append("")

    improvements = result.get("improvements", [])
    if improvements:
        lines.append("## Improvements")
        for it in improvements:
            if isinstance(it, dict):
                lines.append(f"- {it.get('title', '')}: {it.get('detail', '')}")
            else:
                lines.append(f"- {it}")
        lines.append("")

    changes = result.get("changes", [])
    if changes:
        lines.append("## What was fixed")
        for ch in changes:
            if isinstance(ch, dict):
                lines.append(f"- Line {ch.get('line', '?')}: {ch.get('reason', '')}")
                lines.append(f"  - Before: `{ch.get('before', '')}`")
                lines.append(f"  - After: `{ch.get('after', '')}`")
        lines.append("")

    opt = result.get("optimization") or {}
    if opt.get("current_time"):
        lines.append("## Complexity and optimization")
        lines.append(f"- Your code: time {opt.get('current_time')}, space {opt.get('current_space', 'N/A')}")
        if opt.get("status") == "can_be_optimized":
            lines.append(f"- Faster approach: time {opt.get('best_time')}, space {opt.get('best_space')}")
            if opt.get("explanation"):
                lines += ["", opt["explanation"]]
        else:
            lines.append("- Already an efficient approach.")
        lines.append("")
    elif complexity:
        lines += ["## Complexity", f"Average: {complexity.get('average_complexity')} (rating {complexity.get('rating')})", ""]

    lines += ["## Original code", f"```{language.lower()}", code, "```", ""]
    if result.get("improved_code"):
        lines += ["## Fixed code", f"```{language.lower()}", result["improved_code"], "```", ""]
    if opt.get("optimized_code"):
        lines += ["## Optimized code", f"```{language.lower()}", opt["optimized_code"], "```", ""]

    return "\n".join(lines)
