# Timing constraints, DE10-Nano.
create_clock -name clk_50m -period 20.000 [get_ports clk_50m_i]

derive_pll_clocks
derive_clock_uncertainty


# Pushbuttons (asynchronous human inputs)
set_false_path -from [get_ports {btn_n_i[*]}]

# Diagnostic LEDs (static human-visible indicators)
set_false_path -to [get_ports {led_o[*]}]

# I2C bus (100 kHz open-drain, paced by FSM tick counter)
set_false_path -from [get_ports {hdmi_i2c_*}]
set_false_path -to [get_ports {hdmi_i2c_*}]

# The 50 MHz domain and the PLL pixel domain cross only through
# synchronizers: the pix-to-50m toggle pair behind the alive blink, and the
# 50m-to-pix reset synchronizer. Both are metastability-protected by
# construction, so STA must not time them as clocked paths (B15).
set_clock_groups -asynchronous \
    -group [get_clocks {clk_50m}] \
    -group [get_clocks {*divclk*}]
