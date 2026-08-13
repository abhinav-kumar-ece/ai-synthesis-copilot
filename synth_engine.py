"""
Synthesis engine — runs pasted RTL through Yosys generic synthesis to get
real synthesizability results and gate-level stats, distinct from the
static AST linting in checker_engine.py.

This is intentionally PDK-agnostic (generic cell library via Yosys's
built-in `synth` pass). Real area/timing numbers require a specific PDK
(e.g. Sky130 liberty files) which aren't bundled here — see README for why.
"""

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class SynthResult:
    ran: bool = False
    passed: bool = False
    top_module: str = ""
    cell_counts: Dict[str, int] = field(default_factory=dict)
    wire_count: int = 0
    total_cells: int = 0
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    raw_log: str = ""
    tool_missing: bool = False


def yosys_available() -> bool:
    return shutil.which("yosys") is not None


def run_synthesis(code: str, top_module: str = "") -> SynthResult:
    result = SynthResult()

    if not yosys_available():
        result.tool_missing = True
        result.errors.append(
            "Yosys is not installed on this server, so synthesis can't run. "
            "Lint-only results are still shown above."
        )
        return result

    if not top_module:
        m = re.search(r"\bmodule\s+(\w+)", code)
        top_module = m.group(1) if m else ""

    if not top_module:
        result.errors.append("Could not find a module name to synthesize.")
        return result

    result.top_module = top_module

    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = os.path.join(tmpdir, "design.v")
        with open(src_path, "w") as f:
            f.write(code)

        script = f"read_verilog {src_path}; synth -top {top_module}; stat"
        try:
            proc = subprocess.run(
                ["yosys", "-p", script],
                capture_output=True, text=True, timeout=30, cwd=tmpdir,
            )
        except subprocess.TimeoutExpired:
            result.errors.append("Synthesis timed out (30s limit).")
            return result

        result.ran = True
        result.raw_log = proc.stdout + proc.stderr

        for line in result.raw_log.splitlines():
            low = line.strip()
            if low.lower().startswith("error"):
                result.errors.append(low)
            elif low.lower().startswith("warning"):
                result.warnings.append(low)

        cell_section = False
        for line in result.raw_log.splitlines():
            if "Number of wires:" in line:
                try:
                    result.wire_count = int(line.split(":")[1].strip())
                except (ValueError, IndexError):
                    pass
            if "Number of cells:" in line:
                cell_section = True
                try:
                    result.total_cells = int(line.split(":")[1].strip())
                except (ValueError, IndexError):
                    pass
                continue
            if cell_section:
                m = re.match(r"\s*(\$\S+|\w+)\s+(\d+)\s*$", line)
                if m:
                    result.cell_counts[m.group(1)] = int(m.group(2))
                elif line.strip() == "" or ":" in line:
                    cell_section = False

        result.passed = (proc.returncode == 0) and not result.errors
        return result
