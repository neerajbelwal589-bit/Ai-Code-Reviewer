import os
import ast
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

# Prompt/logic badalne par isko badlo, taaki purana cache use na ho
PROMPT_VERSION = "v3"
print(f"[reviewer] loaded, PROMPT_VERSION={PROMPT_VERSION}")  # terminal me dikhna chahiye


def _key(code, language, kind):
    return hashlib.md5(f"{PROMPT_VERSION}|{kind}|{language}|{code}".encode()).hexdigest()


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
- Decide if the code is correct but SLOWER or less idiomatic than the standard
  better approach. Examples:
  * nested loops O(n^2) where a hash map gives O(n)
  * building a string with += inside a loop (use the simplest built-in or
    slicing; use list + "".join() only if nothing simpler fits)
  * re-implementing a built-in by hand (reversed, sum, max, min, sorted,
    slicing like s[::-1]) with a manual loop
- Building a string with += in a loop counts as can_be_optimized, even if the
  Big-O looks the same, because each += may copy the whole string again.
- A hand-written loop that a single built-in or slice can replace counts as
  can_be_optimized.
- If a clearly better approach exists: status = "can_be_optimized", fill
  current_time/current_space (Big-O of the user's code) and best_time/best_space
  (Big-O of your optimized version), and write optimized_code.
- Only use status = "optimal" if NO built-in, idiomatic, or lower-complexity
  version exists. Then best_* same as current_*, optimized_code = "".
- explanation: only 2 to 3 VERY short sentences for a beginner. Say what is
  slow, then what the simpler way is. No jargon, no Big-O words here.
- optimized_code (VERY IMPORTANT, the reader is a BEGINNER):
  * Use the SIMPLEST possible fix. Prefer ONE built-in or slice over a longer
    loop (example: return s[::-1] instead of a loop + list + join).
  * Keep the SAME function name and parameters.
  * Make it as SHORT as possible: ideally 1 to 4 lines inside the function.
  * Do NOT add extra variables, helper lists or extra steps if a one-line
    version exists.
  * Add at most ONE short comment (max 8 words) in the whole code. Do NOT
    comment every line. Never write "# FIXED:" comments here.
  * Do NOT use advanced features (no generators, lambdas, comprehensions,
    type hints, imports) unless the original code already uses them.
  * It must be complete and runnable, and keep the original print/test lines.
- improved_code stays the small safe cleanup/fix. Do NOT put the optimized
  approach inside improved_code.
- The "summary" must clearly say if the code is correct but can be optimized.
- Do not give the top score (9-10) to correct code that can be optimized.
- If you list anything in "improvements" about speed or efficiency, then
  optimization.status MUST be "can_be_optimized".

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


# ---------------------------------------------------------------------------
# Extra static check: string += inside loop (Python only)
# ---------------------------------------------------------------------------
def find_string_concat_in_loop(code):
    """Return line numbers where a str variable is built with += inside a loop."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    hits = []
    str_vars = set()

    # variables initialised with a string literal, e.g. result = ""
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    str_vars.add(t.id)

    # += on those variables inside for / while
    for loop in ast.walk(tree):
        if isinstance(loop, (ast.For, ast.While)):
            for node in ast.walk(loop):
                if (
                    isinstance(node, ast.AugAssign)
                    and isinstance(node.op, ast.Add)
                    and isinstance(node.target, ast.Name)
                    and node.target.id in str_vars
                ):
                    hits.append(node.lineno)
    return sorted(set(hits))


def build_user_prompt(code, language, syntax_bugs=None, hints=None):
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

    hint_note = ""
    if hints:
        hint_note = (
            "\nStatic analysis found these performance issues. Treat them as real: "
            "set optimization.status = can_be_optimized and write optimized_code. "
            "Keep optimized_code VERY short and beginner-simple (prefer a one-line "
            "built-in or slice, at most one comment):\n"
            + "\n".join(f"- {h}" for h in hints)
            + "\n"
        )

    return f"""
Review this {language} code.
{syntax_note}{hint_note}
Code:

```{language.lower()}
{code}
```

Return your review strictly as the JSON schema described in your instructions."""


# ---------------------------------------------------------------------------
# Output ko normalize karna (model ki galtiyan code me theek karo)
# ---------------------------------------------------------------------------
def _to_int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def normalize_result(result, hints):
    # a) overall score = category scores ka average (0-100 -> 0-10 scale)
    cats = result.get("category_scores") or {}
    vals = [max(0, min(100, _to_int(v))) for v in cats.values()]
    if vals:
        result["overall_score"] = round(sum(vals) / len(vals) / 10)
    else:
        result["overall_score"] = max(0, min(10, _to_int(result.get("overall_score"))))

    opt = result.get("optimization")
    if not isinstance(opt, dict):
        opt = {}

    # b) static hint mila hai but model "optimal" bola -> override
    if hints and opt.get("status") != "can_be_optimized":
        opt["status"] = "can_be_optimized"
        if not opt.get("explanation"):
            opt["explanation"] = hints[0]

    # c) can_be_optimized hai to top score nahi + improvement entry zaroor ho
    if opt.get("status") == "can_be_optimized":
        result["overall_score"] = min(result["overall_score"], 8)
        if not result.get("improvements"):
            result["improvements"] = [
                {
                    "title": "Can be optimized",
                    "detail": opt.get(
                        "explanation", "A faster or cleaner approach exists."
                    ),
                }
            ]
    else:
        opt["optimized_code"] = ""

    result["optimization"] = opt

    # d) improvements hain to score 10 nahi
    if result.get("improvements"):
        result["overall_score"] = min(result["overall_score"], 9)

    return result


# ---------------------------------------------------------------------------
# Safety net: optimized_code ko code me simple banao (model na maane tab bhi)
# ---------------------------------------------------------------------------
SIMPLIFY_PROMPT = """
You make code SHORTER and SIMPLER for a complete beginner.
Return ONLY the code. No markdown, no ``` fences, no explanation.

Rules:
- Keep the same function name and parameters.
- Use ONE built-in or slice instead of a loop whenever possible
  (example: return s[::-1] instead of a loop).
- Keep the original print/test lines.
- No extra variables, no helper lists, no imports.
- At most ONE short comment (max 8 words) in the whole code.
- Never write "# FIXED".
"""


def _code_lines(code):
    """Non-empty lines that are not pure comments."""
    return [
        ln for ln in (code or "").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]


def clean_optimized_code(code):
    """Remove '# FIXED' notes and keep at most ONE full-line comment."""
    import re

    code = (code or "").strip()
    # ``` fences hata do agar model ne laga diye
    code = re.sub(r"^```[a-zA-Z]*\n?", "", code)
    code = re.sub(r"\n?```$", "", code)

    out = []
    comments = 0
    for ln in code.splitlines():
        s = ln.strip()
        if s.startswith("#"):
            if "FIXED" in s or comments >= 1:
                continue
            comments += 1
            out.append(ln)
        else:
            # inline "# FIXED: ..." hata do
            out.append(re.sub(r"\s+#\s*FIXED.*$", "", ln))
    return "\n".join(out).strip()


def simplify_optimized(code, optimized, language):
    """Ek aur chhota Gemini call: lambe optimized code ko simple karo."""
    try:
        response = call_gemini(
            f"Original {language} code:\n{code}\n\n"
            f"Optimized version (too long):\n{optimized}\n\n"
            "Rewrite the optimized version as short and simple as possible.",
            {"system_instruction": SIMPLIFY_PROMPT, "temperature": 0.1},
        )
        return clean_optimized_code(response.text)
    except Exception:
        return optimized


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

    # 2b) Performance hints (string += in loop)
    hints = []
    if language.lower() == "python" and not has_syntax_error:
        for ln in find_string_concat_in_loop(code):
            hints.append(
                f"Line {ln}: string built with += inside a loop "
                f"(use the simplest built-in or slicing instead)"
            )

    # 3) Gemini review (also fixes syntax errors)
    try:
        response = call_gemini(
            build_user_prompt(code, language, syntax_bugs, hints),
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

    # 4b) Model ke output ko consistent banao (score, optimization, improvements)
    result = normalize_result(result, hints)

    # 4c) optimized_code ko simple rakho (comments saaf, lamba ho to chhota karwao)
    opt = result.get("optimization", {})
    if opt.get("status") == "can_be_optimized" and opt.get("optimized_code"):
        cleaned = clean_optimized_code(opt["optimized_code"])
        if len(_code_lines(cleaned)) > len(_code_lines(code)):
            cleaned = simplify_optimized(code, cleaned, language)
        opt["optimized_code"] = cleaned

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
