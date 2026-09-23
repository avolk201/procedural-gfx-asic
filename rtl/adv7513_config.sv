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
    // Sources: PG = ADV7513 Programming Guide Rev B.
    localparam config_entry_t ROM [NUM_REGS] = '{
        '{8'h41, 8'h00}, // Power up: 0x41[6]=0, other bits documented 0 (PG 4.7)
        // Fixed registers that must be set after power-up (PG Table 14, sec 4.2.9)
        '{8'h98, 8'h03},
        '{8'h9A, 8'hE0},
        '{8'h9C, 8'h30},
        '{8'h9D, 8'h61},
        '{8'hA2, 8'hA4},
        '{8'hA3, 8'hA4},
        '{8'hE0, 8'hD0},
        '{8'hF9, 8'h00},
        '{8'h15, 8'h00}, // Input ID 0: RGB 4:4:4, separate syncs (PG Table 16).
                         // [7:4] is the I2S sampling-frequency field; 0 is fine,
                         // audio is not enabled in Phase 2.
        '{8'h16, 8'h00}, // RGB 4:4:4: Input Style bits are don't-care (PG Table 16
                         // defines the pin map directly: D[23:16]=R, D[15:8]=G,
                         // D[7:0]=B). Only 4:2:2 formats use the style field.
        '{8'h17, 8'h00}, // Aspect 4:3 (PG 4.3.3); DE generator disabled, so the
                         // externally supplied DE passes through (PG 0x17[0]).
        '{8'hAF, 8'h00}  // DVI mode: 0xAF[1]=0 (PG Table 4)
    };

    typedef enum logic [1:0] {
        START_TX,
        WAIT_DONE,
        STATE_DONE,
        STATE_ERROR
    } fsm_state_t;

    fsm_state_t state;
    logic [3:0] rom_idx;

    // PD/AD low at power-up latches the 8-bit address 0x72, i.e. 7-bit 0x39
    // (HUG 6.1.5). The DE10-Nano PD/AD strap still needs confirming against
    // the board schematic; if pulled high the address is 0x3D instead.
    assign dev_addr_o = 7'h39;
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
