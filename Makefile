# Makefile for rv32-apu-tapeout simulation

# Added colorbars and top to the RTL list
RTL = rtl/apu_pkg.sv rtl/apu_vga_timing.sv rtl/apu_colorbars.sv rtl/apu_top.sv
TB  = tb/sim_main.cpp
OUT = sim_apu_top

# Default target: build and run simulation
sim: $(RTL) $(TB)
	@mkdir -p sim
	verilator --cc --exe --build -Wall --top-module apu_top $(RTL) $(TB) -o $(OUT)
	./obj_dir/$(OUT)

sim_i2c: rtl/i2c_controller.sv tb/sim_i2c.cpp
	@mkdir -p sim
	verilator --cc --exe --build -Wall --top-module i2c_controller rtl/i2c_controller.sv tb/sim_i2c.cpp -o sim_i2c
	./obj_dir/sim_i2c

# Lint only (no C++ build)
lint: $(RTL)
	verilator --lint-only -Wall $(RTL)

lint_i2c: rtl/i2c_controller.sv
	verilator --lint-only -Wall rtl/i2c_controller.sv

# Clean up build artifacts
clean:
	rm -rf obj_dir
	rm -f sim/*.ppm

.PHONY: sim lint lint_i2c clean