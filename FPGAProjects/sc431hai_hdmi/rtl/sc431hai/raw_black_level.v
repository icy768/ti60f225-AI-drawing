// RAW8-domain black-level correction before framebuffer, color gain and gamma.
// Four pixels per cycle; purely combinational, so timing/valid signals do not shift.
module raw_black_level #(
    parameter [7:0] BLACK_LEVEL=8'd16
)(
    input wire [31:0] raw_pixels,
    output wire [31:0] corrected_pixels
);
    genvar p;
    generate for(p=0;p<4;p=p+1) begin: pixel
        wire [7:0] sample_value=raw_pixels[p*8 +: 8];
        assign corrected_pixels[p*8 +: 8] =
            sample_value>BLACK_LEVEL ? sample_value-BLACK_LEVEL : 8'd0;
    end endgenerate
endmodule
