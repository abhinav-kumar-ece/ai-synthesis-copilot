"""Curated RTL examples for the UI's example gallery — one clean design,
one per bug type, so a visitor can see every check fire without writing
any Verilog themselves."""

EXAMPLES = {
    "Clean D flip-flop (should pass)": """module dff(
    input wire clk,
    input wire rst,
    input wire d,
    output reg q
);
    always @(posedge clk) begin
        if (rst)
            q <= 1'b0;
        else
            q <= d;
    end
endmodule
""",

    "Latch inference (if without else)": """module bad_mux(
    input wire sel,
    input wire [3:0] a,
    input wire [3:0] b,
    output reg [3:0] y
);
    always @(*) begin
        if (sel)
            y = a;
        // missing else — infers a latch on y
    end
endmodule
""",

    "Blocking assignment in sequential block": """module bad_counter(
    input wire clk,
    input wire rst,
    output reg [3:0] count
);
    always @(posedge clk) begin
        if (rst)
            count = 4'b0;      // should be <=
        else
            count = count + 1; // should be <=
    end
endmodule
""",

    "Non-blocking in combinational block": """module bad_comb(
    input wire a,
    input wire b,
    output reg y
);
    always @(*) begin
        y <= a & b;  // should be = in combinational logic
    end
endmodule
""",

    "Multi-driver conflict": """module conflict(
    input wire a,
    input wire b,
    output wire y
);
    assign y = a;
    always @(*) begin
        y = b;  // y now has two drivers
    end
endmodule
""",

    "Undriven register": """module ghost_reg(
    input wire a,
    output wire y
);
    reg unused_flag;  // declared, never assigned anywhere
    assign y = a;
endmodule
""",

    "Missing default in case (latch risk)": """module bad_decoder(
    input wire [1:0] sel,
    output reg [3:0] y
);
    always @(*) begin
        case (sel)
            2'b00: y = 4'b0001;
            2'b01: y = 4'b0010;
            // no default — y latches for sel == 2'b10 or 2'b11
        endcase
    end
endmodule
""",
}
