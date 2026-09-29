# Makefile for procedural-gfx-fpga simulation

RTL = rtl/apu_pkg.sv rtl/apu_vga_timing.sv rtl/apu_cordic.sv rtl/apu_colorbars.sv rtl/apu_plasma.sv rtl/apu_top.sv
TB  = tb/sim_main.cpp
OUT = sim_apu_top

sim: $(RTL) $(TB)
	@mkdir -p sim
	verilator --cc --exe --build -Wall --top-module apu_top $(RTL) $(TB) -o $(OUT)
	./obj_dir/$(OUT)

sim_i2c: rtl/i2c_controller.sv tb/sim_i2c.cpp
	@mkdir -p sim
	verilator --cc --exe --build -Wall --top-module i2c_controller rtl/i2c_controller.sv tb/sim_i2c.cpp -o sim_i2c
	./obj_dir/sim_i2c

sim_config: rtl/adv7513_config.sv rtl/i2c_controller.sv tb/tb_adv7513_config.sv tb/sim_adv7513_config.cpp
	@mkdir -p sim
	verilator --cc --exe --build -Wall --top-module tb_adv7513_config tb/tb_adv7513_config.sv rtl/adv7513_config.sv rtl/i2c_controller.sv tb/sim_adv7513_config.cpp -o sim_adv7513_config
	./obj_dir/sim_adv7513_config

# Look check for the plasma scene: one frame to sim/plasma_frame.ppm for
# eyeballing against anim/render.py's output. SCENE is overridden only here;
# the board build picks PLASMA in de10nano_top and the default sim stays
# colorbars, so no regression path depends on this target's result.
sim_plasma: $(RTL) tb/sim_plasma.cpp
	@mkdir -p sim
	verilator --cc --exe --build -Wall --top-module apu_top -GSCENE=1 $(RTL) tb/sim_plasma.cpp -o sim_plasma
	./obj_dir/sim_plasma

# Randomized-reset tier: kills reliance on zero-init state machines. Verilator
# stays 2-state; this is a seed sweep, not X-propagation. 5 seeds green on
# sim, plasma and cordic harnesses, measured 2026-09-28.
XSEEDS = 1 2 3 4 5

xprop: $(RTL) tb/sim_main.cpp
	@mkdir -p sim
	verilator --cc --exe --build -Wall --top-module apu_top --x-initial unique --x-assign unique $(RTL) tb/sim_main.cpp -o sim_xprop
	@for s in $(XSEEDS); do ./obj_dir/sim_xprop +verilator+rand+reset+2 +verilator+seed+$$s > /dev/null || { echo "xprop: FAIL seed $$s"; exit 1; }; done
	@echo "xprop: all seeds green"

# sim/cordic_golden.hex is generated from the model, so a stale file can never
# cross-check the RTL: make rebuilds it whenever cordic_golden.py changes.
# The pinned sha256 catches environment drift: a python or libm that would
# emit a different table fails here instead of silently re-baselining.
sim/cordic_golden.hex: tb/cordic_golden.py tb/cordic_golden.sha256
	@mkdir -p sim
	python3 tb/cordic_golden.py emit sim/cordic_golden.hex
	shasum -a 256 -c tb/cordic_golden.sha256

sim_cordic: rtl/apu_cordic.sv tb/sim_cordic.cpp sim/cordic_golden.hex
	verilator --cc --exe --build -Wall --top-module apu_cordic rtl/apu_cordic.sv tb/sim_cordic.cpp -o sim_cordic
	./obj_dir/sim_cordic

# Lint only (no C++ build)
lint: $(RTL)
	verilator --lint-only -Wall --top-module apu_top $(RTL)

lint_i2c: rtl/i2c_controller.sv
	verilator --lint-only -Wall rtl/i2c_controller.sv

lint_top: rtl/apu_pkg.sv rtl/apu_vga_timing.sv rtl/apu_cordic.sv rtl/apu_colorbars.sv rtl/apu_plasma.sv rtl/apu_top.sv rtl/i2c_controller.sv rtl/adv7513_config.sv rtl/pll_25m.sv rtl/de10nano_top.sv
	verilator --lint-only -Wall --top-module de10nano_top rtl/apu_pkg.sv rtl/apu_vga_timing.sv rtl/apu_cordic.sv rtl/apu_colorbars.sv rtl/apu_plasma.sv rtl/apu_top.sv rtl/i2c_controller.sv rtl/adv7513_config.sv rtl/pll_25m.sv rtl/de10nano_top.sv rtl/sync_reset.sv

# apu_cordic gets its own lint as a fast standalone check; lint_top covers
# it in-tree (instantiated via apu_plasma under apu_top).
lint_cordic: rtl/apu_cordic.sv
	verilator --lint-only -Wall --top-module apu_cordic rtl/apu_cordic.sv

golden:
	python3 tb/cordic_golden.py

tools-tests:
	python3 tools/tests/test_rv32asm.py
	python3 tools/tests/test_rv32enc.py
	python3 tools/tests/test_rv32iss.py

# Serial on purpose: every Verilator target builds into obj_dir, and
# $(MAKE) -j1 defeats an inherited -j from `make -j8 regress`.
GATES = lint lint_top lint_cordic lint_i2c sim sim_i2c sim_config golden sim_cordic sim_plasma tools-tests

regress:
	@for t in $(GATES); do printf "== %s\n" $$t; $(MAKE) -j1 $$t || exit 1; done
	@echo "regress: all gates green"

# Coverage tier: build every harness with --coverage into its own Mdir under
# sim/ (gitignored), run each with a per-target dat, merge, enforce floors.
# Floors are baseline minus margin (B10 convention): measured 2026-09-29 and
# recorded in docs/verification.md. Tighten with a new measurement, never
# loosen without one.
COV_LINE_FLOOR = 85
COV_TOGGLE_FLOOR = 84

coverage: sim/cordic_golden.hex
	@mkdir -p sim/cov
	verilator --cc --exe --build -Wall --coverage --top-module apu_top --Mdir sim/obj_cov_apu $(RTL) tb/sim_main.cpp -o sim_cov_apu
	verilator --cc --exe --build -Wall --coverage --top-module apu_top --Mdir sim/obj_cov_plasma -GSCENE=1 $(RTL) tb/sim_plasma.cpp -o sim_cov_plasma
	verilator --cc --exe --build -Wall --coverage --top-module i2c_controller --Mdir sim/obj_cov_i2c rtl/i2c_controller.sv tb/sim_i2c.cpp -o sim_cov_i2c
	verilator --cc --exe --build -Wall --coverage --top-module tb_adv7513_config --Mdir sim/obj_cov_config tb/tb_adv7513_config.sv rtl/adv7513_config.sv rtl/i2c_controller.sv tb/sim_adv7513_config.cpp -o sim_cov_config
	verilator --cc --exe --build -Wall --coverage --top-module apu_cordic --Mdir sim/obj_cov_cordic rtl/apu_cordic.sv tb/sim_cordic.cpp -o sim_cov_cordic
	./sim/obj_cov_apu/sim_cov_apu
	mv sim/coverage.dat sim/cov/apu.dat
	./sim/obj_cov_plasma/sim_cov_plasma
	mv sim/coverage.dat sim/cov/plasma.dat
	./sim/obj_cov_i2c/sim_cov_i2c
	mv sim/coverage.dat sim/cov/i2c.dat
	./sim/obj_cov_config/sim_cov_config
	mv sim/coverage.dat sim/cov/config.dat
	./sim/obj_cov_cordic/sim_cov_cordic
	mv sim/coverage.dat sim/cov/cordic.dat
	verilator_coverage --write sim/cov/merged.dat sim/cov/apu.dat sim/cov/plasma.dat sim/cov/i2c.dat sim/cov/config.dat sim/cov/cordic.dat
	verilator_coverage sim/cov/merged.dat | tee sim/cov/summary.txt
	@python3 -c "import re, sys; t = open('sim/cov/summary.txt').read(); g = lambda k: float(re.search(k + r'\s*: ([0-9.]+)%', t).group(1)); line, toggle = g('line'), g('toggle'); print(f'coverage floors: line >= $(COV_LINE_FLOOR), toggle >= $(COV_TOGGLE_FLOOR); measured line {line}, toggle {toggle}'); sys.exit(0 if line >= $(COV_LINE_FLOOR) and toggle >= $(COV_TOGGLE_FLOOR) else 1)"

# Clean up build artifacts
clean:
	rm -rf obj_dir
	rm -f sim/*.ppm
	rm -f sim/cordic_golden.hex

# sim/ and obj_dir/ are real directories, so the run targets must be phony
# or make treats them as up to date on a rerun
.PHONY: sim sim_plasma sim_i2c sim_config sim_cordic lint lint_i2c lint_top lint_cordic regress tools-tests golden xprop coverage clean