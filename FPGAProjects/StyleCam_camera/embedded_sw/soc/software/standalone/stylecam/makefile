PROJ_NAME=stylecam

STANDALONE=..

SRCS = 	$(wildcard src/*.c) \
        ${STANDALONE}/common/start.S \
        ${STANDALONE}/common/trap.S

CFLAGS += -Os

include ${STANDALONE}/common/bsp.mk
include ${STANDALONE}/common/riscv64-unknown-elf.mk
include ${STANDALONE}/common/standalone.mk

LDSCRIPT = ${BSP_PATH}/linker/default.ld
