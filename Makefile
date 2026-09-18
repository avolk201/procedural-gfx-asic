# Makefile for rv32-apu-tapeout simulation

RTL = rtl/apu_pkg.sv rtl/apu_vga_timing.sv
TB  = tb/sim_main.cpp
OUT = sim_vga_timing

# Default target: build and run simulation
sim: $(RTL) $(TB)
	@mkdir -p sim
	verilator --cc --exe --build -Wall --top-module apu_vga_timing $(RTL) $(TB) -o $(OUT)
	./obj_dir/$(OUT)

# Lint only (no C++ build)
lint: $(RTL)
	verilator --lint-only -Wall $(RTL)

# Clean up build artifacts
clean:
	rm -rf obj_dir
	rm -f sim/*.ppm

.PHONY: sim lint clean