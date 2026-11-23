# run_demo.py
"""Print the glider table and the hardware numbers, then draw 5 figures into figures/."""
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")                    # draw straight to files, no window needed
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.colors import ListedColormap

from twistlife import core

OUT = Path(__file__).resolve().parent / "figures"
OI = {"black": "#000000", "orange": "#E69F00", "sky": "#56B4E9", "green": "#009E73",
      "yellow": "#F0E442", "blue": "#0072B2", "red": "#D55E00", "purple": "#CC79A7"}
# Okabe-Ito colours are safe for colour-blind readers. Line styles help as a second clue.
COLOUR = {"plane": OI["black"], "torus": OI["blue"], "klein": OI["orange"], "projective": OI["green"]}
STYLE = {"plane": ":", "torus": "-", "klein": "--", "projective": "-."}
LIFE_CMAP = ListedColormap(["#FFFFFF", OI["blue"]])
WIDTH_IN, DPI = 16, 100                  # 16 inches x 100 dpi = 1600 px wide
plt.rcParams.update({"font.size": 22, "axes.titlesize": 24, "axes.labelsize": 24,
                     "legend.fontsize": 20, "lines.linewidth": 4})

# Alt text and captions. The README uses exactly these texts.
FIGURES = {
    "fig1_gluing.png": {
        "alt": "Three squares with coloured arrows on their edges. Left and right edges have one "
               "arrow, top and bottom edges have two arrows. Arrows pointing the same way mean a "
               "straight glue, arrows pointing opposite ways mean a glue with a flip.",
        "caption": "How the three surfaces are glued. Torus: both pairs straight. Klein bottle: "
                   "top and bottom flipped. Projective plane: both pairs flipped."},
    "fig2_glider_flip.png": {
        "alt": "A row of 8 small 10 by 10 grids, generations 0 to 28. A blue glider moves down "
               "and right, leaves through the orange bottom edge and comes back at the top as "
               "a mirror image, now moving down and left.",
        "caption": "A glider on a 10 x 10 Klein bottle, every 4 generations. After crossing the "
                   "flipped edge it is its own mirror image."},
    "fig3_return_times.png": {
        "alt": "A heat map table. Rows are grid sizes, columns are torus, Klein bottle and "
               "projective plane. Each box shows the first exact return and the first mirrored "
               "return of a glider, in generations.",
        "caption": "Glider return times, measured by simulation. Grey means nothing was seen "
                   "within the limit. The same numbers are in figures/glider_table.txt."},
    "fig4_population.png": {
        "alt": "Line chart of living cells over 300 generations for the R-pentomino on a 32 by "
               "32 grid, one line per surface. The lines are equal at the start and split later.",
        "caption": "R-pentomino population on each surface. At first all lines agree, because "
                   "the pattern has not reached an edge yet."},
    "fig5_hardware.png": {
        "alt": "A rising straight line of estimated LUTs against number of cells, a dashed "
               "horizontal line at the Zynq-7020 LUT count, and a dotted vertical line at the "
               "largest square grid that fits.",
        "caption": "HYPOTHESIS, not a synthesis result: LUT estimate with a fixed number of LUTs "
                   "per cell. Check the datasheet. Stage 3 of the plan will give real numbers."},
}


def save(fig, name):
    fig.savefig(OUT / name, dpi=DPI)     # no bbox_inches="tight": it would change the width
    plt.close(fig)
    print(f"wrote figures/{name}")


def edge(ax, start, end, colour, heads):
    s, e = np.array(start, float), np.array(end, float)
    ax.plot(*zip(s, e), color=colour, lw=8, solid_capstyle="round")
    d = (e - s) / np.linalg.norm(e - s)
    for k in range(heads):               # 1 or 2 heads, so the pairs differ even without colour
        c = (s + e) / 2 + d * 0.14 * (k - (heads - 1) / 2)
        ax.annotate("", xy=c + 0.06 * d, xytext=c - 0.06 * d,
                    arrowprops=dict(arrowstyle="-|>", color=colour, lw=4, mutation_scale=50))


def fig_gluing():
    titles = {"torus": "Torus\nboth straight", "klein": "Klein bottle\ntop/bottom flipped",
              "projective": "Projective plane\nboth flipped"}
    fig, axes = plt.subplots(1, 3, figsize=(WIDTH_IN, 7), layout="constrained")
    for ax, topo in zip(axes, titles):
        _, flip_x, _, flip_y = core.GLUE[topo]
        # Same arrow direction on a pair = straight glue. Opposite direction = flip.
        edge(ax, (0, 0), (0, 1), OI["sky"], 1)
        edge(ax, *(((1, 1), (1, 0)) if flip_x else ((1, 0), (1, 1))), OI["sky"], 1)
        edge(ax, (0, 0), (1, 0), OI["red"], 2)
        edge(ax, *(((1, 1), (0, 1)) if flip_y else ((0, 1), (1, 1))), OI["red"], 2)
        ax.set_title(titles[topo])
        ax.set_xlim(-0.15, 1.15), ax.set_ylim(-0.15, 1.15)
        ax.set_aspect("equal"), ax.axis("off")
    save(fig, "fig1_gluing.png")


def fig_glider_flip():
    W = H = 10
    start = core.place(core.empty(W, H), core.PATTERNS["glider"], 2, 5, "klein")
    states = core.simulate(start, "klein", 28)
    gens = list(range(0, 29, 4))
    fig, axes = plt.subplots(1, len(gens), figsize=(WIDTH_IN, 3.8), layout="constrained")
    for ax, g in zip(axes, gens):
        ax.imshow(states[g], cmap=LIFE_CMAP, vmin=0, vmax=1)
        ax.set_xticks(np.arange(-0.5, W, 1), minor=True)
        ax.set_yticks(np.arange(-0.5, H, 1), minor=True)
        ax.grid(which="minor", color="#CCCCCC", lw=1)
        ax.tick_params(which="both", length=0, labelbottom=False, labelleft=False)
        for yline in (-0.5, H - 0.5):    # the flipped pair of edges
            ax.axhline(yline, color=OI["orange"], lw=6)
        ax.set_title(f"gen {g}")
    fig.suptitle("Klein bottle: out through the bottom, back at the top, mirrored", fontsize=22)
    save(fig, "fig2_glider_flip.png")


def fig_return_table(rows):
    sizes = list(dict.fromkeys((r["W"], r["H"]) for r in rows))
    topos = list(dict.fromkeys(r["topology"] for r in rows))
    val = np.full((len(sizes), len(topos)), np.nan)
    fig, ax = plt.subplots(figsize=(WIDTH_IN, 11), layout="constrained")
    for r in rows:
        i, j = sizes.index((r["W"], r["H"])), topos.index(r["topology"])
        seen = [t for t in (r["exact"], r["mirror"]) if t is not None]
        if seen:
            val[i, j] = min(seen)
        text = f"exact {r['exact'] or '-'}\nmirror {r['mirror'] or '-'}"
        if r["died"]:
            text += f"\ndied {r['died']}"
        ax.text(j, i, text, ha="center", va="center", color="white", fontsize=20,
                path_effects=[pe.withStroke(linewidth=4, foreground="black")])
    cmap = plt.get_cmap("cividis").copy()
    cmap.set_bad("#BBBBBB")
    im = ax.imshow(np.ma.masked_invalid(val), cmap=cmap, aspect="auto")
    ax.set_xticks(range(len(topos)), topos)
    ax.set_yticks(range(len(sizes)), [f"{W}x{H}" for W, H in sizes])
    ax.set_title("Glider: first return (generations), measured")
    fig.colorbar(im, ax=ax, label="first return, exact or mirror")
    save(fig, "fig3_return_times.png")


def fig_population():
    W = H = 32
    fig, ax = plt.subplots(figsize=(WIDTH_IN, 8), layout="constrained")
    for topo in core.TOPOLOGIES:
        start = core.place(core.empty(W, H), core.PATTERNS["r_pentomino"], 14, 14, topo)
        pops = [int(s.sum()) for s in core.simulate(start, topo, 300)]
        ax.plot(pops, color=COLOUR[topo], ls=STYLE[topo], label=topo)
    ax.set_xlabel("generation"), ax.set_ylabel("living cells")
    ax.set_title("R-pentomino on a 32 x 32 grid")
    ax.legend()
    save(fig, "fig4_population.png")


def fig_hardware():
    cfg, n = core.CONFIG, core.largest_square()
    cells = np.arange(1, 141) ** 2
    fig, ax = plt.subplots(figsize=(WIDTH_IN, 8), layout="constrained")
    ax.plot(cells, cells * cfg["luts_per_cell"], color=OI["blue"],
            label=f"assumption: {cfg['luts_per_cell']} LUTs per cell")
    ax.axhline(cfg["zynq7020_luts"], color=OI["red"], ls="--",
               label=f"Zynq-7020: {cfg['zynq7020_luts']} LUTs (check the datasheet)")
    ax.axvline(n * n, color=OI["green"], ls=":", label=f"largest square: {n} x {n} = {n * n} cells")
    ax.set_xlabel("cells (W x H)"), ax.set_ylabel("LUTs")
    ax.set_title("HYPOTHESIS: estimate, not a synthesis result")
    ax.legend()
    save(fig, "fig5_hardware.png")


def main():
    OUT.mkdir(exist_ok=True)
    rows = core.glider_table()
    table, hw = core.format_glider_table(rows), core.hardware_report()
    print("Glider return times (measured by simulation):\n" + table + "\n\n" + hw + "\n")
    (OUT / "glider_table.txt").write_text(table + "\n")
    (OUT / "hardware_estimate.txt").write_text(hw + "\n")
    fig_gluing(), fig_glider_flip(), fig_return_table(rows), fig_population(), fig_hardware()


if __name__ == "__main__":
    main()
