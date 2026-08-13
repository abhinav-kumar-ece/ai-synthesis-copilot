"""
Optional AI diagnosis layer. If ANTHROPIC_API_KEY is set in the environment
(e.g. as a Streamlit secret), this sends the RTL + tool findings to Claude
and asks for a plain-English diagnosis and a suggested fix. Entirely
optional — the checker and synthesis engine work fine without it.

This never auto-applies changes; it only returns text for a human to review.
"""

import os
import json
import urllib.request
import urllib.error

MODEL = "claude-sonnet-5"
API_URL = "https://api.anthropic.com/v1/messages"


def ai_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def diagnose(code: str, lint_issues: list, synth_warnings: list, synth_errors: list) -> str:
    """
    Returns a plain-text diagnosis + suggested fix, or an error message
    string starting with 'AI diagnosis unavailable' if it can't run.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return "AI diagnosis unavailable: no ANTHROPIC_API_KEY configured on this server."

    findings = []
    for i in lint_issues:
        findings.append(f"[{i.severity.upper()}] {i.code}: {i.message}")
    for w in synth_warnings:
        findings.append(f"[SYNTH WARNING] {w}")
    for e in synth_errors:
        findings.append(f"[SYNTH ERROR] {e}")

    findings_text = "\n".join(findings) if findings else "(no findings — asking for a general review)"

    prompt = (
        "You are reviewing Verilog RTL for a student's hardware project. "
        "Here is the RTL:\n\n```verilog\n" + code + "\n```\n\n"
        "Here are the automated findings from a linter and Yosys synthesis:\n\n"
        + findings_text +
        "\n\nIn plain English, explain what's actually wrong (if anything) and give a "
        "concrete, minimal code fix for the most important issue. Keep it under 200 words. "
        "If there are no real issues, say so briefly."
    )

    payload = {
        "model": MODEL,
        "max_tokens": 500,
        "messages": [{"role": "user", "content": prompt}],
    }

    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text_blocks = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
        return "\n".join(text_blocks) if text_blocks else "AI diagnosis returned no text."
    except urllib.error.HTTPError as e:
        return f"AI diagnosis failed: HTTP {e.code} — {e.read().decode('utf-8', errors='ignore')[:200]}"
    except Exception as e:
        return f"AI diagnosis failed: {e}"
