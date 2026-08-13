# AI Synthesis Copilot

An AI-assisted physical-design pre-check for Verilog RTL, built as a hosted
web app. Paste a module and get three layers of feedback:

1. **Semantic lint** (`checker_engine.py`, pyverilog AST) — latch inference,
   blocking/non-blocking misuse, undriven regs, multi-driver conflicts,
   undriven outputs.
2. **Real synthesis** (`synth_engine.py`, Yosys) — actual generic-cell
   synthesis, not just static analysis. Surfaces true synthesizability
   errors/warnings and a gate-count breakdown.
3. **AI diagnosis** (`ai_diagnose.py`, optional) — if an `ANTHROPIC_API_KEY`
   is configured, sends the RTL + findings to Claude for a plain-English
   explanation and a suggested fix. Off by default; the app works fully
   without it.

## Why this exists

Static linting catches structural mistakes, but doesn't tell you whether a
design actually synthesizes or how big it comes out. Full PDK-accurate PPA
(the kind you'd get from OpenLane/LibreLane on Sky130) takes minutes per run
and needs a local PDK install. This sits in between: seconds-fast, generic
synthesis feedback you can run before burning a full physical-design run —
with an AI layer that explains *why* something's wrong, not just that it is.

## Local run

```bash
sudo apt-get install -y iverilog yosys
pip install -r requirements.txt
streamlit run app.py
```

To enable the AI diagnosis layer locally:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
streamlit run app.py
```

## Deploy — Streamlit Community Cloud (free)

1. Push this folder to a GitHub repo.
2. https://share.streamlit.io → **New app** → point at the repo, `app.py`.
3. `packages.txt` is picked up automatically for `iverilog` + `yosys` (apt).
4. **Optional AI layer:** in the app's Settings → Secrets, add:
```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
```
   Without this secret set, the app still runs — the AI checkbox is just
   disabled.
5. You get a public `https://<app>.streamlit.app` URL.

## Files

| File | Purpose |
|---|---|
| `checker_engine.py` | AST-based semantic lint (pyverilog) |
| `synth_engine.py` | Real Yosys generic synthesis + gate stats |
| `ai_diagnose.py` | Optional Claude-based diagnosis (needs API key) |
| `app.py` | Streamlit UI tying all three together |
| `requirements.txt` | Python deps |
| `packages.txt` | apt deps: `iverilog`, `yosys` |

## Known limitations

- **No PDK on the server** — gate counts are generic-cell (Yosys's internal
  library), not Sky130/GF180-mapped. Not real area or timing. Says so in
  the UI. Run your local OpenLane/LibreLane flow for PDK-accurate PPA.
- **No simulation** — static lint + synthesis only, won't catch functional
  logic bugs (wrong arithmetic, wrong FSM transitions, etc.).
- **AI suggestions are advisory, not auto-applied** — you review and apply
  fixes yourself. This is a deliberate scope cut for the hackathon-scale
  build; a self-healing auto-fix loop is a natural next step.
- Single top-module files only — no multi-file hierarchy stitching yet.

## Possible next steps

- Auto-apply AI-suggested fixes and re-run the loop until clean
  (self-healing RTL).
- Bundle Sky130 liberty files for PDK-accurate gate counts.
- Multi-file / hierarchical design support.
