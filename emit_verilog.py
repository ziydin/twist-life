# emit_verilog.py
"""Write Verilog wiring tables, test vectors and two small Verilog modules.

Nothing written here has been compiled or simulated. It is the input for Stage 2.
"""
from pathlib import Path

from twistlife import core

W, H = 16, 16                            # small on purpose: easy to read and to simulate
HW = Path(__file__).resolve().parent / "hardware"
GEN = HW / "generated"

CELL_V = core.GENERATED_HEADER + """
// hardware/cell.v - one Life cell. UNTESTED: never compiled, simulated or synthesized.
// The cell does not know which surface it lives on. It only sees 8 wires.
module cell (
    input  wire       clk,
    input  wire       load,   // 1 = copy 'init' into the cell (sets the start state)
    input  wire       init,
    input  wire [7:0] nb,     // the 8 neighbours, connected by topology_<name>.vh
    output reg        alive
);
    // 4 bits are enough, because the count is at most 8.
    wire [3:0] n = nb[0] + nb[1] + nb[2] + nb[3] + nb[4] + nb[5] + nb[6] + nb[7];
    always @(posedge clk) begin
        if (load) alive <= init;
        else      alive <= (n == 4'd3) | (alive & (n == 4'd2));   // B3/S23
    end
endmodule
"""

GRID_V = core.GENERATED_HEADER + f"""
// hardware/life_grid.v - {W} x {H} cells, all updated on the same clock edge. UNTESTED.
// The included wiring file was generated for W={W}, H={H}. Other sizes need new files.
// To change the surface, change the include line below.
// Stage 2 idea: iverilog -g2012 -I hardware/generated hardware/cell.v hardware/life_grid.v <testbench>
module life_grid #(parameter W = {W}, parameter H = {H}) (
    input  wire           clk,
    input  wire           load,
    input  wire [W*H-1:0] init,   // bit i = cell i = y*W + x, same as the vector files
    output wire [W*H-1:0] state
);
    wire [8*W*H-1:0] nb;
    `include "topology_torus.vh"
    genvar i;
    generate
        for (i = 0; i < W*H; i = i + 1) begin : cells
            cell c (.clk(clk), .load(load), .init(init[i]), .nb(nb[8*i +: 8]), .alive(state[i]));
        end
    endgenerate
endmodule
"""


def topology_vh(W, H, topo):
    N = W * H
    nbr = core.neighbour_table(W, H, topo)
    src = lambda j: "1'b0" if j == N else f"state[{j}]"   # 1'b0 = dead cell outside the plane
    lines = [core.GENERATED_HEADER,
             f"// topology={topo} W={W} H={H} N={N}. Cell i = y*W + x.",
             "// nb[8*i+k] = neighbour k of cell i, with k following core.OFFSETS:",
             "//   " + " ".join(f"k{k}=({dx},{dy})" for k, (dx, dy) in enumerate(core.OFFSETS)),
             "// The cells are the same on every surface. Only these lines change."]
    for i in range(N):
        terms = ", ".join(src(int(j)) for j in nbr[i][::-1])  # {a, b} puts a on the top bit
        lines.append(f"assign nb[{8 * i + 7}:{8 * i}] = {{{terms}}};  // cell ({i % W},{i // W})")
    return "\n".join(lines) + "\n"


def main():
    GEN.mkdir(parents=True, exist_ok=True)
    for topo in core.TOPOLOGIES:
        (GEN / f"topology_{topo}.vh").write_text(topology_vh(W, H, topo))
        # Same seed for every surface: same start, so differences come only from the gluing.
        vec = core.write_vectors(GEN / f"vectors_{topo}.txt", W, H, topo)
        wrong = core.check_vectors(vec)
        print(f"{topo:<11} wiring + vectors written, Python re-check: "
              f"{'OK' if not wrong else f'WRONG at gens {wrong}'}")
    (HW / "cell.v").write_text(CELL_V)
    (HW / "life_grid.v").write_text(GRID_V)
    print("hardware/cell.v and hardware/life_grid.v written (untested)")


if __name__ == "__main__":
    main()
