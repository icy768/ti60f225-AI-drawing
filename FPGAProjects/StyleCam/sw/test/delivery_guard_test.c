#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include "vision.h"

static unsigned writes;
static uint32_t base;
void host_wr(uint32_t offset, uint32_t value)
{
    writes++;
    if (offset == V_BUF_BASE) base = value;
}
uint32_t host_rd(uint32_t offset) { return offset == V_BUF_BASE ? base : 0; }

int main(void)
{
    uint32_t good[] = {0x53544e31u, 1, 3, 0, 0, 0, 0};
    assert(vision_load_blob(0, 7) < 0);
    assert(vision_load_blob(good, 3) < 0);
    assert(vision_load_blob(good, 6) < 0);
    good[1] = 0xffffffffu;
    assert(vision_load_blob(good, 7) < 0);
    good[1] = 1; good[2] = 4;
    assert(vision_load_blob(good, 7) < 0);
    good[2] = 3; good[3] = 1;
    assert(vision_load_blob(good, 7) < 0);
    assert(writes == 0);
    good[3] = 0;
    assert(vision_load_blob(good, 7) == 1 && writes == 3);
    assert(vision_set_buffer_base(1) < 0);
    assert(vision_set_buffer_base(0xffe00000u) < 0);
    assert(writes == 3);
    assert(vision_set_buffer_base(0x02000000u) == 0);
    assert(base == 0x02000000u && writes == 4);
    puts("DELIVERY GUARDS PASS");
    return 0;
}
