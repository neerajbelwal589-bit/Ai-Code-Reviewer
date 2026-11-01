import re
from radon.complexity import cc_visit
from radon.metrics import mi_visit

def analyze_complexity(code: str, language: str):
    if language == "Python":
        return _analyze_python(code)
    return _analyze_heuristic(code)

def _analyze_python(code: str):
    try:
        blocks = cc_visit(code)
    except SyntaxError as e:
        return {
            "method": "radon",
            "average_complexity": 0,
            "rating": "N/A",
            "details": [],
            "maintainability_index": None,
            "error": f"Syntax error, could not analyze: {e}",
        }
    if not blocks:
        return {
            "method": "radon",
            "average_complexity": 1,
            "rating": "A",
            "details": [],
            "maintainability_index": _safe_mi(code),
        }
    details = [
        {"name": b.name, "complexity": b.complexity, "rank": _rank_letter(b.complexity)}
        for b in blocks
    ]
    avg = sum(b.complexity for b in blocks) / len(blocks)

    return {
        "method": "radon",
        "average_complexity": round(avg, 2),
        "rating": _rank_letter(avg),
        "details": details,
        "maintainability_index": _safe_mi(code),
    }


def _safe_mi(code: str):
    try:
        return round(mi_visit(code, multi=True), 2)
    except Exception:
        return None


def _rank_letter(complexity: float):
    if complexity <= 5:
        return "A"
    if complexity <= 10:
        return "B"
    if complexity <= 20:
        return "C"
    if complexity <= 30:
        return "D"
    if complexity <= 40:
        return "E"
    return "F"


def _analyze_heuristic(code: str):
    branch_keywords = re.findall(
        r"\b(if|for|while|case|catch|else if|switch)\b", code
    )
    branch_count = len(branch_keywords)

    max_depth = 0
    current_depth = 0
    for char in code:
        if char == "{":
            current_depth += 1
            max_depth = max(max_depth, current_depth)
        elif char == "}":
            current_depth = max(0, current_depth - 1)

    # Simple weighted score: branching contributes more than raw nesting
    estimated_complexity = 1 + branch_count + (max_depth * 0.5)

    if estimated_complexity <= 5:
        rating = "Low"
    elif estimated_complexity <= 12:
        rating = "Medium"
    else:
        rating = "High"

    return {
        "method": "heuristic",
        "average_complexity": round(estimated_complexity, 2),
        "rating": rating,
        "details": [
            {"name": "branch_count", "complexity": branch_count, "rank": "-"},
            {"name": "max_nesting_depth", "complexity": max_depth, "rank": "-"},
        ],
        "maintainability_index": None,
    }
