#include <assert.h>
#include <stdint.h>
#include "vision.h"
#include "net_blob.h"

static unsigned writes;
void host_wr(uint32_t off, uint32_t value) { (void)off; (void)value; writes++; }
uint32_t host_rd(uint32_t off) { (void)off; return 0; }

int main(void)
{
    uint32_t h[7] = {0x53544E31u, 1, NET_NSTYLE, 0, 0, 0, 0};
    assert(vision_load_blob(0, 7) == -1);
    assert(vision_load_blob(h, 3) == -1);
    assert(vision_load_blob(h, 6) == -2);
    h[1] = 0xffffffffu;
    assert(vision_load_blob(h, 7) == -2);
    h[1] = 1; h[2] = NET_NSTYLE + 1;
    assert(vision_load_blob(h, 7) == -3);
    h[2] = NET_NSTYLE; h[3] = 1;
    assert(vision_load_blob(h, 7) == -3);
    assert(writes == 0);
    assert(vision_load_blob(net_blob, NET_BLOB_WORDS) == 4050);
    assert(writes == 3u * 4050u);
    return 0;
}
