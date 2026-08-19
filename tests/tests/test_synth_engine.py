import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from synth_engine import run_synthesis, yosys_available

pytest_plugins = []


def _skip_if_no_yosys():
    if not yosys_available():
        import pytest
        pytest.skip("yosys not installed in this environment")


def test_empty_input():
    r = run_synthesis("")
    assert not r.passed
    assert not r.ran


def test_clean_counter_synthesizes():
    _skip_if_no_yosys()
    code = """
    module counter(input wire clk, input wire rst, output reg [3:0] count);
    always @(posedge clk) begin
        if (rst) count <= 4'b0;
        else count <= count + 1'b1;
    end
    endmodule
    """
    r = run_synthesis(code)
    assert r.ran
    assert r.passed
    assert r.total_cells > 0
    assert r.top_module == "counter"


def test_no_module_name_found():
    r = run_synthesis("not actually verilog at all")
    assert not r.passed


def test_explicit_top_module_used():
    _skip_if_no_yosys()
    code = """
    module a_module(input wire x, output wire y);
    assign y = x;
    endmodule
    """
    r = run_synthesis(code, top_module="a_module")
    assert r.top_module == "a_module"
    assert r.ran
