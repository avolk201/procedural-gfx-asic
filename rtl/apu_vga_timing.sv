module apu_vga_timing (
	input  logic             clk_pix_i,
	input  logic             rst_n_i,
	output logic             hsync_o,
	output logic             vsync_o,
	output logic             de_o,
	output apu_pkg::coord_t  x_o,
	output apu_pkg::coord_t  y_o,
	output logic             sof_o,
	output logic             sol_o
);

	logic [9:0] h_cnt, h_cnt_next;
	logic [9:0] v_cnt, v_cnt_next;
	logic       de_next;
	logic       hsync_next;
	logic       vsync_next;
	logic       sof_next;
	logic       sol_next;

    // Sync region boundaries (derived from package constants)
	localparam int unsigned H_SYNC_START = apu_pkg::ACTIVE_W + apu_pkg::H_FP;
	localparam int unsigned H_SYNC_END   = H_SYNC_START + apu_pkg::HSYNC_WIDTH;
	localparam int unsigned V_SYNC_START = apu_pkg::ACTIVE_H + apu_pkg::V_FP;
	localparam int unsigned V_SYNC_END   = V_SYNC_START + apu_pkg::VSYNC_WIDTH;

	always_comb begin
		if (h_cnt == apu_pkg::coord_t'(apu_pkg::H_TOTAL - 1)) begin
			h_cnt_next = '0;
			if (v_cnt == apu_pkg::coord_t'(apu_pkg::V_TOTAL - 1))
				v_cnt_next = '0;
			else
				v_cnt_next = v_cnt + 1'b1;
		end else begin
			h_cnt_next = h_cnt + 1'b1;
			v_cnt_next = v_cnt;
		end

		de_next = (h_cnt < apu_pkg::coord_t'(apu_pkg::ACTIVE_W)) &&
				  (v_cnt < apu_pkg::coord_t'(apu_pkg::ACTIVE_H));
        		// HSync active low during sync pulse region

		hsync_next = !(h_cnt >= apu_pkg::coord_t'(H_SYNC_START) && 
		               h_cnt <  apu_pkg::coord_t'(H_SYNC_END));
		vsync_next = !(v_cnt >= apu_pkg::coord_t'(V_SYNC_START) && 
		               v_cnt <  apu_pkg::coord_t'(V_SYNC_END));

		sol_next = h_cnt_next == '0;
		sof_next = sol_next && (v_cnt_next == '0);
	end

	always_ff @(posedge clk_pix_i or negedge rst_n_i) begin
		if (!rst_n_i) begin
			h_cnt <= '0;
			v_cnt <= '0;
		end else begin
			h_cnt <= h_cnt_next;
			v_cnt <= v_cnt_next;
		end
	end

	always_ff @(posedge clk_pix_i or negedge rst_n_i) begin
		if (!rst_n_i) begin
			hsync_o <= 1'b1;
			vsync_o <= 1'b1;
			de_o    <= 1'b0;
			x_o     <= '0;
			y_o     <= '0;
			sof_o   <= 1'b0;
			sol_o   <= 1'b0;
		end else begin
			hsync_o <= hsync_next;
			vsync_o <= vsync_next;
			de_o    <= de_next;
			x_o     <= h_cnt;
			y_o     <= v_cnt;
			sof_o   <= sof_next;
			sol_o   <= sol_next;
		end
	end
endmodule
