# Makefile for rv32-apu simulation

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

# sim/cordic_golden.hex is generated from the model, so a stale file can never
# cross-check the RTL: make rebuilds it whenever cordic_golden.py changes.
sim/cordic_golden.hex: tb/cordic_golden.py
	@mkdir -p sim
	python3 tb/cordic_golden.py emit sim/cordic_golden.hex

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

# apu_cordic is standalone (not yet instantiated in de10nano_top), so it gets
# its own lint rather than being folded into lint_top, whose top is de10nano_top.
lint_cordic: rtl/apu_cordic.sv
	verilator --lint-only -Wall --top-module apu_cordic rtl/apu_cordic.sv

# Clean up build artifacts
clean:
	rm -rf obj_dir
	rm -f sim/*.ppm
	rm -f sim/cordic_golden.hex

# sim/ and obj_dir/ are real directories, so the run targets must be phony
# or make treats them as up to date on a rerun
.PHONY: sim sim_i2c sim_config sim_cordic lint lint_i2c lint_top lint_cordic clean