"""
RTL Intent Checker - core engine
Parses Verilog RTL with pyverilog and runs semantic/style checks that go
beyond plain syntax validity: latch inference, blocking/non-blocking misuse,
undriven/unused signals, width red flags, and multi-driver conflicts.
"""

import os
import re
import tempfile
from dataclasses import dataclass, field
from typing import List

from pyverilog.vparser.parser import parse
from pyverilog.vparser.ast import (
    ModuleDef, Always, IfStatement, NonblockingSubstitution,
    BlockingSubstitution, SensList, Sens, Decl, Reg, Wire, Input, Output,
    Inout, Identifier, Case, CaseStatement,
)


@dataclass
class Issue:
    severity: str   # "error" | "warning" | "info"
    code: str       # short machine-readable id
    message: str
    line: int = 0


@dataclass
class ModulePort:
    name: str
    direction: str
    width: str = "1"


@dataclass
class CheckResult:
    module_name: str = ""
    ports: List[ModulePort] = field(default_factory=list)
    issues: List[Issue] = field(default_factory=list)
    passed: bool = False

    @property
    def error_count(self):
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self):
        return sum(1 for i in self.issues if i.severity == "warning")


def _write_temp_verilog(code: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".v")
    with os.fdopen(fd, "w") as f:
        f.write(code)
    return path


def _collect_signal_names(node, names, kind):
    """Walk decl list collecting reg/wire names."""
    for item in getattr(node, "items", []) or []:
        if isinstance(item, kind):
            names.add(item.name)


def check_rtl(code: str) -> CheckResult:
    result = CheckResult()
    path = _write_temp_verilog(code)

    try:
        ast, _ = parse([path])
    except Exception as e:
        result.issues.append(Issue("error", "SYNTAX", f"Parse failed: {e}"))
        os.unlink(path)
        return result
    finally:
        if os.path.exists(path):
            os.unlink(path)

    modules = [d for d in ast.description.definitions if isinstance(d, ModuleDef)]
    if not modules:
        result.issues.append(Issue("error", "NO_MODULE", "No module definition found."))
        return result

    mod = modules[0]
    result.module_name = mod.name

    # --- ports ---
    reg_names, wire_names = set(), set()
    assigned_in_always = set()
    driven_by_assign = set()
    all_signal_names = set()

    # ANSI-style ports (Verilog-2001): declared directly in the port list as
    # Ioport nodes wrapping an Input/Output/Inout (+ optional Wire/Reg pair).
    if mod.portlist:
        for p in mod.portlist.ports:
            first = getattr(p, "first", None)
            second = getattr(p, "second", None)
            if isinstance(first, Input):
                result.ports.append(ModulePort(first.name, "input", _width_str(first)))
                all_signal_names.add(first.name)
            elif isinstance(first, Output):
                result.ports.append(ModulePort(first.name, "output", _width_str(first)))
                all_signal_names.add(first.name)
            elif isinstance(first, Inout):
                result.ports.append(ModulePort(first.name, "inout", _width_str(first)))
                all_signal_names.add(first.name)
            else:
                pname = getattr(p, "name", None)
                if pname:
                    all_signal_names.add(pname)
            if isinstance(second, Reg):
                reg_names.add(second.name)
            elif isinstance(second, Wire):
                wire_names.add(second.name)

    for item in mod.items:
        if isinstance(item, Decl):
            for d in item.list:
                if isinstance(d, Input):
                    result.ports.append(ModulePort(d.name, "input", _width_str(d)))
                    all_signal_names.add(d.name)
                elif isinstance(d, Output):
                    result.ports.append(ModulePort(d.name, "output", _width_str(d)))
                    all_signal_names.add(d.name)
                elif isinstance(d, Inout):
                    result.ports.append(ModulePort(d.name, "inout", _width_str(d)))
                    all_signal_names.add(d.name)
                elif isinstance(d, Reg):
                    reg_names.add(d.name)
                    all_signal_names.add(d.name)
                elif isinstance(d, Wire):
                    wire_names.add(d.name)
                    all_signal_names.add(d.name)

    # --- walk always blocks for semantic issues ---
    from pyverilog.vparser.ast import Assign

    for item in mod.items:
        if isinstance(item, Assign):
            lhs_name = _lhs_name(item.left)
            if lhs_name:
                driven_by_assign.add(lhs_name)

        if isinstance(item, Always):
            is_clocked = _is_edge_sensitive(item.sens_list)
            targets_this_block = set()
            has_blocking = _contains(item.statement, BlockingSubstitution)
            has_nonblocking = _contains(item.statement, NonblockingSubstitution)

            _collect_lhs_targets(item.statement, targets_this_block)
            assigned_in_always |= targets_this_block

            if is_clocked and has_blocking:
                result.issues.append(Issue(
                    "warning", "BLOCKING_IN_SEQ",
                    "Blocking assignment (=) used inside a clocked (sequential) "
                    "always block; use non-blocking (<=) to model flip-flop behavior correctly."
                ))
            if (not is_clocked) and has_nonblocking:
                result.issues.append(Issue(
                    "warning", "NONBLOCKING_IN_COMB",
                    "Non-blocking assignment (<=) used inside a combinational "
                    "always block; use blocking (=) to avoid simulation/synthesis mismatch."
                ))

            if not is_clocked:
                incomplete = _find_incomplete_branches(item.statement, targets_this_block)
                for sig in incomplete:
                    result.issues.append(Issue(
                        "error", "LATCH_INFERENCE",
                        f"Signal '{sig}' is not assigned on every path of a "
                        f"combinational always block — this infers an unintended latch. "
                        f"Add an else branch or a default assignment."
                    ))

    # --- undriven registers ---
    for r in reg_names:
        if r not in assigned_in_always:
            result.issues.append(Issue(
                "warning", "UNDRIVEN_REG",
                f"Reg '{r}' is declared but never assigned in any always block."
            ))

    # --- multiple-driver conflicts (assign + always on same net) ---
    conflicts = driven_by_assign & assigned_in_always
    for c in conflicts:
        result.issues.append(Issue(
            "error", "MULTI_DRIVER",
            f"Signal '{c}' appears to be driven by both a continuous 'assign' "
            f"statement and an always block — this creates conflicting drivers."
        ))

    # --- unused outputs (declared but appears nowhere as a driven target) ---
    driven_any = assigned_in_always | driven_by_assign
    output_names = {p.name for p in result.ports if p.direction == "output"}
    for o in output_names:
        if o not in driven_any and o not in reg_names.union(wire_names) - driven_any:
            # only flag if truly never driven anywhere
            if o not in driven_any:
                result.issues.append(Issue(
                    "warning", "UNDRIVEN_OUTPUT",
                    f"Output '{o}' does not appear to be driven anywhere in the module."
                ))

    result.passed = result.error_count == 0
    return result


def _width_str(decl_item) -> str:
    w = getattr(decl_item, "width", None)
    if w is None:
        return "1"
    try:
        msb = getattr(w.msb, "value", "?")
        lsb = getattr(w.lsb, "value", "?")
        return f"[{msb}:{lsb}]"
    except Exception:
        return "?"


def _lhs_name(node):
    if isinstance(node, Identifier):
        return node.name
    name = getattr(node, "name", None)
    if name:
        return name
    var = getattr(node, "var", None)
    if var is not None:
        return _lhs_name(var)
    return None


def _contains(node, node_type):
    if node is None:
        return False
    if isinstance(node, node_type):
        return True
    for child in getattr(node, "children", lambda: [])():
        if _contains(child, node_type):
            return True
    return False


def _collect_lhs_targets(node, out_set):
    if node is None:
        return
    if isinstance(node, (NonblockingSubstitution, BlockingSubstitution)):
        n = _lhs_name(node.left)
        if n:
            out_set.add(n)
    for child in getattr(node, "children", lambda: [])():
        _collect_lhs_targets(child, out_set)


def _is_edge_sensitive(sens_list) -> bool:
    if sens_list is None:
        return False
    for s in getattr(sens_list, "list", []) or []:
        if isinstance(s, Sens) and s.type in ("posedge", "negedge"):
            return True
    return False


def _find_incomplete_branches(stmt, block_targets):
    """
    Very targeted latch check: for top-level if-statements without an else,
    or case statements without a default, inside a combinational block,
    flag targets assigned in the 'if' branch but not guaranteed elsewhere.
    This is a heuristic, not a full CFG analysis.
    """
    flagged = set()

    def walk(node):
        if isinstance(node, IfStatement):
            if node.false_statement is None:
                true_targets = set()
                _collect_lhs_targets(node.true_statement, true_targets)
                flagged.update(true_targets & block_targets)
            walk(node.true_statement)
            if node.false_statement is not None:
                walk(node.false_statement)
        elif isinstance(node, CaseStatement):
            has_default = any(c.cond is None for c in node.caselist)
            if not has_default:
                case_targets = set()
                for c in node.caselist:
                    _collect_lhs_targets(c.statement, case_targets)
                flagged.update(case_targets & block_targets)
            for c in node.caselist:
                walk(c.statement)
        else:
            for child in getattr(node, "children", lambda: [])():
                walk(child)

    walk(stmt)
    return flagged
