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
