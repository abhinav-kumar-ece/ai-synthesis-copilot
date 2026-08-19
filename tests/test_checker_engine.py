import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from checker_engine import check_rtl


def issue_codes(result):
    return {i.code for i in result.issues}


def test_empty_input():
    r = check_rtl("")
    assert not r.passed
    assert "EMPTY_INPUT" in issue_codes(r)


def test_whitespace_only_input():
    r = check_rtl("   \n\n  ")
    assert not r.passed
    assert "EMPTY_INPUT" in issue_codes(r)


def test_syntax_error():
    r = check_rtl("module broken( input a output b );")
    assert not r.passed
    assert "SYNTAX" in issue_codes(r)


def test_clean_dff_passes():
    code = """
    module dff(input wire clk, input wire rst, input wire d, output reg q);
    always @(posedge clk) begin
        if (rst) q <= 1'b0;
        else q <= d;
    end
    endmodule
    """
    r = check_rtl(code)
    assert r.passed
    assert r.error_count == 0
    assert r.module_name == "dff"
    assert {p.name for p in r.ports} == {"clk", "rst", "d", "q"}


def test_latch_inference_if_without_else():
    code = """
    module bad_mux(input wire sel, input wire [3:0] a, output reg [3:0] y);
    always @(*) begin
        if (sel) y = a;
    end
    endmodule
    """
    r = check_rtl(code)
    assert not r.passed
    assert "LATCH_INFERENCE" in issue_codes(r)


def test_latch_inference_case_without_default():
    code = """
    module bad_case(input wire [1:0] sel, output reg [3:0] y);
    always @(*) begin
        case (sel)
            2'b00: y = 4'd1;
            2'b01: y = 4'd2;
        endcase
    end
    endmodule
    """
    r = check_rtl(code)
    assert not r.passed
    assert "LATCH_INFERENCE" in issue_codes(r)


def test_case_with_default_no_latch():
    code = """
    module ok_case(input wire [1:0] sel, output reg [3:0] y);
    always @(*) begin
        case (sel)
            2'b00: y = 4'd1;
            default: y = 4'd0;
        endcase
    end
    endmodule
    """
    r = check_rtl(code)
    assert r.passed
    assert "LATCH_INFERENCE" not in issue_codes(r)


def test_blocking_in_sequential_block():
    code = """
    module bad_seq(input wire clk, input wire d, output reg q);
    always @(posedge clk) begin
        q = d;
    end
    endmodule
    """
    r = check_rtl(code)
    assert "BLOCKING_IN_SEQ" in issue_codes(r)


def test_nonblocking_in_combinational_block():
    code = """
    module bad_comb(input wire a, output reg y);
    always @(*) begin
        y <= a;
    end
    endmodule
    """
    r = check_rtl(code)
    assert "NONBLOCKING_IN_COMB" in issue_codes(r)


def test_undriven_reg():
    code = """
    module has_ghost_reg(input wire a, output wire y);
    reg unused_reg;
    assign y = a;
    endmodule
    """
    r = check_rtl(code)
    assert "UNDRIVEN_REG" in issue_codes(r)


def test_multi_driver_conflict():
    code = """
    module conflict(input wire a, input wire b, output wire y);
    assign y = a;
    always @(*) begin
        y = b;
    end
    endmodule
    """
    r = check_rtl(code)
    assert "MULTI_DRIVER" in issue_codes(r)


def test_old_style_ports_parsed():
    code = """
    module old_style(clk, rst, out);
    input clk, rst;
    output reg out;
    always @(posedge clk) begin
        if (rst) out <= 0;
        else out <= ~out;
    end
    endmodule
    """
    r = check_rtl(code)
    assert {p.name for p in r.ports} == {"clk", "rst", "out"}
    assert r.passed


def test_parameterized_width_does_not_crash():
    code = """
    module param_test #(parameter WIDTH=8) (
        input wire [WIDTH-1:0] a,
        output reg [WIDTH-1:0] y
    );
    always @(*) y = a;
    endmodule
    """
    r = check_rtl(code)
    widths = {p.name: p.width for p in r.ports}
    assert "?" not in widths["a"]
    assert "WIDTH" in widths["a"]


def test_multi_module_file_analyzes_both():
    code = """
    module sub(input a, input sel, output reg b);
    always @(*) begin
        if (sel) b = a;
    end
    endmodule

    module top(input clk, input a, output reg b);
    always @(posedge clk) b = a;
    endmodule
    """
    r = check_rtl(code)
    assert "sub" in r.module_name and "top" in r.module_name
    assert any("[sub]" in i.message for i in r.issues)
    assert any("[top]" in i.message for i in r.issues)
    assert "LATCH_INFERENCE" in issue_codes(r)
    assert "BLOCKING_IN_SEQ" in issue_codes(r)
