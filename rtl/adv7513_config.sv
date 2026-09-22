// rtl/adv7513_config.sv
// Walks a static ROM of (reg, val) pairs to configure the ADV7513 HDMI transmitter.
// Halts on ack_err_i (D10) or holds done_o upon reaching the final entry.

module adv7513_config (
    input  logic       clk_i,
    input  logic       rst_n_i,
    input  logic       busy_i,
    input  logic       done_i,
    input  logic       ack_err_i,

    output logic       start_o,
    output logic [6:0] dev_addr_o,
    output logic [7:0] reg_addr_o,
    output logic [7:0] data_o,
    output logic       done_o,
    output logic       error_o
);

    typedef struct packed {
        logic [7:0] addr;
        logic [7:0] data;
    } config_entry_t;

    localparam int unsigned NUM_REGS = 13;

    // 640x480 RGB 4:4:4 in DVI mode. DVI bypasses infoframes and audio packets.
    localparam config_entry_t ROM [NUM_REGS] = '{
        '{8'h41, 8'h10}, // Power up analog core & TMDS transmitters
        // Required ADI fixed trim writes (Programming Guide sec 3.1)
        '{8'h98, 8'h03},
        '{8'h9A, 8'hE0},
        '{8'h9C, 8'h30},
        '{8'h9D, 8'h61},
        '{8'hA2, 8'hA4},
        '{8'hA3, 8'hA4},
        '{8'hE0, 8'hD0},
        '{8'hF9, 8'h00},
        '{8'h15, 8'h00}, // 24-bit RGB 4:4:4, rising edge clock
        '{8'h16, 8'h00}, // Style 1 pinout (D[23:16]=R, D[15:8]=G, D[7:0]=B)
        '{8'h17, 8'h00}, // 4:3, bypass internal DE generation
        '{8'hAF, 8'h04}  // DVI mode (bit 1 = 0)
    };

    typedef enum logic [1:0] {
        START_TX,
        WAIT_DONE,
        STATE_DONE,
        STATE_ERROR
    } fsm_state_t;

    fsm_state_t state;
    logic [3:0] rom_idx;

    assign dev_addr_o = 7'h39; // DE10-Nano ties ADV7513 PD/AD pin to GND
    assign reg_addr_o = ROM[rom_idx].addr;
    assign data_o     = ROM[rom_idx].data;

    assign start_o = (state == START_TX);
    assign done_o  = (state == STATE_DONE);
    assign error_o = (state == STATE_ERROR);

    always_ff @(posedge clk_i or negedge rst_n_i) begin
        if (!rst_n_i) begin
            state   <= START_TX;
            rom_idx <= '0;
        end else begin
            case (state)
                START_TX: begin
                    if (busy_i) state <= WAIT_DONE; // D1: hold start_o until sampled
                end

                WAIT_DONE: begin
                    if (done_i) begin
                        if (ack_err_i) begin
                            state <= STATE_ERROR;
                        end else if (rom_idx == 4'(NUM_REGS - 1)) begin
                            state <= STATE_DONE;
                        end else begin
                            rom_idx <= rom_idx + 1'b1;
                            state   <= START_TX;
                        end
                    end
                end

                STATE_DONE:  begin end
                STATE_ERROR: begin end
            endcase
        end
    end

endmodule
