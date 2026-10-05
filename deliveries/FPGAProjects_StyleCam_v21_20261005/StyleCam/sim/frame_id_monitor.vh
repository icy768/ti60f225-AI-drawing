// Simulation-only identity scoreboard. Does not alter synthesized RTL.
integer trace_fd, source_id = 0, capture_id = 0, nn_id = 0;
integer a_ids[0:3], b_ids[0:3];
initial begin
    trace_fd = $fopen("frame_ids.csv", "w");
    $fwrite(trace_fd, "time_ns,event,frame_id\n");
    for (integer k = 0; k < 4; k = k + 1) begin a_ids[k] = 0; b_ids[k] = 0; end
end
always @(posedge clk_axi) if (!rst) begin
    if (dut.u_core.cam_go) begin
        source_id = source_id + 1;
        $fwrite(trace_fd, "%0d,source,%0d\n", $time, source_id);
        capture_id = source_id;
    end
    if (dut.u_core.cw_done) begin
        a_ids[dut.u_core.a_wr] = capture_id;
        $fwrite(trace_fd, "%0d,camera_complete,%0d\n", $time, capture_id);
    end
    if (dut.u_core.nn_start) begin
        nn_id = a_ids[dut.u_core.a_nn];
        $fwrite(trace_fd, "%0d,nn_start,%0d\n", $time, nn_id);
    end
    if (dut.u_core.nw_done) begin
        b_ids[dut.u_core.b_wr] = nn_id;
        $fwrite(trace_fd, "%0d,nn_complete,%0d\n", $time, nn_id);
    end
    if (!dut.u_core.dr_run && !dut.u_core.dr_start && dut.u_core.req_valid &&
        !dut.u_core.req_take && dut.u_core.req_data[11] && dut.u_core.b_latest_v)
        $fwrite(trace_fd, "%0d,display_commit,%0d\n", $time, b_ids[dut.u_core.b_latest]);
end
