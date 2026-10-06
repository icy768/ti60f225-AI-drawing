#ifndef STYLECAM_BOARD_PROFILE_H
#define STYLECAM_BOARD_PROFILE_H

/* Confirm these values against the integrated BSP, clocks and linker map.
 * Until confirmed, main stops before accessing the vision APB peripheral.
 */
#ifndef STYLECAM_BOARD_CONFIRMED
#define STYLECAM_BOARD_CONFIRMED 0
#endif
#ifndef VISION_BASE
#define VISION_BASE 0xF8100000u
#endif
#ifndef F_AXI
#define F_AXI 150000000u
#endif
#ifndef STYLECAM_FRAME_BASE
#define STYLECAM_FRAME_BASE 0x00000000u
#endif
#define STYLECAM_FRAME_RESERVED_BYTES (7u * 0x200000u)

#endif
