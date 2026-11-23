<!-- hardware/PLAN.md -->
# Hardware plan

Every speed or size number in this plan is a HYPOTHESIS until a stage says otherwise.
A stage is only "done" when its check has really passed.

## Stage 0: Python model. Status: DONE

- **Input:** the Life rule B3/S23 and the gluing rules.
- **Output:** `twistlife/core.py`, tests, figures.
- **How I know it works:** `python tests/test_core.py` prints OK for every test. The fast step equals the slow, simple step.

## Stage 1: generated wiring and vectors. Status: DONE AS FILES, UNTESTED

- **Input:** the neighbour tables from Stage 0.
- **Output:** `hardware/generated/topology_<name>.vh` (8 wires per cell), `hardware/generated/vectors_<name>.txt` (start state and states after 1, 10, 100 generations, in hex), `hardware/cell.v`, `hardware/life_grid.v`.
- **How I know it works:** so far only Python reloads the vectors and gets the same states. No Verilog tool has read these files yet.

## Stage 2: simulate the Verilog. Status: NOT STARTED

- **Input:** the Stage 1 files and a testbench I still have to write (`hardware/tb_life.v`). The testbench reads a vector file with `$readmemh`, loads generation 0, gives 1, 10 and 100 clock ticks and compares.
- **Tool:** Icarus Verilog, an open-source Verilog simulator. For example:
  `iverilog -g2012 -I hardware/generated -o sim.vvp hardware/cell.v hardware/life_grid.v hardware/tb_life.v && vvp sim.vvp`
- **Output:** one line per surface and generation: match or no match.
- **How I know it works:** all four surfaces match at generations 1, 10 and 100. Then I break one wire on purpose and check that the testbench reports a mismatch, so I know the test can fail.

## Stage 3: synthesize for the PYNQ-Z2. Status: NOT STARTED

- **Input:** the simulated design from Stage 2.
- **Tool:** Vivado, for the Zynq-7020 chip on the PYNQ-Z2.
- **Output:** the utilization report (real LUT and flip-flop counts) and the timing report (highest safe clock speed).
- **How I know it works:** the reports exist. I divide the LUT count by the number of cells and replace `luts_per_cell` in `CONFIG` with the measured value. The README estimate is updated or removed.

## Stage 4: show it on the board. Status: NOT STARTED

- **Input:** the synthesized design, the board switches, HDMI out (or LEDs for a tiny grid or a population count).
- **Output:** a visible grid. The switches choose plane, torus, Klein bottle or projective plane. Only edge cells need a switch between wirings (HYPOTHESIS).
- **How I know it works:** a glider on the Klein bottle visibly comes back mirrored, like Figure 2. The board slows the update down so humans can see it. The state read back from the board equals the Python model for the same start.
