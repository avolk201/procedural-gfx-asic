// i2c_controller - write-only I2C controller for ADV7513 configuration.

module i2c_controller #(
    parameter int unsigned CLK_DIV = 250
)(
    input  logic       clk_i,
    input  logic       rst_n_i,
    input  logic       start_i,
    input  logic [6:0] dev_addr_i,
    input  logic [7:0] reg_addr_i,
    input  logic [7:0] data_i,
    output logic       busy_o,
    output logic       done_o,
    output logic       ack_err_o,
    input  logic       sda_i,
    input  logic       scl_i,
    output logic       sda_oe_o,
    output logic       scl_oe_o
);

    logic sda_oe, scl_oe;
    assign sda_oe_o = sda_oe;
    assign scl_oe_o = scl_oe;

    logic tick;
    int unsigned count;
    always_ff @(posedge clk_i or negedge rst_n_i) begin
        if (!rst_n_i)
            count <= '0;
        else if (count == CLK_DIV-1)
            count <= '0;
        else
            count <= count + 1'b1;
    end
    assign tick = (count == CLK_DIV-1);
    
    typedef enum logic [2:0] {
        IDLE, START, SEND_BYTE, ACK, STOP, DONE
    } state_t;

    state_t state;
    logic [1:0] byte_idx;
    logic [2:0] bit_cnt;
    logic       phase;
    logic [7:0] tx_byte;

    always_comb begin
        case (byte_idx)
            2'd0:    tx_byte = {dev_addr_i, 1'b0};
            2'd1:    tx_byte = reg_addr_i;
            2'd2:    tx_byte = data_i;
            default: tx_byte = data_i;
        endcase
    end

    always_ff @(posedge clk_i or negedge rst_n_i) begin
        if (!rst_n_i) begin
            state     <= IDLE;
            sda_oe    <= 1'b0;
            scl_oe    <= 1'b0;
            byte_idx  <= 2'd0;
            bit_cnt   <= 3'd0;
            phase     <= 1'b0;
            done_o    <= 1'b0;
            ack_err_o <= 1'b0;
            busy_o    <= 1'b0;
        end 
        else if (tick) begin
            done_o <= 1'b0;
            case (state)
                IDLE: begin
                    sda_oe <= 1'b0;
                    scl_oe <= 1'b0;
                    if (start_i) begin
                        state  <= START;
                        busy_o <= 1'b1;
                    end
                end
                START: begin
                    sda_oe <= 1'b1; 
                    scl_oe <= 1'b0;
                    state   <= SEND_BYTE;
                    bit_cnt <= 3'd7;
                    phase   <= 1'b0;
                    byte_idx <= 2'd0;
                end
                SEND_BYTE: begin
                    if (phase == 1'b0) begin
                        scl_oe <= 1'b1;
                        sda_oe <= ~tx_byte[bit_cnt];
                        phase  <= 1'b1;
                    end else begin
                        scl_oe <= 1'b0;
                        phase  <= 1'b0;
                        if (bit_cnt == 3'd0) begin
                            state <= ACK;
                        end else begin
                            bit_cnt <= bit_cnt - 1'b1;
                        end
                    end
                end
                ACK: begin
                    if (phase == 1'b0) begin
                        scl_oe <= 1'b1;
                        sda_oe <= 1'b0;
                        phase  <= 1'b1;
                    end else begin
                        scl_oe <= 1'b0;
                        phase  <= 1'b0;
                        if (sda_i == 1'b1) ack_err_o <= 1'b1;
                        byte_idx <= byte_idx + 1'b1;
                        if (byte_idx == 2'd2) begin
                            state   <= STOP;
                            bit_cnt <= 3'd2;  // STOP walks 2 -> 1 -> 0
                        end else begin
                            state   <= SEND_BYTE;
                            bit_cnt <= 3'd7;  // reload MSB for the next byte
                        end
                    end
                end
                STOP: begin
                    if (bit_cnt == 3'd2) begin
                        sda_oe <= 1'b1; scl_oe <= 1'b1;
                        bit_cnt <= 3'd1;
                    end else if (bit_cnt == 3'd1) begin
                        sda_oe <= 1'b1; scl_oe <= 1'b0;
                        bit_cnt <= 3'd0;
                    end else begin
                        sda_oe <= 1'b0; scl_oe <= 1'b0;
                        state <= DONE;
                    end
                end
                DONE: begin
                    done_o <= 1'b1;
                    busy_o <= 1'b0;
                    state  <= IDLE;
                end
                default: state <= IDLE;
            endcase
        end
    end

    logic _unused_ok = &{1'b0, scl_i};

endmodule
