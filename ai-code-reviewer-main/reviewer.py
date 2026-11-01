import os
from dotenv import load_dotenv

load_dotenv()
from google import genai
from utils import safe_json_parse
from google.genai import types
from syntax_checker import check_syntax
from static_analysis import analyze_static

MODEL_NAME = "gemini-3.5-flash"


SYSTEM_PROMPT = """
You are a senior software engineer performing a code review.

You ALWAYS respond with ONLY ONE VALID JSON OBJECT.

Never return markdown.

Never return ```json

Never explain anything outside JSON.

Schema:

{
  "summary":"",
  "bugs":[
    {
      "line":"",
      "severity":"",
      "description":""
    }
  ],
  "improvements":[
    {
      "title":"",
      "detail":""
    }
  ],
  "complexity_notes":"",
  "improved_code":"",
  "overall_score":8
}

Rules

- Return JSON only.
- improved_code should contain COMPLETE runnable code.
- Don't invent bugs.
- Keep suggestions educational.
"""


def get_client():
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise EnvironmentError(
            "GEMINI_API_KEY not found."
        )

    return genai.Client(api_key=api_key)


def build_user_prompt(code, language):

    return f"""
Review this {language} code.

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
            "complexity_notes": "N/A",
            "overall_score": 0,
            "improved_code": "",
            "summary": "No code was provided to review.",
            "error": True,
        }

	#syntax check
    syntax_result = check_syntax(code, language)

    if not syntax_result["valid"]:
        return {
            "summary": "Syntax error detected.",
            "bugs": syntax_result["bugs"],
            "improvements": [],
            "complexity_notes": "Fix syntax errors before reviewing.",
            "improved_code": "",
            "overall_score": 1,
        }

    
    # Static Analysis
    static_bugs = analyze_static(code,language)

    # Gemini Review
    client = get_client()

    try:

        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=build_user_prompt(code, language),
            config={
                "system_instruction": SYSTEM_PROMPT,
                "temperature": 0.2,
                "response_mime_type": "application/json",
            },
        )

        raw_text = response.text

        result = safe_json_parse(raw_text)

    except Exception as e:

        return {
            "bugs": static_bugs,
            "improvements": [],
            "complexity_notes": "N/A",
            "overall_score": 0,
            "improved_code": "",
            "summary": f"Gemini API Error: {e}",
            "error": True,
        }

    # Merge Bugs
    result["bugs"] = static_bugs + result.get("bugs", [])

    return result
