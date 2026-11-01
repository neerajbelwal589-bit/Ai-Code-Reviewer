import json
import re

LANGUAGE_CONFIG={
    "Python":{"ace_mode":"python","ext":".py","supports_radon":True},
    "C++":{"ace_mode":"c_cpp","ext":".cpp","supports_radon":False},
    "Java":{"ace_mode":"java","ext":".java","supports_radon":False}
}

SEVERITY_STYLE={
    "critical": {"emoji": "🔴", "label": "Critical"},
    "warning":  {"emoji": "🟡", "label": "Warning"},
    "info":     {"emoji": "🔵", "label": "Info"},
}

def safe_json_parse(raw_text: str) -> dict:
    if not raw_text:
        return _fallback_response("Empty response from model.")

    cleaned = raw_text.strip()

    # Strip markdown code fences if present
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    # If there's extra chatter, try to isolate the outermost {...} block
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)

    try:
        data = json.loads(cleaned)
        return _normalize_response(data)
    except json.JSONDecodeError as e:
        return _fallback_response(f"Could not parse model response: {e}")


def _normalize_response(data: dict) -> dict:
    """Ensure every expected key exists so app.py never KeyErrors."""
    data.setdefault("bugs", [])
    data.setdefault("improvements", [])
    data.setdefault("complexity_notes", "No complexity notes provided.")
    data.setdefault("overall_score", 5)
    data.setdefault("improved_code", "")
    data.setdefault("summary", "")

    # Clamp score into 1-10 range defensively
    try:
        score = float(data["overall_score"])
        data["overall_score"] = max(1, min(10, score))
    except (TypeError, ValueError):
        data["overall_score"] = 5

    return data


def _fallback_response(error_message: str) -> dict:
    return {
        "bugs": [],
        "improvements": [],
        "complexity_notes": "N/A",
        "overall_score": 0,
        "improved_code": "",
        "summary": error_message,
        "error": True,
    }


def score_color(score: float) -> str:
    """Return a color for progress bars / metrics based on score."""
    if score >= 8:
        return "green"
    if score >= 5:
        return "orange"
    return "red"


def score_label(score: float) -> str:
    if score >= 8:
        return "Excellent"
    if score >= 6:
        return "Good"
    if score >= 4:
        return "Needs Work"
    return "Poor"


def format_bug_entry(bug: dict) -> str:
    """Render a single bug dict into a readable markdown string."""
    severity = str(bug.get("severity", "info")).lower()
    style = SEVERITY_STYLE.get(severity, SEVERITY_STYLE["info"])
    line = bug.get("line", "N/A")
    desc = bug.get("description", "No description provided.")
    return f"{style['emoji']} **{style['label']}** (Line {line}): {desc}"


def format_improvement_entry(item: dict) -> str:
    title = item.get("title", "Suggestion")
    detail = item.get("detail", "")
    return f"💡 **{title}**\n\n{detail}"