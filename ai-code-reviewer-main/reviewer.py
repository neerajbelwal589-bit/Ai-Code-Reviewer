import os
import hashlib
from dotenv import load_dotenv

load_dotenv()
from google import genai
from utils import safe_json_parse
from google.genai import types
from syntax_checker import check_syntax
from static_analysis import analyze_static

# Pehla model khatam ho jaye (quota/404) to agla try hoga
MODELS = ["gemini-3.5-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite"]

# Same code dobara aaye to API call nahi hogi
_cache = {}


def _key(code, language, kind):
    return hashlib.md5(f"{kind}|{language}|{code}".encode()).hexdigest()


SYSTEM_PROMPT = """
You are a friendly senior engineer reviewing code written by a BEGINNER.

You ALWAYS respond with ONLY ONE VALID JSON OBJECT.
Never return markdown. Never return ```json. Never explain outside the JSON.

Schema:

{
  "summary": "",
  "bugs": [
    {"line": "", "severity": "", "description": ""}
  ],
  "improvements": [
    {"title": "", "detail": ""}
  ],
  "changes": [
    {"line": "", "before": "", "after": "", "reason": ""}
  ],
  "complexity_notes": "",
  "optimization": {
    "status": "optimal or can_be_optimized",
    "current_time": "",
    "current_space": "",
    "best_time": "",
    "best_space": "",
    "explanation": "",
    "optimized_code": ""
  },
  "improved_code": "",
  "category_scores": {
    "security": 0,
    "best_practices": 0,
    "maintainability": 0,
    "error_handling": 0,
    "performance": 0
  },
  "overall_score": 8
}

Rules for improved_code (VERY IMPORTANT):
- Make the SMALLEST change that fixes the problem. Keep the same structure,
  function names and variable names as the original code.
- Keep it simple and easy for a beginner to read.
- Do NOT add advanced features: no type hints, no typing imports, no
  decorators, no classes, no new libraries, unless the original code
  already uses them.
- If the code is already correct, only do tiny cleanups (spacing, naming,
  a short comment). Never rewrite it into something longer or fancier.
- If the code has errors (syntax or logic), FIX them so the code runs correctly.
- At every place you changed, add a short comment like: # FIXED: reason
- improved_code must be COMPLETE, runnable code.

Rules for changes:
- One entry per fix. "before" is the original line, "after" is the new line,
  "reason" explains in simple words (1 sentence) what was wrong.
- If nothing was wrong, return an empty list.

Rules for optimization (VERY IMPORTANT):
- Decide if the code is correct but SLOWER than the standard better approach
  (example: brute force nested loops O(n^2) where a hash map gives O(n)).
- If a clearly better approach exists: status = "can_be_optimized", fill
  current_time/current_space (Big-O of the user's code) and best_time/best_space
  (Big-O of your optimized version), and write optimized_code.
- If the code is already efficient (or only tiny micro-optimizations exist):
  status = "optimal", best_* same as current_*, optimized_code = "".
- explanation: 3 to 5 short sentences for a beginner. Say what is slow, then
  explain the faster idea with a simple everyday example. No jargon without
  explaining it.
- optimized_code: keep the SAME function name and parameters, keep it simple,
  and add a short comment on each important line explaining what it does.
  It must be complete and runnable.
- improved_code stays the small safe cleanup/fix. Do NOT put the optimized
  approach inside improved_code.
- The "summary" must clearly say if the code is correct but can be optimized.
- Do not give the top score (9-10) to correct code that can be optimized.

Rules for category_scores:
- Each value is an integer from 0 to 100 for that quality area.
- Be honest and consistent with the bugs you list. Examples: SQL injection or
  hardcoded passwords make security very low; no try/except or no input checks
  make error_handling low; brute force on a big problem makes performance low.
- For tiny harmless code, do not punish security or error_handling too much.
- The average of the five should roughly match overall_score x 10.

Other rules:
- Don't invent bugs.
- Write bug descriptions and reasons in simple, beginner-friendly English.
- Syntax errors are reported separately: don't repeat them in "bugs",
  but DO fix them in improved_code and list them in "changes".
"""


def get_client():
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY not found.")

    return genai.Client(api_key=api_key)


def call_gemini(contents, config):
    """Models ko ek ek karke try karta hai. Quota khatam ho to agla model."""
    client = get_client()
    last_error = None
    for model in MODELS:
        try:
            return client.models.generate_content(
                model=model, contents=contents, config=config
            )
        except Exception as e:
            last_error = e
            msg = str(e)
            # quota khatam ya model nahi mila -> agla model try karo
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg or "404" in msg:
                continue
            raise
    raise last_error


def friendly_error(e):
    """Lamba raw error ki jagah chhota message dikhao."""
    msg = str(e)
    if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
        return "Daily AI limit khatam ho gaya hai. Thodi der baad try karein."
    return f"Gemini API Error: {msg}"


def build_user_prompt(code, language, syntax_bugs=None):
    syntax_note = ""
    if syntax_bugs:
        lines = []
        for b in syntax_bugs:
            if isinstance(b, dict):
                lines.append(f"- Line {b.get('line', '?')}: {b.get('description', '')}")
            else:
                lines.append(f"- {b}")
        syntax_note = (
            "\nThe syntax checker found these errors. Fix them in improved_code "
            "and list each fix in changes:\n" + "\n".join(lines) + "\n"
        )

    return f"""
Review this {language} code.
{syntax_note}
Code:

```{language.lower()}
{code}
```

Return your review strictly as the JSON schema described in your instructions."""


def review_code(code, language):
    if not code or not code.strip():
        return {
            "bugs": [],
            "improvements": [],
            "changes": [],
            "complexity_notes": "N/A",
            "overall_score": 0,
            "improved_code": "",
            "summary": "No code was provided to review.",
            "error": True,
        }

    # 0) Cache check: same code pehle review ho chuka hai to wahi result do
    key = _key(code, language, "review")
    if key in _cache:
        return _cache[key]

    # 1) Syntax check (no longer stops the review)
    syntax_result = check_syntax(code, language)
    has_syntax_error = not syntax_result["valid"]
    syntax_bugs = syntax_result["bugs"] if has_syntax_error else []

    # 2) Static analysis only makes sense on code that parses
    static_bugs = [] if has_syntax_error else analyze_static(code, language)

    # 3) Gemini review (also fixes syntax errors)
    try:
        response = call_gemini(
            build_user_prompt(code, language, syntax_bugs),
            {
                "system_instruction": SYSTEM_PROMPT,
                "temperature": 0.2,
                "response_mime_type": "application/json",
            },
        )
        result = safe_json_parse(response.text)

    except Exception as e:
        if has_syntax_error:
            # Still show the syntax errors even if Gemini failed
            return {
                "summary": "Syntax error detected. Could not generate a fix right now.",
                "bugs": syntax_bugs,
                "improvements": [],
                "changes": [],
                "complexity_notes": "Fix syntax errors before reviewing.",
                "improved_code": "",
                "overall_score": 1,
            }
        return {
            "bugs": static_bugs,
            "improvements": [],
            "changes": [],
            "complexity_notes": "N/A",
            "overall_score": 0,
            "improved_code": "",
            "summary": friendly_error(e),
            "error": True,
        }

    # 4) Merge everything
    result["bugs"] = syntax_bugs + static_bugs + result.get("bugs", [])
    result.setdefault("changes", [])
    if not isinstance(result.get("optimization"), dict):
        result["optimization"] = {}

    if has_syntax_error:
        result["overall_score"] = min(result.get("overall_score", 3), 3)
        if not result.get("summary"):
            result["summary"] = "Syntax error detected. A fixed version is in the Before / After tab."

    # 5) Sirf successful result cache karo
    _cache[key] = result
    return result


EXPLAIN_PROMPT = """
You are a patient teacher explaining code to a complete beginner.
Use very simple English and short sentences. Explain any technical word the
first time you use it. Do not use JSON. Use this exact Markdown structure:

### What this code does
(2 to 3 sentences)

### Step by step
(numbered list, one step per important line or block, mention the line number)

### Words you should know
(2 to 4 short bullets: term - simple meaning)

### Example
(one small example: sample input and the output the code gives)

Keep the whole answer under 300 words. Do not suggest changes, only explain.
"""


def explain_code(code, language):
    """Beginner-friendly explanation of the code. Returns Markdown text."""
    if not code or not code.strip():
        return "No code to explain."

    key = _key(code, language, "explain")
    if key in _cache:
        return _cache[key]

    try:
        response = call_gemini(
            f"Explain this {language} code:\n\n```{language.lower()}\n{code}\n```",
            {"system_instruction": EXPLAIN_PROMPT, "temperature": 0.3},
        )
        text = response.text
        _cache[key] = text
        return text
    except Exception as e:
        return f"Could not explain the code right now: {friendly_error(e)}"
