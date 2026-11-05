import streamlit as st
from auth_ui import render_auth_page
from reviewer import review_code, explain_code
from report import build_report
from complexity import analyze_complexity
from dashboard import render_dashboard
from history import create_history_table, save_review, get_user_history
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

# ---------- CSS ----------
# style.css is loaded first (your existing look). EXTRA_CSS comes after it and
# styles the dashboard (score ring, category bars, summary, issues) so you do
# not have to touch style.css.
EXTRA_CSS = """
.dash { display:flex; flex-direction:column; gap:16px; margin-bottom:12px; }
.dash-head { display:flex; align-items:center; gap:20px; }
.score-ring {
    width:112px; height:112px; border-radius:50%; flex-shrink:0;
    background: conic-gradient(var(--c) calc(var(--pct) * 1%), #1f2335 0);
    display:flex; align-items:center; justify-content:center;
}
.score-inner {
    width:88px; height:88px; border-radius:50%; background:#0f1117;
    display:flex; flex-direction:column; align-items:center; justify-content:center;
}
.score-num { font-size:2rem; font-weight:700; line-height:1; color:#fff; }
.score-of { font-size:.75rem; color:#8b90a7; }
.dash-head-text h2 { margin:0 0 4px 0; padding:0; font-size:1.8rem; color:#fff; }
.dash-head-text p { margin:0; color:#9aa0b8; font-size:.95rem; }

.cat-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
.cat {
    background:#14172400; border:1px solid #232744; border-left:3px solid var(--c);
    border-radius:8px; padding:12px 14px; background:#131626;
}
.cat-row { display:flex; justify-content:space-between; font-size:.9rem;
           color:#e5e7f2; margin-bottom:8px; }
.bar { height:6px; background:#23273d; border-radius:99px; overflow:hidden; }
.bar-fill { height:100%; background:var(--c); border-radius:99px; }

.summary-card {
    background:#171a30; border:1px solid #2a2f55; border-radius:10px; padding:16px 18px;
}
.summary-card h4 { margin:0 0 8px 0; color:#818cf8; font-size:1.05rem; }
.summary-card p { margin:0; color:#d6d9ea; line-height:1.6; font-size:.95rem; }

.issues-title { margin:6px 0 0 0; color:#f87171; font-size:.8rem;
                letter-spacing:.08em; text-transform:uppercase; }
.issue { background:#1a1316; border:1px solid #4a1f26; border-left:3px solid #f87171;
         border-radius:8px; padding:12px 14px; }
.issue-title { color:#fca5a5; font-weight:600; margin-bottom:4px; }
.issue-desc { color:#d6d9ea; font-size:.92rem; line-height:1.5; }
.issue.ok { background:#10201a; border-color:#1d4a38; border-left-color:#34d399; color:#a7f3d0; }

@media (max-width: 800px) { .cat-grid { grid-template-columns:1fr; } }
"""

try:
    with open("style.css", "r", encoding="utf-8") as f:
        base_css = f.read()
except FileNotFoundError:
    base_css = ""
st.markdown(f"<style>{base_css}\n{EXTRA_CSS}</style>", unsafe_allow_html=True)

create_history_table()

if not render_auth_page():
    st.stop()

# ---------- Constants ----------
PLACEHOLDERS = {
    "Python": "def add(a, b):\n    return a+b\n",
    "C++": "int add(int a, int b) {\n    return a+b;\n}\n",
    "Java": "int add(int a, int b) {\n    return a+b;\n}\n",
}
EDITOR_HEIGHT = 650
SEVERITY_ICON = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵", "info": "⚪"}

# ---------- Session state (shared by all pages) ----------
st.session_state.setdefault("review_result", None)
st.session_state.setdefault("complexity_result", None)
st.session_state.setdefault("reviewed_code", "")
st.session_state.setdefault("reviewed_language", "Python")
st.session_state.setdefault("active_panel", None)
st.session_state.setdefault("explanation", None)
st.session_state.setdefault("editor_ver", 0)

user = st.session_state.get("user", {})

# ---------- Sidebar (same on every page) ----------
with st.sidebar:
    name = user.get("name", "User")
    st.markdown(
        f"""
        <div class="profile-card">
            <div class="avatar">{name[:1].upper()}</div>
            <div>
                <div class="profile-name">{name}</div>
                <div class="profile-email">{user.get("email", "")}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.selectbox("Language", list(LANGUAGE_CONFIG.keys()), key="language")

    st.markdown("##### How it works")
    st.markdown(
        "1. Paste or write your code\n"
        "2. Click **Review code**\n"
        "3. Open the **Report** page for the full details"
    )
    st.caption("Requires `GEMINI_API_KEY` in your environment.")

    if st.button("Logout", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.pop("user", None)
        st.rerun()


def _sync_code():
    """Keep what the user typed, so the editor is not reset after visiting another page."""
    saved = st.session_state.get("saved_code")
    if saved is not None:
        st.session_state.editor_code = saved


# =====================================================================
# PAGE 1: REVIEW  (full-width editor)
# =====================================================================
def review_page():
    language = st.session_state.language

    st.markdown(f"### Your {language} code")

    # reset editor when language changes
    if st.session_state.get("editor_lang") != language:
        st.session_state.editor_lang = language
        st.session_state.editor_code = PLACEHOLDERS[language]
        st.session_state.saved_code = PLACEHOLDERS[language]
        st.session_state.editor_ver = 0
    ver = st.session_state.editor_ver

    if HAS_ACE:
        code_input = st_ace(
            value=st.session_state.editor_code,
            language=LANGUAGE_CONFIG[language]["ace_mode"],
            theme="tomorrow_night",
            font_size=14,
            height=EDITOR_HEIGHT,
            auto_update=True,
            show_gutter=True,
            wrap=True,
            key=f"code_editor_{language}_{ver}",
        )
    else:
        code_input = st.text_area(
            "Paste code here",
            value=st.session_state.editor_code,
            height=EDITOR_HEIGHT,
            key=f"code_text_{language}_{ver}",
        )

    code_input = code_input if code_input is not None else st.session_state.editor_code
    st.session_state.saved_code = code_input

    line_count = len(code_input.splitlines()) if code_input else 0
    st.caption(f"{line_count} lines · {len(code_input or '')} characters")

    col_run, col_clear, _ = st.columns([1, 1, 3])
    run_clicked = col_run.button("✨ Review code", type="primary", use_container_width=True)
    clear_clicked = col_clear.button("Clear results", use_container_width=True)

    if clear_clicked:
        st.session_state.review_result = None
        st.session_state.complexity_result = None
        st.session_state.active_panel = None
        st.session_state.explanation = None
        st.rerun()

    if run_clicked:
        if not code_input or not code_input.strip():
            st.warning("Add some code in the editor first, then click Review code.")
        else:
            with st.spinner("Reviewing your code..."):
                st.session_state.review_result = review_code(code_input, language)
                st.session_state.complexity_result = analyze_complexity(code_input, language)
                st.session_state.reviewed_code = code_input
                st.session_state.reviewed_language = language
                st.session_state.active_panel = None
                st.session_state.explanation = None

                if user:
                    save_review(
                        user["id"],
                        language,
                        code_input,
                        st.session_state.review_result,
                        st.session_state.complexity_result,
                    )

    # ---------- Compact summary + hyperlinks ----------
    result = st.session_state.review_result
    if result:
        with st.container(border=True):
            if result.get("error"):
                st.error(result.get("summary", "Something went wrong during the review. Try again."))
            else:
                score100 = int(round(float(result.get("overall_score", 0) or 0) * 10))
                bugs = result.get("bugs", [])
                improvements = result.get("improvements", [])

                m1, m2, m3, m4 = st.columns([1, 1, 1, 1.4])
                m1.metric("Overall score", f"{score100}/100")
                m2.metric("Bugs", len(bugs))
                m3.metric("Improvements", len(improvements))
                with m4:
                    st.write("")
                    st.page_link(report_pg, label="View full report", icon="📊")
                    st.page_link(history_pg, label="Open history", icon="📜")


# =====================================================================
# PAGE 2: REPORT  (dashboard + tabs + actions)
# =====================================================================
def report_page():
    _sync_code()

    result = st.session_state.review_result
    complexity = st.session_state.complexity_result

    st.page_link(review_pg, label="Back to editor", icon="⬅️")
    st.markdown("### Review results")

    if not result:
        st.markdown(
            """
            <div class="empty-state">
                <b>No review yet</b><br>
                Go to the editor, write or paste code and click <b>Review code</b>.
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    if result.get("error"):
        st.error(result.get("summary", "Something went wrong during the review. Try again."))
        return

    bugs = result.get("bugs", [])
    improvements = result.get("improvements", [])
    score = result.get("overall_score", 0)

    render_dashboard(result, complexity)

    opt = result.get("optimization") or {}
    can_opt = opt.get("status") == "can_be_optimized"

    if can_opt and not bugs:
        st.warning(
            "Your code is correct, but it is not the fastest way to solve this. "
            "Open the 🚀 Optimization tab to see a faster version."
        )
    elif can_opt:
        st.warning("After fixing the bugs, this code can also be made faster. See the 🚀 Optimization tab.")
    elif opt.get("status") == "optimal":
        st.success("This is already an efficient approach.")

    # ---------- Action bar ----------
    def _toggle(name):
        st.session_state.active_panel = None if st.session_state.active_panel == name else name

    reviewed_code = st.session_state.reviewed_code
    reviewed_lang = st.session_state.reviewed_language
    report_md = build_report(result, complexity, reviewed_code, reviewed_lang)

    a1, a2, a3, a4, _sp = st.columns([1, 1.1, 1.1, 1.3, 0.1])
    a1.button("🔧 Fix code", use_container_width=True, key="btn_fix", on_click=_toggle, args=("fix",))
    a2.button("📖 Explain code", use_container_width=True, key="btn_explain", on_click=_toggle, args=("explain",))
    a3.button("📋 Copy report", use_container_width=True, key="btn_report", on_click=_toggle, args=("report",))
    a4.download_button(
        "⬇️ Download report",
        data=report_md,
        file_name="code_review_report.md",
        mime="text/markdown",
        use_container_width=True,
        key="dl_report",
    )

    panel = st.session_state.active_panel

    if panel == "fix":
        with st.container(border=True):
            st.markdown("#### 🔧 Fixed code")
            fixed = result.get("improved_code", "")
            if not fixed:
                st.info("No fixed version was returned for this code.")
            else:
                for ch in result.get("changes", []):
                    if isinstance(ch, dict):
                        st.markdown(f"- **Line {ch.get('line', '?')}:** {ch.get('reason', '')}")
                if not result.get("changes"):
                    st.success("Your code had no errors. This is a small cleanup.")
                st.code(fixed, language=reviewed_lang.lower())
                if st.button("Use this code in the editor", key="btn_apply"):
                    st.session_state.editor_code = fixed
                    st.session_state.saved_code = fixed
                    st.session_state.editor_ver += 1
                    st.session_state.active_panel = None
                    st.switch_page(review_pg)

    elif panel == "explain":
        with st.container(border=True):
            st.markdown("#### 📖 Code explanation")
            cached = st.session_state.explanation
            if not cached or cached.get("code") != reviewed_code:
                with st.spinner("Writing a simple explanation..."):
                    text = explain_code(reviewed_code, reviewed_lang)
                st.session_state.explanation = {"code": reviewed_code, "text": text}
            st.markdown(st.session_state.explanation["text"])

    elif panel == "report":
        with st.container(border=True):
            st.markdown("#### 📋 Report")
            st.caption("Click the copy icon at the top right of the box to copy the whole report.")
            st.code(report_md, language="markdown")

    t_bugs, t_improve, t_complex, t_opt, t_score, t_diff = st.tabs(
        ["🐛 Bugs", "💡 Improvements", "⚙️ Complexity", "🚀 Optimization", "📊 Score", "🔄 Before / After"]
    )

    with t_bugs:
        if not bugs:
            st.success("No bugs found. Nice and clean!")
        for bug in bugs:
            if isinstance(bug, dict):
                sev = str(bug.get("severity", "info")).lower()
                title = f"{SEVERITY_ICON.get(sev, '⚪')} Line {bug.get('line', 'N/A')} · {sev.title()}"
                content = format_bug_entry(bug)
            else:
                title, content = "⚪ Code issue", str(bug)
            with st.expander(title):
                st.markdown(content)

    with t_improve:
        if not improvements:
            st.info("No specific improvements suggested.")
        for i, item in enumerate(improvements, 1):
            with st.expander(
                item.get("title", f"Suggestion {i}") if isinstance(item, dict) else f"Suggestion {i}"
            ):
                st.markdown(format_improvement_entry(item))

    with t_complex:
        if opt.get("current_time"):
            b1, b2, b3 = st.columns(3)
            b1.metric("Time (Big-O)", opt.get("current_time"))
            b2.metric("Space (Big-O)", opt.get("current_space", "N/A"))
            b3.metric("Speed", "Can be faster" if can_opt else "Efficient")
            if can_opt:
                st.info(
                    f"A faster approach reaches time {opt.get('best_time', '?')}. "
                    "See the 🚀 Optimization tab."
                )
        if complexity:
            c1, c2, c3 = st.columns(3)
            c1.metric("Method", complexity["method"].title())
            c2.metric("Avg. complexity", complexity["average_complexity"])
            c3.metric("Rating", complexity["rating"])

            if complexity.get("maintainability_index") is not None:
                st.metric("Maintainability index", complexity["maintainability_index"])
            if complexity.get("details"):
                st.markdown("**Breakdown**")
                st.table(complexity["details"])
            if complexity.get("error"):
                st.warning(complexity["error"])
        if result.get("complexity_notes"):
            st.caption(result["complexity_notes"])

    with t_opt:
        if not opt:
            st.info("No optimization details were returned.")
        elif not can_opt:
            st.success("Your code already uses an efficient approach. Nothing to optimize.")
            if opt.get("explanation"):
                st.markdown(opt["explanation"])
        else:
            st.markdown("#### Your code vs a faster approach")
            o1, o2, o3, o4 = st.columns(4)
            o1.metric("Your time", opt.get("current_time", "?"))
            o2.metric("Faster time", opt.get("best_time", "?"))
            o3.metric("Your space", opt.get("current_space", "?"))
            o4.metric("Faster space", opt.get("best_space", "?"))

            st.markdown("#### Why it can be faster")
            st.markdown(opt.get("explanation", ""))
            st.caption(
                "Time = how the running time grows as the input gets bigger. "
                "Space = how much extra memory the code uses. Smaller is better."
            )

            lang_key = reviewed_lang.lower()
            oc_left, oc_right = st.columns(2)
            with oc_left:
                st.markdown("**Your code (works, but slower)**")
                st.code(reviewed_code, language=lang_key)
            with oc_right:
                st.markdown("**Optimized code (faster)**")
                st.code(opt.get("optimized_code", ""), language=lang_key)

            if opt.get("optimized_code"):
                st.download_button(
                    "Download optimized code",
                    data=opt["optimized_code"],
                    file_name="optimized_code.txt",
                    key="dl_optimized",
                )

    with t_score:
        color = score_color(score)
        st.markdown(f"### Code health: **{score}/10** · {score_label(score)}")
        st.progress(min(max(score / 10, 0), 1.0))
        if color == "green":
            st.success("This code is in great shape.")
        elif color == "orange":
            st.warning("Decent, but there is room to improve.")
        else:
            st.error("This code needs significant work.")

    with t_diff:
        improved = result.get("improved_code", "")
        lang_key = reviewed_lang.lower()
        if improved:
            left, right = st.columns(2)
            with left:
                st.markdown("**Original**")
                st.code(reviewed_code, language=lang_key)
            with right:
                st.markdown("**AI-improved**")
                st.code(improved, language=lang_key)
            changes = result.get("changes", [])
            if changes:
                st.markdown("#### What was wrong and how it was fixed")
                for ch in changes:
                    if not isinstance(ch, dict):
                        continue
                    with st.expander(f"Line {ch.get('line', '?')} · {ch.get('reason', '')[:60]}", expanded=True):
                        st.markdown(f"**Problem:** {ch.get('reason', '')}")
                        b_col, a_col = st.columns(2)
                        b_col.markdown("Before")
                        b_col.code(ch.get("before", ""), language=lang_key)
                        a_col.markdown("After")
                        a_col.code(ch.get("after", ""), language=lang_key)
            elif not bugs:
                st.success("Your code was already correct. Only small cleanups were made.")

            st.download_button(
                "Download improved code",
                data=improved,
                file_name=f"improved_code.{LANGUAGE_CONFIG[reviewed_lang].get('ext', 'txt')}",
            )
        else:
            st.info("No improved version was returned.")


# =====================================================================
# PAGE 3: HISTORY
# =====================================================================
def history_page():
    _sync_code()

    st.page_link(review_pg, label="Back to editor", icon="⬅️")
    st.markdown("### Previous reviews")
    if not user:
        st.warning("Log in to see your history.")
        return

    history = get_user_history(user["id"])
    if not history:
        st.markdown(
            '<div class="empty-state"><b>No reviews yet</b><br>'
            "Your reviews will show up here after you run one.</div>",
            unsafe_allow_html=True,
        )
        return

    st.caption(f"{len(history)} saved reviews")
    for item in history:
        with st.expander(f"{item['language']} · {item['created_at']}"):
            st.markdown("**Code**")
            st.code(item["code"], language=item["language"].lower())
            st.markdown("**Review result**")
            st.code(item["review_result"], language="json")


# ---------- Navigation ----------
review_pg = st.Page(review_page, title="Review", icon="✍️", url_path="review", default=True)
report_pg = st.Page(report_page, title="Report", icon="📊", url_path="report")
history_pg = st.Page(history_page, title="History", icon="📜", url_path="history")

# position="top" needs Streamlit >= 1.46; remove it to use the sidebar menu instead
pg = st.navigation([review_pg, report_pg, history_pg], position="top")
pg.run()
