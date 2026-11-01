import streamlit as st
from reviewer import review_code
from complexity import analyze_complexity
from utils import (
    LANGUAGE_CONFIG,
    score_color,
    score_label,
    format_bug_entry,
    format_improvement_entry,
)

try:
    from streamlit_ace import st_ace
    HAS_ACE = True
except ImportError:
    HAS_ACE = False

st.set_page_config(page_title="AI Code Reviewer", page_icon="🔍", layout="wide")

st.title("🔍 AI Code Reviewer")
st.caption("Paste your code, get instant AI feedback — bugs, improvements, and a complexity score.")

with st.sidebar:
    st.header("⚙️ Settings")
    language = st.selectbox("Language", list(LANGUAGE_CONFIG.keys()))
    st.markdown("---")
    st.markdown(
        "**How it works**\n\n"
        "1. Paste or write your code\n"
        "2. Click **Review My Code**\n"
        "3. Get bugs, suggestions, complexity & a score"
    )
    st.markdown("---")
    st.caption("Requires `GEMINI_API_KEY` set as an environment variable.")

#session
if "review_result" not in st.session_state:
    st.session_state.review_result = None
if "complexity_result" not in st.session_state:
    st.session_state.complexity_result = None

st.subheader("Your Code")

placeholder_code = {
    "Python": "def add(a, b):\n    return a+b\n",
    "C++": "int add(int a, int b) {\n    return a+b;\n}\n",
    "Java": "int add(int a, int b) {\n    return a+b;\n}\n",
}[language]

if HAS_ACE:
    code_input = st_ace(
        value=placeholder_code,
        language=LANGUAGE_CONFIG[language]["ace_mode"],
        theme="tomorrow_night",
        font_size=14,
        height=300,
        key="code_editor",
    )
else:
    code_input = st.text_area("Paste code here", value=placeholder_code, height=300)

col_run, col_clear = st.columns([1, 5])
with col_run:
    run_clicked = st.button("Review Code", type="primary", use_container_width=True)
with col_clear:
    if st.button("Clear results"):
        st.session_state.review_result = None
        st.session_state.complexity_result = None
        st.rerun()

if run_clicked:
    if not code_input or not code_input.strip():
        st.warning("Please paste some code first.")
    else:
        with st.spinner("AI is reviewing your code..."):
            st.session_state.review_result = review_code(code_input, language)
            st.session_state.complexity_result = analyze_complexity(code_input, language)


# ---------- Results ----------
result = st.session_state.review_result
complexity = st.session_state.complexity_result

if result:
    if result.get("error"):
        st.error(result.get("summary", "Something went wrong during review."))
    else:
        st.markdown("---")
        st.subheader("Review Results")

        if result.get("summary"):
            st.info(result["summary"])

        tab_bugs, tab_improve, tab_complexity, tab_score, tab_diff = st.tabs(
            ["🐛 Bugs", "💡 Improvements", "⚙️ Complexity", "📊 Score", "🔀 Before/After"]
        )

        # --- Bugs tab ---
        with tab_bugs:
            bugs = result.get("bugs", [])
            if not bugs:
                st.success("No bugs found. Nice and clean! ✅")
            else:
                for bug in bugs:
                    with st.expander(f"Line {bug.get('line', 'N/A')} — {bug.get('severity', 'info').title()}"):
                        st.markdown(format_bug_entry(bug))

        # --- Improvements tab ---
        with tab_improve:
            improvements = result.get("improvements", [])
            if not improvements:
                st.info("No specific improvements suggested.")
            else:
                for item in improvements:
                    st.markdown(format_improvement_entry(item))
                    st.markdown("")

        # --- Complexity tab ---
        with tab_complexity:
            if complexity:
                c1, c2, c3 = st.columns(3)
                c1.metric("Method", complexity["method"].title())
                c2.metric("Avg. Complexity", complexity["average_complexity"])
                c3.metric("Rating", complexity["rating"])

                if complexity.get("maintainability_index") is not None:
                    st.metric("Maintainability Index", complexity["maintainability_index"])

                if complexity.get("details"):
                    st.markdown("**Breakdown**")
                    st.table(complexity["details"])

                if complexity.get("error"):
                    st.warning(complexity["error"])

            st.caption(result.get("complexity_notes", ""))

        # --- Score tab ---
        with tab_score:
            score = result.get("overall_score", 0)
            color = score_color(score)
            label = score_label(score)

            st.markdown(f"### Overall Code Health: **{score}/10** — {label}")
            st.progress(min(max(score / 10, 0), 1.0))

            if color == "green":
                st.success("This code is in great shape!")
            elif color == "orange":
                st.warning("Decent, but there's room to improve.")
            else:
                st.error("This code needs significant work.")

        # --- Before / After tab ---
        with tab_diff:
            improved = result.get("improved_code", "")
            if improved:
                left, right = st.columns(2)
                with left:
                    st.markdown("**Original**")
                    st.code(code_input, language=language.lower())
                with right:
                    st.markdown("**AI-Improved**")
                    st.code(improved, language=language.lower())
            else:
                st.info("No improved version was returned.")
else:
    st.markdown("---")
    st.caption("Paste your code above and click **Review My Code** to get started.")
