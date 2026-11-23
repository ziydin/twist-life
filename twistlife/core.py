# twistlife/core.py
"""TwistLife core: Conway's Game of Life (rule B3/S23) on glued grids.

Conventions (used everywhere, also in the Verilog files):
  - The grid has W columns (x) and H rows (y). Arrays are indexed grid[y, x].
  - Cell index i = y * W + x. Row 0 is drawn at the top, so +y means "down".
  - A state is a numpy uint8 array of 0 (dead) and 1 (alive).
"""
from math import isqrt
from pathlib import Path
import numpy as np

CONFIG = {
    "seed": 42,              # fixed seed, so random grids are the same on every run
    "luts_per_cell": 6,      # HYPOTHESIS, not measured. A cell reads 9 bits (8 neighbours
                             # plus itself). One 6-input LUT (LUT = small lookup table, the
                             # basic logic block of an FPGA) cannot do that alone, so we
                             # guess a small adder plus rule logic: about 6. Stage 3 checks it.
    "zynq7020_luts": 53200,  # Zynq-7020 size as given to us. Check the datasheet.
    "zynq7020_ffs": 106400,  # flip-flops (1-bit memory cells). Check the datasheet.
}

TOPOLOGIES = ("plane", "torus", "klein", "projective")

# How we glue. Each entry is (wrap_x, flip_x, wrap_y, flip_y).
#   wrap_x: walking off the left/right edge brings you back on the other side.
#   flip_x: ...and on the way your row is turned upside down: y -> H-1-y.
#   wrap_y: walking off the top/bottom edge brings you back on the other side.
#   flip_y: ...and on the way your column is mirrored: x -> W-1-x.
# plane:      nothing glued. Cells outside the grid are simply dead.
# torus:      both pairs straight. A donut: leave right, come back left on the same row.
# klein:      left/right straight, top/bottom with a flip. Leave through the bottom
#             at column x, come back through the top at column W-1-x.
# projective: both pairs with a flip.
GLUE = {
    "plane": (False, False, False, False),
    "torus": (True, False, True, False),
    "klein": (True, False, True, True),
    "projective": (True, True, True, True),
}

# The 8 neighbour directions (dx, dy). The order matters only for the Verilog wiring.
OFFSETS = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]


def reduce_xy(X, Y, W, H, topology):
    """Take a point (X, Y) of the infinite plane and bring it back into the grid.

    Returns (x, y) inside the grid, or None if the point is outside and dead (plane).

    Why corners are safe:
      torus, klein: this two-step recipe (first fix x, then fix y) is the same as
        applying a symmetry of the infinite plane: a shift, or a "glide" (shift plus
        mirror). Shifts and glides fit together without conflicts, so the order does
        not matter and a diagonal step across a corner lands on the correct cell.
      projective: this surface can NOT be made from the flat plane in that clean way.
        The four corners of the square are glued in pairs, so only TWO cells meet at
        each corner point instead of four. The diagonal step across such a corner
        (for example from cell (0,0) to (-1,-1)) comes back to the cell itself.
        Worked out on paper: "x first" and "y first" give the same answer here.
        We keep this as a written-down choice: 4 corner cells count themselves once
        as a neighbour. The symmetry test checks that the table stays consistent.
    """
    wrap_x, flip_x, wrap_y, flip_y = GLUE[topology]
    if not 0 <= X < W:
        if not wrap_x:
            return None
        k, X = divmod(X, W)          # k = how many times we crossed (can be negative)
        if flip_x and k % 2:         # an odd number of flipped crossings mirrors the row
            Y = H - 1 - Y
    if not 0 <= Y < H:
        if not wrap_y:
            return None
        k, Y = divmod(Y, H)
        if flip_y and k % 2:         # X is already inside, and W-1-X keeps it inside
            X = W - 1 - X
    return X, Y


def neighbour_table(W, H, topology):
    """nbr[i, k] = index of the k-th neighbour of cell i. Shape (W*H, 8).

    Index N = W*H means "the extra dead cell". Only the plane uses it.
    In hardware this table IS the wiring, which is why topology costs no logic.
    """
    N = W * H
    nbr = np.full((N, 8), N, dtype=np.int64)
    for y in range(H):
        for x in range(W):
            for k, (dx, dy) in enumerate(OFFSETS):
                p = reduce_xy(x + dx, y + dy, W, H, topology)
                if p is not None:
                    nbr[y * W + x, k] = p[1] * W + p[0]
    return nbr


def step_slow(grid, topology):
    """One generation, written as plainly as possible. Used only to check step_fast."""
    H, W = grid.shape
    new = np.zeros((H, W), dtype=np.uint8)
    for y in range(H):
        for x in range(W):
            n = 0
            for dx, dy in OFFSETS:
                p = reduce_xy(x + dx, y + dy, W, H, topology)
                if p is not None:
                    n += int(grid[p[1], p[0]])
            alive = grid[y, x] == 1
            # B3/S23: born with exactly 3 neighbours, survives with 2 or 3.
            new[y, x] = 1 if (n == 3 or (alive and n == 2)) else 0
    return new


def step_fast(grid, nbr):
    """One generation with numpy. All cells are updated at once, like in hardware."""
    H, W = grid.shape
    flat = np.append(grid.ravel(), 0).astype(np.uint8)  # last entry = the extra dead cell
    n = flat[nbr].sum(axis=1)
    alive = flat[:-1] == 1
    return ((n == 3) | (alive & (n == 2))).astype(np.uint8).reshape(H, W)


def simulate(grid, topology, gens):
    """Return the list [state 0, state 1, ..., state gens]."""
    nbr = neighbour_table(grid.shape[1], grid.shape[0], topology)
    states = [grid.copy()]
    for _ in range(gens):
        states.append(step_fast(states[-1], nbr))
    return states


# ---------- patterns ----------
PATTERNS = {
    "glider": [[0, 1, 0], [0, 0, 1], [1, 1, 1]],   # moves +1 in x and +1 in y every 4 gens
    "blinker": [[1, 1, 1]],                        # period 2
    "block": [[1, 1], [1, 1]],                     # never changes
    "r_pentomino": [[0, 1, 1], [1, 1, 0], [0, 1, 0]],  # tiny, but busy for a long time
}


def empty(W, H):
    return np.zeros((H, W), dtype=np.uint8)


def place(grid, pattern, x, y, topology="torus"):
    """Put a pattern with its top-left corner at (x, y). Wraps using the surface rules."""
    H, W = grid.shape
    pat = np.asarray(pattern, dtype=np.uint8)
    for py, px in zip(*np.nonzero(pat)):
        p = reduce_xy(x + int(px), y + int(py), W, H, topology)
        if p is not None:
            grid[p[1], p[0]] = 1
    return grid


def random_grid(W, H, density=0.35, seed=None):
    rng = np.random.default_rng(CONFIG["seed"] if seed is None else seed)
    return (rng.random((H, W)) < density).astype(np.uint8)


# ---------- glider tracker ----------
def track_glider(W, H, topology, limit, x=1, y=1):
    """Measure, by simulation only, when a glider comes back.

    exact:  first generation where the grid equals the start grid.
    mirror: first generation where the grid equals the start grid mirrored
            left-right ("mirror-x") or top-bottom ("mirror-y").
    died:   generation where everything died (can happen near projective corners).
    """
    start = place(empty(W, H), PATTERNS["glider"], x, y, topology)
    mirrors = {"mirror-x": start[:, ::-1], "mirror-y": start[::-1, :]}
    nbr = neighbour_table(W, H, topology)
    res = {"topology": topology, "W": W, "H": H, "limit": limit,
           "exact": None, "mirror": None, "mirror_kind": None, "died": None}
    g = start
    for t in range(1, limit + 1):
        g = step_fast(g, nbr)
        if not g.any():
            res["died"] = t
            break
        if res["mirror"] is None:
            for kind, m in mirrors.items():
                if np.array_equal(g, m):
                    res["mirror"], res["mirror_kind"] = t, kind
                    break
        if np.array_equal(g, start):
            res["exact"] = t
            break          # from here on everything repeats, nothing new to learn
    return res


GLIDER_SIZES = [(8, 8), (12, 8), (9, 9), (16, 16), (20, 12), (7, 11)]


def glider_table(sizes=GLIDER_SIZES, topologies=("torus", "klein", "projective")):
    # The limit is just a generous time budget, not a prediction.
    return [track_glider(W, H, t, limit=8 * W * H) for (W, H) in sizes for t in topologies]


def format_glider_table(rows):
    def cell(r):
        if r["died"]:
            return f"died at {r['died']}"
        e = r["exact"] if r["exact"] is not None else "-"
        m = f"{r['mirror']} ({r['mirror_kind']})" if r["mirror"] is not None else "-"
        return f"exact {e}, mirror {m}"
    topos = list(dict.fromkeys(r["topology"] for r in rows))
    lines = ["size   | " + " | ".join(f"{t:<28}" for t in topos)]
    for (W, H) in dict.fromkeys((r["W"], r["H"]) for r in rows):
        cells = [cell(r) for t in topos for r in rows
                 if (r["W"], r["H"], r["topology"]) == (W, H, t)]
        lines.append(f"{W}x{H}".ljust(6) + " | " + " | ".join(f"{c:<28}" for c in cells))
    lines.append("('-' = not seen within the limit of 8*W*H generations)")
    return "\n".join(lines)


# ---------- hardware numbers (all HYPOTHESIS) ----------
def hardware_estimate(W, H, cfg=CONFIG):
    cells = W * H
    luts = cells * cfg["luts_per_cell"]
    return {"cells": cells, "wires": 8 * cells, "state_bits": cells, "luts": luts,
            "lut_share": luts / cfg["zynq7020_luts"], "ff_share": cells / cfg["zynq7020_ffs"]}


def largest_square(cfg=CONFIG):
    n = isqrt(cfg["zynq7020_luts"] // cfg["luts_per_cell"])
    while n * n > cfg["zynq7020_ffs"]:   # one flip-flop per cell must also fit
        n -= 1
    return n


def hardware_report(sizes=((16, 16), (32, 32), (64, 64), (100, 100)), cfg=CONFIG):
    out = [f"HYPOTHESIS. Assumption: about {cfg['luts_per_cell']} LUTs per cell, 1 flip-flop "
           f"per cell. Zynq-7020: {cfg['zynq7020_luts']} LUTs, {cfg['zynq7020_ffs']} "
           "flip-flops (check the datasheet)."]
    for W, H in sizes:
        e = hardware_estimate(W, H, cfg)
        out.append(f"  {W}x{H}: cells {e['cells']}, wires {e['wires']}, state bits "
                   f"{e['state_bits']}, LUTs ~{e['luts']} ({100 * e['lut_share']:.1f}% of "
                   f"chip), FFs {100 * e['ff_share']:.1f}%")
    n = largest_square(cfg)
    out.append(f"  Largest square grid under this assumption: {n} x {n} (HYPOTHESIS)")
    return "\n".join(out)


# ---------- test vectors (shared by emit_verilog.py and the tests) ----------
VECTOR_GENS = (0, 1, 10, 100)
GENERATED_HEADER = "// generated by Python, not yet compiled or simulated"


def grid_to_hex(grid):
    """Bit i of the number = cell i (i = y*W + x). Bit 0 is the least significant bit."""
    bits = grid.ravel()
    value = 0
    for i in np.nonzero(bits)[0]:
        value |= 1 << int(i)
    return format(value, f"0{(bits.size + 3) // 4}x")


def hex_to_grid(text, W, H):
    value = int(text, 16)
    return np.array([(value >> i) & 1 for i in range(W * H)], dtype=np.uint8).reshape(H, W)


def write_vectors(path, W, H, topology, seed=None):
    """One hex word per line, '//' comments, so Verilog's $readmemh can read it later."""
    states = simulate(random_grid(W, H, seed=seed), topology, max(VECTOR_GENS))
    lines = [GENERATED_HEADER,
             f"// W={W} H={H} topology={topology} gens={','.join(map(str, VECTOR_GENS))}",
             "// bit i = cell i = y*W + x, bit 0 = least significant"]
    lines += [f"{grid_to_hex(states[g])} // gen {g}" for g in VECTOR_GENS]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines) + "\n")
    return path


def read_vectors(path):
    info, words = {}, []
    for line in Path(path).read_text().splitlines():
        if line.startswith("// W="):
            info = dict(kv.split("=") for kv in line[3:].split())
        body = line.split("//")[0].strip()
        if body:
            words.append(body)
    gens = [int(g) for g in info["gens"].split(",")]
    return int(info["W"]), int(info["H"]), info["topology"], dict(zip(gens, words))


def check_vectors(path):
    """Reload a vector file, re-simulate from gen 0, return the list of wrong generations."""
    W, H, topology, words = read_vectors(path)
    states = simulate(hex_to_grid(words[0], W, H), topology, max(words))
    return [g for g, word in words.items() if grid_to_hex(states[g]) != word]
