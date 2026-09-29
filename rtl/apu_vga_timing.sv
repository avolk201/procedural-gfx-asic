module apu_vga_timing #(
	parameter int unsigned DEPTH = 1
) (
	input  logic             clk_pix_i,
	input  logic             rst_n_i,
	output logic             hsync_o,
	output logic             vsync_o,
	output logic             de_o,
	output apu_pkg::coord_t  x_o,
	output apu_pkg::coord_t  y_o,
	output logic             sof_o,
	output logic             sol_o,
	// D18 prefetch: scene-side window, DEPTH clk ahead of the beam, so a
	// scene whose output is delayed by DEPTH lands exactly on the active
	// window. Contract: 1 <= DEPTH <= apu_pkg::H_BP (48).
	output logic             de_pre_o,
	output apu_pkg::coord_t  x_pre_o,
	output apu_pkg::coord_t  y_pre_o,
	output logic             sof_pre_o
);

	logic [9:0] h_cnt, h_cnt_next;
	logic [9:0] v_cnt, v_cnt_next;
	logic       de_next;
	logic       hsync_next;
	logic       vsync_next;
	logic       sof_next;
	logic       sol_next;

    // Sync region boundaries
	localparam int unsigned H_SYNC_START = apu_pkg::ACTIVE_W + apu_pkg::H_FP;
	localparam int unsigned H_SYNC_END   = H_SYNC_START + apu_pkg::HSYNC_WIDTH;
	localparam int unsigned V_SYNC_START = apu_pkg::ACTIVE_H + apu_pkg::V_FP;
	localparam int unsigned V_SYNC_END   = V_SYNC_START + apu_pkg::VSYNC_WIDTH;

	// D18 prefetch window: column c is fed to the scenes DEPTH clk before
	// the beam reaches it. PRE_START is the h_cnt at which the next line's
	// column 0 is fed; DEPTH <= H_BP keeps that inside the back porch.
	localparam int unsigned PRE_START = apu_pkg::H_TOTAL - DEPTH;

	logic [9:0] h_pre, v_pre;
	logic       pre_carry, v_wrap;
	logic       de_pre_next, sof_pre_next;

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

		// VESA 640x480@60Hz DMT specifies active-low sync pulses
		hsync_next = !(h_cnt >= apu_pkg::coord_t'(H_SYNC_START) && 
		               h_cnt <  apu_pkg::coord_t'(H_SYNC_END));
		vsync_next = !(v_cnt >= apu_pkg::coord_t'(V_SYNC_START) && 
		               v_cnt <  apu_pkg::coord_t'(V_SYNC_END));

		sol_next = h_cnt_next == '0;
		sof_next = sol_next && (v_cnt_next == '0);

		pre_carry = (h_cnt >= apu_pkg::coord_t'(PRE_START));
		h_pre = pre_carry ? (h_cnt - apu_pkg::coord_t'(PRE_START))
		                  : (h_cnt + apu_pkg::coord_t'(DEPTH));
		v_wrap = (v_cnt == apu_pkg::coord_t'(apu_pkg::V_TOTAL - 1));
		v_pre = pre_carry ? (v_wrap ? '0 : v_cnt + 1'b1) : v_cnt;
		de_pre_next = (h_pre < apu_pkg::coord_t'(apu_pkg::ACTIVE_W)) &&
		              (v_pre < apu_pkg::coord_t'(apu_pkg::ACTIVE_H));
		sof_pre_next = (h_cnt_next == apu_pkg::coord_t'(PRE_START)) && v_wrap;
	end

	logic [7:0]  hsync_low_cnt;
	logic [11:0] vsync_low_cnt;
	/* verilator lint_off SYNCASYNCNET */
	always_ff @(posedge clk_pix_i or negedge rst_n_i) begin
		if (!rst_n_i) begin
			hsync_low_cnt <= '0;
			vsync_low_cnt <= '0;
		end else begin
			hsync_low_cnt <= hsync_o ? '0 : hsync_low_cnt + 1'b1;
			vsync_low_cnt <= vsync_o ? '0 : vsync_low_cnt + 1'b1;
		end
	end

	logic hsync_o_d, vsync_o_d;
	logic hsync_seen_fall, vsync_seen_fall;
	always_ff @(posedge clk_pix_i or negedge rst_n_i) begin
		if (!rst_n_i) begin
			hsync_o_d       <= 1'b1;
			vsync_o_d       <= 1'b1;
			hsync_seen_fall <= 1'b0;
			vsync_seen_fall <= 1'b0;
		end else begin
			hsync_o_d <= hsync_o;
			vsync_o_d <= vsync_o;
			hsync_seen_fall <= hsync_seen_fall || (hsync_o_d && !hsync_o);
			vsync_seen_fall <= vsync_seen_fall || (vsync_o_d && !vsync_o);
		end
	end

	property p_hsync_width;
		@(posedge clk_pix_i) disable iff (!rst_n_i)
		(hsync_o && !hsync_o_d) && hsync_seen_fall |-> hsync_low_cnt == 8'(apu_pkg::HSYNC_WIDTH);
	endproperty
	assert property (p_hsync_width) else $error("HSync width violation");

	property p_vsync_width;
		@(posedge clk_pix_i) disable iff (!rst_n_i)
		(vsync_o && !vsync_o_d) && vsync_seen_fall |-> vsync_low_cnt == 12'(apu_pkg::VSYNC_WIDTH * apu_pkg::H_TOTAL);
	endproperty
	assert property (p_vsync_width) else $error("VSync width violation");

	property p_de_not_in_hsync;
		@(posedge clk_pix_i) disable iff (!rst_n_i)
		!(de_o && !hsync_o);
	endproperty
	assert property (p_de_not_in_hsync) else $error("DE during HSync violation");

	property p_de_not_in_vsync;
		@(posedge clk_pix_i) disable iff (!rst_n_i)
		!(de_o && !vsync_o);
	endproperty
	assert property (p_de_not_in_vsync) else $error("DE during VSync violation");
	/* verilator lint_on SYNCASYNCNET */

	always_ff @(posedge clk_pix_i or negedge rst_n_i) begin
		if (!rst_n_i) begin
			h_cnt <= '0;
			// Start on the last v-blank line so the first active line is
			// fully prefetched (D18). Video begins one line later, inside
			// blanking; no frame ever loses its first DEPTH pixels.
			v_cnt <= apu_pkg::coord_t'(apu_pkg::V_TOTAL - 1);
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
			de_pre_o  <= 1'b0;
			x_pre_o   <= '0;
			y_pre_o   <= '0;
			sof_pre_o <= 1'b0;
		end else begin
			hsync_o <= hsync_next;
			vsync_o <= vsync_next;
			de_o    <= de_next;
			x_o     <= h_cnt;
			y_o     <= v_cnt;
			sof_o   <= sof_next;
			sol_o   <= sol_next;
			de_pre_o  <= de_pre_next;
			x_pre_o   <= h_pre;
			y_pre_o   <= v_pre;
			sof_pre_o <= sof_pre_next;
		end
	end
endmodule
