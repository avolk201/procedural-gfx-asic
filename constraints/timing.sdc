# Timing constraints, DE10-Nano.
# Honest placeholder until Phase 2: the pixel clock PLL does not exist yet.
# Do not use this file for closure claims.

create_clock -name clk_50m -period 20.000 [get_ports clk_50m_i]

# TODO(Phase 2): once the PLL exists, add
#   create_generated_clock for the 25.175 MHz pixel clock sourced from the
#   actual PLL output pin (name it after the real instance hierarchy), and
#   an output clock constraint on hdmi_tx_clk for the ADV7513 interface.
