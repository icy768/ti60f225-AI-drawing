`timescale 1ns/1ps
// Independent sensor model observes only physical SCL/SDA and enable.
// No ROM import, internal state access, forced values, or canned readback stream.
module stream_check_tb;
    reg clk=0;
    always #5 clk=~clk;
    tri1 scl,sda;
    wire scl_out,sda_out,scl_oe,sda_oe,enable,osc_enable;
    wire [7:0] leds;
    reg slave_low=0,stretch_low=0,stuck_sda=0;
    assign scl=scl_oe ? scl_out : 1'bz;
    assign scl=stretch_low ? 1'b0 : 1'bz;
    assign sda=sda_oe ? sda_out : 1'bz;
    assign sda=(slave_low || stuck_sda) ? 1'b0 : 1'bz;
    reg reset=1;
    wire id_ok,config_ok,stream_set,finished;
    wire [2:0] error_code;
    wire [7:0] command_index;
    wire [287:0] diagnostic_words;
    wire diagnostic_valid;
    assign scl_out=0; assign sda_out=0;
    sc431hai_setup #(.CLK_PER_MS(100),.I2C_TICK(20),.TIMEOUT_TICKS(40)) dut(
      .clk(clk),.reset(reset),.scl_in(scl),.sda_in(sda),.scl_low(scl_oe),.sda_low(sda_oe),
      .cam_enable(enable),.id_ok(id_ok),.config_ok(config_ok),.stream_set(stream_set),
      .finished(finished),.error_code(error_code),.command_index(command_index),
      .diagnostic_words(diagnostic_words),.diagnostic_valid(diagnostic_valid));
    initial begin repeat(10) @(negedge clk); reset=0;end
    reg [7:0] mem[0:65535];
    reg [7:0] shift=0,send_data=0;
    reg [15:0] address=0;
    integer scenario=0, mode=0,role=0,bits=0;
    integer starts=0,stops=0,restarts=0,writes=0,reads=0,stream_writes=0;
    integer i,saved_starts,expected_led;
    reg in_transaction=0,ack_ok=0,stretch_done=0;
    // modes: 0 idle, 1 receive, 2 transmit, 3 await STOP/START
    always @(negedge sda) if(scl===1'b1 && enable===1'b1) begin
        if(in_transaction) begin
            if(mode!=1 || role!=3 || bits>1) $fatal(1,"Malformed repeated START");
            restarts=restarts+1;
        end
        in_transaction=1; starts=starts+1;
        mode=1; role=0; bits=0; shift=0;
    end
    always @(posedge sda) if(scl===1'b1 && enable===1'b1 && in_transaction) begin
        if(mode!=3 && !(mode==1 && role==3 && bits<=1))
            $fatal(1,"Unexpected STOP mode=%0d role=%0d bits=%0d",mode,role,bits);
        stops=stops+1; in_transaction=0; mode=0;
    end
    always @(posedge scl) if(in_transaction) begin
        if(mode==1) begin
            if(bits<8) begin shift={shift[6:0],sda}; bits=bits+1; end
            else if(bits==8) bits=9;
        end else if(mode==2) begin
            if(bits<8) bits=bits+1;
            else if(bits==8) begin
                if(sda!==1'b1) $fatal(1,"Single-byte read must end with master NACK");
                bits=9;
            end
        end
    end
    always @(negedge scl) begin
        #1;
        if(in_transaction && mode==1) begin
            if(bits==8) begin
                ack_ok=1;
                if(role==0 && shift!=8'h60 && shift!=8'h61)
                    $fatal(1,"Wrong slave address %h",shift);
                if(scenario==2 && role==0) ack_ok=0;
                if(scenario==3 && role==3 && address==16'h301f) ack_ok=0;
                if(scenario==9 && role==1) ack_ok=0;
                if(scenario==10 && role==2) ack_ok=0;
                if(scenario==11 && role==0 && shift==8'h61) ack_ok=0;
                if(scenario==12 && role==0 && shift==8'h61 && address==16'h3e09 && stream_writes==1) ack_ok=0;
                slave_low=ack_ok;
            end else if(bits==9) begin
                slave_low=0; bits=0;
                if(!ack_ok) mode=3;
                else case(role)
                    0: if(shift==8'h61) begin
                        mode=2; send_data=mem[address]; reads=reads+1;
                        if(scenario==4 && address==16'h3208) send_data=8'h00;
                        if(scenario==13 && address==16'h3e08) send_data=8'h00;
                        slave_low=~send_data[7];
                    end else role=1;
                    1: begin address[15:8]=shift; role=2; end
                    2: begin address[7:0]=shift; role=3; end
                    3: begin
                        if(address==16'h3107 || address==16'h3108) $fatal(1,"Attempted write to chip ID");
                        if(address==16'h0100 && shift==1 &&
                          ({mem[16'h3208],mem[16'h3209]}!=1920 ||
                           {mem[16'h320a],mem[16'h320b]}!=1080 || mem[16'h4501]!=8'hac ||
                           mem[16'h3e08]!=8'h83 || mem[16'h3e09]!=8'h20))
                            $fatal(1,"Stream enabled before complete window/test configuration");
                        writes=writes+1;
                        if(address==16'h0100 && shift==1) stream_writes=stream_writes+1;
                        if(!(scenario==5 && address==16'h0100 && stream_writes==1 && shift==1))
                            mem[address]=shift;
                        mode=3;
                    end
                endcase
                shift=0;
            end
        end else if(in_transaction && mode==2) begin
            if(bits<8) slave_low=~send_data[7-bits];
            else if(bits==8) slave_low=0;
            else begin slave_low=0; mode=3; end
        end
    end
    // Stretch the first data clock, without looking inside the master.
    initial begin
        wait(scenario==6);
        wait(in_transaction);
        @(negedge scl); stretch_low=1; #2400; stretch_low=0; stretch_done=1;
    end
    initial begin
        if(!$value$plusargs("CASE=%d",scenario)) scenario=0;
        for(i=0;i<65536;i=i+1) mem[i]=0;
        mem[16'h3107]=8'hcd; mem[16'h3108]=(scenario==1)?8'h00:8'h6b;
        // Deliberately non-default gain bytes: diagnostics must report, not compare or write them.
        mem[16'h3e08]=8'h87;mem[16'h3e09]=8'h55;
        mem[16'h3e06]=8'h01;mem[16'h3e07]=8'ha0;
        if(scenario==7) stretch_low=1;
        if(scenario==8) stuck_sda=1;
        // Check real top-level POR and released pads before setup is allowed to run.
        repeat(200) @(negedge clk);
        if(enable!==0 || scl_oe!==0 || sda_oe!==0)
            $fatal(1,"Top startup outputs invalid");
        wait(enable===1);
        wait(finished===1); #1000;
        if(scenario==0 || scenario==6) begin
            if(error_code!=0 || !id_ok || !config_ok || !stream_set || !enable)
                $fatal(1,"Success status mismatch");
            if({mem[16'h3208],mem[16'h3209]}!==16'd1920 ||
               {mem[16'h320a],mem[16'h320b]}!==16'd1080 ||
               mem[16'h4501]!==8'ha4 || mem[16'h0100]!==1)
                $fatal(1,"SC431HAI mode mismatch");
            if(writes!=165 || reads!=25 || stream_writes!=1 || stops!=190 || restarts!=25)
                $fatal(1,"Protocol counts writes=%0d reads=%0d stops=%0d restarts=%0d",writes,reads,stops,restarts);
            if(!diagnostic_valid || diagnostic_words!=={
               32'h003e0000,32'h003e0146,32'h003e0200,
               8'd0,16'h320e,mem[16'h320e],8'd0,16'h320f,mem[16'h320f],
               32'h003e0883,32'h003e0920,32'h003e0601,32'h003e07a0})
                $fatal(1,"Incorrect diagnostic register capture: %h",diagnostic_words);
            if(scenario==6 && !stretch_done) $fatal(1,"Stretch not exercised");
        end else if(scenario==12) begin
            if(error_code!=2 || enable!==0 || !stream_set || !config_ok || diagnostic_valid)
                $fatal(1,"Partial diagnostic read incorrectly accepted");
        end else if(scenario==13) begin
            if(error_code!=3 || enable!==0 || stream_set || !config_ok || stream_writes!=0)
                $fatal(1,"Stream enabled despite gain readback mismatch");
        end else begin
            expected_led=(scenario==2 || scenario==3 || scenario>=9)?2:
                         ((scenario==7 || scenario==8)?4:3);
            if(error_code!=expected_led || enable!==0 || stream_set!==0)
                $fatal(1,"Failure not safely halted error=%0d",error_code);
            if((scenario==1 || scenario==2 || scenario>=9) && writes!=0)
                $fatal(1,"Writes after ID failure");
            if(scenario==5 && !config_ok) $fatal(1,"Lost config milestone");
            if(scenario!=5 && config_ok) $fatal(1,"False config milestone");
        end
        saved_starts=starts;
        repeat(3000) @(negedge clk);
        if(starts!=saved_starts || scl_oe!==0 || sda_oe!==0) $fatal(1,"Did not halt/release bus");
        $display("PASS case=%0d err=%02h writes=%0d reads=%0d starts=%0d stops=%0d",
                 scenario,error_code,writes,reads,starts,stops);
        $finish;
    end
    initial begin #20000000; $fatal(1,"Global test timeout"); end
endmodule
