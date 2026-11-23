# tests/test_core.py
"""Plain-assert tests. Run with `python tests/test_core.py` (or with pytest).

Each test prints one line: OK or FAILED, with the numbers it saw.
"""
import sys
import tempfile
from math import lcm
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))          # so `python tests/test_core.py` finds the package
from twistlife import core  # noqa: E402

NOTES = {}   # extra numbers for the one-line report (pytest ignores this)

# Sizes for the neighbour test. If 'projective' fails for one size, remove that size
# here, write a comment "dropped WxH: projective failed with N bad pairs", and say so
# in the README. Do not hide failures.
SYM_SIZES = [(4, 4), (5, 7), (8, 8), (12, 8), (9, 13), (16, 16), (20, 12)]


def test_neighbour_table_symmetric():
    # Why: "B touches A" must mean "A touches B". If corner gluing is wrong,
    # a corner cell points at some cell that does not point back. Counting
    # multiplicity matters: on the projective plane a cell can see the same
    # neighbour twice, and then it must be seen back twice.
    bad, self_loops = [], {}
    for topo in core.TOPOLOGIES:
        for W, H in SYM_SIZES:
            N = W * H
            nbr = core.neighbour_table(W, H, topo)
            assert nbr.shape == (N, 8), f"{topo} {W}x{H}: shape {nbr.shape}"
            assert nbr.min() >= 0 and nbr.max() <= N, f"{topo} {W}x{H}: index out of range"
            if topo != "plane":
                assert nbr.max() < N, f"{topo} {W}x{H}: glued surface used the dead cell"
            rows, cols = np.repeat(np.arange(N), 8), nbr.ravel()
            keep = cols < N                       # ignore the plane's dead cell
            M = np.zeros((N, N), dtype=np.int64)
            np.add.at(M, (rows[keep], cols[keep]), 1)
            n_bad = int((M != M.T).sum()) // 2
            if n_bad:
                bad.append(f"{topo} {W}x{H}: {n_bad} asymmetric pairs")
            self_loops[(topo, W, H)] = int((nbr == np.arange(N)[:, None]).any(axis=1).sum())
    proj = sorted({v for (t, _, _), v in self_loops.items() if t == "projective"})
    NOTES["test_neighbour_table_symmetric"] = (
        f"{len(core.TOPOLOGIES)} surfaces x {len(SYM_SIZES)} sizes; "
        f"projective cells that list themselves (corner choice): {proj}")
    assert not bad, "; ".join(bad)


def test_fast_equals_slow():
    checked = 0
    for topo in core.TOPOLOGIES:
        for i, (W, H) in enumerate([(8, 8), (9, 7), (16, 12)]):
            g = core.random_grid(W, H, seed=core.CONFIG["seed"] + i)
            nbr = core.neighbour_table(W, H, topo)
            for gen in range(25):
                fast, slow = core.step_fast(g, nbr), core.step_slow(g, topo)
                diff = int((fast != slow).sum())
                assert diff == 0, f"{topo} {W}x{H} gen {gen + 1}: {diff} cells differ"
                g = fast
                checked += 1
    NOTES["test_fast_equals_slow"] = f"{checked} steps compared, 0 differences"


def test_block_and_blinker():
    for topo in core.TOPOLOGIES:
        nbr = core.neighbour_table(10, 10, topo)
        b0 = core.place(core.empty(10, 10), core.PATTERNS["block"], 4, 4, topo)
        assert np.array_equal(core.step_fast(b0, nbr), b0), f"{topo}: block changed"
        k0 = core.place(core.empty(10, 10), core.PATTERNS["blinker"], 3, 5, topo)
        k1 = core.step_fast(k0, nbr)
        k2 = core.step_fast(k1, nbr)
        assert not np.array_equal(k1, k0), f"{topo}: blinker did not blink"
        assert np.array_equal(k2, k0), f"{topo}: blinker period is not 2"
    NOTES["test_block_and_blinker"] = f"block still, blinker period 2 on {len(core.TOPOLOGIES)} surfaces"


def test_glider_torus_returns():
    parts = []
    for W, H in [(8, 8), (12, 8), (9, 9), (7, 11)]:
        limit = 8 * W * H
        r = core.track_glider(W, H, "torus", limit)
        assert r["exact"] is not None, f"{W}x{H}: no exact return within {limit} gens"
        # The simple guess (1 step diagonally per 4 gens): 4*lcm(W,H). Printed, not asserted.
        parts.append(f"{W}x{H}: gen {r['exact']} (guess {4 * lcm(W, H)})")
    NOTES["test_glider_torus_returns"] = "; ".join(parts)


def test_glider_klein_returns_or_mirrors():
    LIMIT = 1000   # stated limit, in generations
    parts = []
    for W, H in [(8, 8), (12, 8), (9, 9)]:
        r = core.track_glider(W, H, "klein", LIMIT)
        assert r["exact"] is not None or r["mirror"] is not None, \
            f"{W}x{H}: neither exact nor mirror within {LIMIT} (died: {r['died']})"
        parts.append(f"{W}x{H}: exact {r['exact']}, mirror {r['mirror']} {r['mirror_kind'] or ''}".strip())
    NOTES["test_glider_klein_returns_or_mirrors"] = f"limit {LIMIT}; " + "; ".join(parts)


def test_population_matches_plane_far_from_edges():
    # R-pentomino in the middle of 32x32. Changes spread at most 1 cell per generation,
    # so for 10 generations no edge is reached and the gluing cannot matter yet.
    W = H = 32
    start = core.place(core.empty(W, H), core.PATTERNS["r_pentomino"], 14, 14, "plane")
    ref = [int(s.sum()) for s in core.simulate(start, "plane", 10)]
    for topo in ("torus", "klein", "projective"):
        pops = [int(s.sum()) for s in core.simulate(start, topo, 10)]
        assert pops == ref, f"{topo}: {pops} vs plane {ref}"
    NOTES["test_population_matches_plane_far_from_edges"] = f"populations gen 0..10: {ref}"


def test_vectors_reload_and_reproduce():
    with tempfile.TemporaryDirectory() as tmp:
        for topo in core.TOPOLOGIES:
            p = core.write_vectors(Path(tmp) / f"vectors_{topo}.txt", 12, 10, topo)
            wrong = core.check_vectors(p)
            assert not wrong, f"{topo}: wrong generations {wrong}"
    # Also check the real files from emit_verilog.py, if they exist yet.
    real = sorted((ROOT / "hardware" / "generated").glob("vectors_*.txt"))
    for p in real:
        wrong = core.check_vectors(p)
        assert not wrong, f"{p.name}: wrong generations {wrong}"
    NOTES["test_vectors_reload_and_reproduce"] = (
        f"temp files OK for {len(core.TOPOLOGIES)} surfaces; generated files checked: "
        f"{len(real)}" + ("" if real else " (run emit_verilog.py first)"))


if __name__ == "__main__":
    tests = [f for name, f in list(globals().items()) if name.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"OK      {t.__name__}: {NOTES.get(t.__name__, '')}")
        except AssertionError as e:
            failed += 1
            print(f"FAILED  {t.__name__}: {e}")
    print(f"{len(tests) - failed}/{len(tests)} tests passed")
    sys.exit(1 if failed else 0)
