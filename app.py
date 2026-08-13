import streamlit as st
from checker_engine import check_rtl
from synth_engine import run_synthesis, yosys_available
from ai_diagnose import ai_available, diagnose

st.set_page_config(page_title="AI Synthesis Copilot", page_icon="🧠", layout="wide")

st.title("🧠 AI Synthesis Copilot")
st.caption(
    "Paste Verilog RTL. This runs a pyverilog semantic lint, a real Yosys "
    "generic synthesis for synthesizability + gate counts, and (if configured) "
    "an AI diagnosis of what to fix."
)

DEFAULT_CODE = """module example(
    input wire clk,
    input wire rst,
    input wire sel,
    input wire [3:0] a,
    input wire [3:0] b,
    output reg [3:0] y
);
    always @(*) begin
        if (sel)
            y = a;
    end
endmodule
"""

col_in, col_out = st.columns([1, 1], gap="large")

with col_in:
    st.subheader("Your RTL")
    code = st.text_area("Verilog source", value=DEFAULT_CODE, height=420, label_visibility="collapsed")
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

            if lint_result.passed and synth_result.passed and not lint_result.issues:
                st.success(f"✅ Clean — `{lint_result.module_name}` lints clean and synthesizes.")
            elif lint_result.passed and synth_result.passed:
                st.warning(f"⚠️ `{lint_result.module_name}` synthesizes, but has {lint_result.warning_count} lint warning(s).")
            else:
                st.error(f"❌ `{lint_result.module_name or synth_result.top_module}` has issues that need fixing.")

            if lint_result.ports:
                with st.expander(f"Module interface ({len(lint_result.ports)} ports)", expanded=False):
                    for p in lint_result.ports:
                        st.markdown(f"- **{p.name}** — `{p.direction}` {p.width}")

            st.markdown("---")
            st.markdown("**Semantic lint (pyverilog AST)**")
            if lint_result.issues:
                for issue in lint_result.issues:
                    icon = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(issue.severity, "⚪")
                    st.markdown(f"{icon} **[{issue.code}]** {issue.message}")
            else:
                st.markdown("No lint findings.")

            st.markdown("---")
            st.markdown("**Yosys generic synthesis**")
            if synth_result.tool_missing:
                st.info("Yosys isn't installed on this server — synthesis step skipped.")
            elif not synth_result.ran:
                for e in synth_result.errors:
                    st.markdown(f"🔴 {e}")
            else:
                if synth_result.errors:
                    for e in synth_result.errors:
                        st.markdown(f"🔴 {e}")
                if synth_result.warnings:
                    for w in synth_result.warnings:
                        st.markdown(f"🟡 {w}")
                if not synth_result.errors and not synth_result.warnings:
                    st.markdown("Synthesized with no errors or warnings.")

                if synth_result.total_cells:
                    st.markdown(f"**Gate count (generic cells):** {synth_result.total_cells} total, "
                                f"{synth_result.wire_count} wires")
                    with st.expander("Cell breakdown", expanded=False):
                        for cell, n in sorted(synth_result.cell_counts.items(), key=lambda x: -x[1]):
                            st.markdown(f"- `{cell}`: {n}")
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
    else:
        st.info("Paste your RTL and click **Analyze RTL** to see results here.")

st.markdown("---")
st.caption(
    "Static lint + generic synthesis — this won't catch every functional bug (no simulation), "
    "and gate counts here are unmapped to any real PDK. Treat it as a fast pre-check before "
    "you burn a full synthesis/PnR run."
)
