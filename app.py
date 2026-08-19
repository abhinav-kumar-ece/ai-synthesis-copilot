import streamlit as st
from datetime import datetime
from checker_engine import check_rtl
from synth_engine import run_synthesis
from ai_diagnose import ai_available, diagnose
from examples import EXAMPLES

st.set_page_config(page_title="AI Synthesis Copilot", page_icon="🧠", layout="wide")

st.markdown("""
<style>
    .stApp { }
    div[data-testid="stMetricValue"] { font-size: 1.4rem; }
    .badge {
        display: inline-block; padding: 3px 10px; border-radius: 12px;
        font-size: 0.85rem; font-weight: 600; margin-right: 6px;
    }
    .badge-error   { background: #3a1414; color: #ff8080; border: 1px solid #6b2020; }
    .badge-warning { background: #3a3014; color: #ffd580; border: 1px solid #6b5720; }
    .badge-ok      { background: #12301c; color: #7ee0a0; border: 1px solid #205c32; }
</style>
""", unsafe_allow_html=True)

st.title("🧠 AI Synthesis Copilot")
st.caption(
    "Paste Verilog RTL. This runs a pyverilog semantic lint, a real Yosys "
    "generic synthesis for synthesizability + gate counts, and (if configured) "
    "an AI diagnosis of what to fix."
)

if "rtl_code" not in st.session_state:
    st.session_state.rtl_code = EXAMPLES["Clean D flip-flop (should pass)"]

col_in, col_out = st.columns([1, 1], gap="large")

with col_in:
    st.subheader("Your RTL")

    example_choice = st.selectbox(
        "Load an example",
        ["— pick an example —"] + list(EXAMPLES.keys()),
        label_visibility="collapsed",
    )
    if example_choice != "— pick an example —":
        st.session_state.rtl_code = EXAMPLES[example_choice]

    code = st.text_area(
        "Verilog source",
        value=st.session_state.rtl_code,
        height=380,
        label_visibility="collapsed",
        key="rtl_textarea",
    )

    run = st.button("Analyze RTL", type="primary", use_container_width=True)
    want_ai = st.checkbox(
        "Ask AI to diagnose findings" + ("" if ai_available() else " (needs ANTHROPIC_API_KEY — not set on this server)"),
        value=False,
        disabled=not ai_available(),
    )

with col_out:
    st.subheader("Result")
    if run:
        if not code.strip():
            st.warning("Paste some Verilog code first.")
        else:
            with st.spinner("Linting..."):
                lint_result = check_rtl(code)

            with st.spinner("Running Yosys synthesis..."):
                synth_result = run_synthesis(code)

            report_lines = [
                f"AI Synthesis Copilot report — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                f"Module(s): {lint_result.module_name or synth_result.top_module}",
                "",
            ]

            if lint_result.passed and synth_result.passed and not lint_result.issues:
                st.success(f"✅ Clean — `{lint_result.module_name}` lints clean and synthesizes.")
                report_lines.append("Verdict: CLEAN — no lint findings, synthesis passed.")
            elif lint_result.passed and synth_result.passed:
                st.warning(f"⚠️ `{lint_result.module_name}` synthesizes, but has {lint_result.warning_count} lint warning(s).")
                report_lines.append(f"Verdict: WARNINGS — synthesizes, {lint_result.warning_count} lint warning(s).")
            else:
                st.error(f"❌ `{lint_result.module_name or synth_result.top_module}` has issues that need fixing.")
                report_lines.append("Verdict: ERRORS — needs fixing before this is trustworthy RTL.")

            if lint_result.ports:
                with st.expander(f"Module interface ({len(lint_result.ports)} ports)", expanded=False):
                    for p in lint_result.ports:
                        st.markdown(f"- **{p.name}** — `{p.direction}` {p.width}")

            st.markdown("---")
            st.markdown("**Semantic lint (pyverilog AST)**")
            report_lines.append("\n--- Semantic lint ---")
            if lint_result.issues:
                for issue in lint_result.issues:
                    icon = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(issue.severity, "⚪")
                    st.markdown(f"{icon} **[{issue.code}]** {issue.message}")
                    report_lines.append(f"[{issue.severity.upper()}] {issue.code}: {issue.message}")
            else:
                st.markdown("No lint findings.")
                report_lines.append("No lint findings.")

            st.markdown("---")
            st.markdown("**Yosys generic synthesis**")
            report_lines.append("\n--- Yosys synthesis ---")
            if synth_result.tool_missing:
                st.info("Yosys isn't installed on this server — synthesis step skipped.")
                report_lines.append("Yosys not available — step skipped.")
            elif not synth_result.ran:
                for e in synth_result.errors:
                    st.markdown(f"🔴 {e}")
                    report_lines.append(f"ERROR: {e}")
            else:
                if synth_result.errors:
                    for e in synth_result.errors:
                        st.markdown(f"🔴 {e}")
                        report_lines.append(f"ERROR: {e}")
                if synth_result.warnings:
                    for w in synth_result.warnings:
                        st.markdown(f"🟡 {w}")
                        report_lines.append(f"WARNING: {w}")
                if not synth_result.errors and not synth_result.warnings:
                    st.markdown("Synthesized with no errors or warnings.")
                    report_lines.append("Synthesized cleanly, no errors or warnings.")

                if synth_result.total_cells:
                    st.markdown(f"**Gate count (generic cells):** {synth_result.total_cells} total, "
                                f"{synth_result.wire_count} wires")
                    report_lines.append(f"Gate count: {synth_result.total_cells} cells, {synth_result.wire_count} wires")
                    with st.expander("Cell breakdown", expanded=False):
                        for cell, n in sorted(synth_result.cell_counts.items(), key=lambda x: -x[1]):
                            st.markdown(f"- `{cell}`: {n}")
                            report_lines.append(f"  {cell}: {n}")
                    st.caption(
                        "Generic gate counts only — no PDK loaded on this server, so this is "
                        "not Sky130/GF180-accurate area or timing. Run through your local "
                        "OpenLane/LibreLane flow for real PPA numbers."
                    )

            if want_ai:
                st.markdown("---")
                st.markdown("**AI diagnosis**")
                with st.spinner("Asking Claude..."):
                    ai_text = diagnose(code, lint_result.issues, synth_result.warnings, synth_result.errors)
                st.markdown(ai_text)
                report_lines.append("\n--- AI diagnosis ---")
                report_lines.append(ai_text)

            st.download_button(
                "Download report (.txt)",
                data="\n".join(report_lines),
                file_name="rtl_report.txt",
                mime="text/plain",
                use_container_width=True,
            )
    else:
        st.info("Paste your RTL (or load an example on the left) and click **Analyze RTL** to see results here.")

st.markdown("---")
st.caption(
    "Static lint + generic synthesis — this won't catch every functional bug (no simulation), "
    "and gate counts here are unmapped to any real PDK. Treat it as a fast pre-check before "
    "you burn a full synthesis/PnR run."
)
