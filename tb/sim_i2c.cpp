// tb/sim_i2c.cpp
// Testbench for i2c_master - verifies I2C protocol output

#include "Vi2c_master.h"
#include "verilated.h"
#include <cstdio>
#include <cstdint>

int main(int argc, char **argv) {
    Verilated::commandArgs(argc, argv);
    auto *tb = new Vi2c_master;
    
    // Reset sequence
    tb->clk_i = 0;
    tb->rst_n_i = 0;
    tb->start_i = 0;
    tb->dev_addr_i = 0x39;  // ADV7513 address
    tb->reg_addr_i = 0x41;  // Example register
    tb->data_i = 0x00;      // Example data
    
    for (int i = 0; i < 20; i++) {
        tb->clk_i = 1; tb->eval();
        tb->clk_i = 0; tb->eval();
    }
    tb->rst_n_i = 1;
    
    // Issue start command
    tb->start_i = 1;
    tb->clk_i = 1; tb->eval();
    tb->clk_i = 0; tb->eval();
    tb->start_i = 0;
    
    // Run until done, monitoring bus
    bool prev_sda = true, prev_scl = true;
    int cycle_count = 0;
    
    printf("Monitoring I2C bus...\n");
    
    while (!tb->done_o && cycle_count < 100000) {
        tb->clk_i = 1; 
        tb->eval();
        
        bool sda = (tb->sda_io == 0) ? false : true;  // 0 = pulled low, 1 = released
        bool scl = (tb->scl_io == 0) ? false : true;
        
        // Detect edges and print bus activity
        if (scl != prev_scl) {
            if (scl) {
                // Rising edge of SCL - slave samples SDA here
                printf("SCL↑ SDA=%d (cycle %d)\n", sda ? 1 : 0, cycle_count);
            } else {
                // Falling edge of SCL
                printf("SCL↓ SDA=%d (cycle %d)\n", sda ? 1 : 0, cycle_count);
            }
        }
        
        if (sda != prev_sda && scl) {
            // SDA changed while SCL high - START or STOP condition
            if (!sda) {
                printf("*** START detected at cycle %d ***\n", cycle_count);
            } else {
                printf("*** STOP detected at cycle %d ***\n", cycle_count);
            }
        }
        
        prev_sda = sda;
        prev_scl = scl;
        
        tb->clk_i = 0; 
        tb->eval();
        cycle_count++;
    }
    
    printf("\nTransaction completed in %d cycles\n", cycle_count);
    if (tb->ack_err_o) {
        printf("ERROR: ACK error detected!\n");
    } else {
        printf("SUCCESS: Transaction completed without errors\n");
    }
    
    delete tb;
    return 0;
}