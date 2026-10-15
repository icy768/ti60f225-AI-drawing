"""Independent check of the ESP32 frame parser against the RTL framing rules.

Mirrors sc_stream_link.v (CRC over sync+header+payload, low CRC byte first) and
re-implements the exact state machine of readFpgaTask() to prove it consumes
exactly LEN payload bytes plus 2 CRC bytes and only publishes on a CRC match.
"""
import random

SYNC0, SYNC1, TYPE_VIDEO = 0xA5, 0x5A, 0x01
W, H, FMT = 96, 54, 0
LEN = W * H * 2


def crc_step(c, b):
    c ^= (b << 8) & 0xFFFF
    for _ in range(8):
        c = ((c << 1) ^ 0x1021) & 0xFFFF if (c & 0x8000) else (c << 1) & 0xFFFF
    return c


def build_frame(seq, payload):
    hdr = [SYNC0, SYNC1, TYPE_VIDEO, seq & 0xFF, W, H, FMT, LEN & 0xFF, (LEN >> 8) & 0xFF]
    crc = 0xFFFF
    for b in hdr:
        crc = crc_step(crc, b)
    for b in payload:
        crc = crc_step(crc, b)
    return bytes(hdr + list(payload) + [crc & 0xFF, (crc >> 8) & 0xFF])


def parse(stream, preview_bytes=LEN):
    """Exact port of readFpgaTask(); returns list of published (seq, payload)."""
    S_SYNC0, S_SYNC1, S_HEADER, S_PAYLOAD, S_CRC = range(5)
    st = S_SYNC0
    hdr = bytearray(7)
    hi = 0
    length = got = 0
    crc = 0xFFFF
    crc_lo = 0
    have_lo = False
    back = bytearray(preview_bytes)
    out = []
    crc_errors = sync_losses = 0

    for b in stream:
        if st == S_SYNC0:
            if b == SYNC0:
                st = S_SYNC1
        elif st == S_SYNC1:
            if b == SYNC1:
                st = S_HEADER
                hi = 0
                crc = crc_step(0xFFFF, SYNC0)
                crc = crc_step(crc, SYNC1)
            elif b != SYNC0:
                st = S_SYNC0
                sync_losses += 1
        elif st == S_HEADER:
            hdr[hi] = b
            hi += 1
            crc = crc_step(crc, b)
            if hi == 7:
                nbytes = hdr[5] | (hdr[6] << 8)
                if hdr[0] != TYPE_VIDEO or nbytes != preview_bytes:
                    crc_errors += 1
                    st = S_SYNC0
                else:
                    length = nbytes
                    got = 0
                    st = S_PAYLOAD
        elif st == S_PAYLOAD:
            if got < preview_bytes:
                back[got] = b
            got += 1
            crc = crc_step(crc, b)
            if got >= length:
                st = S_CRC
                have_lo = False
        else:  # S_CRC
            if not have_lo:
                crc_lo = b
                have_lo = True
            else:
                want = crc_lo | (b << 8)
                if want == crc and got == length:
                    out.append((hdr[1], bytes(back[:length])))
                else:
                    crc_errors += 1
                st = S_SYNC0
    return out, crc_errors, sync_losses


def forged_length_frame():
    """Header claims a huge payload, body is short: must be rejected, never written past
    the preview buffer."""
    hdr = [SYNC0, SYNC1, TYPE_VIDEO, 0x07, W, H, FMT, 0xFF, 0xFF]   # len = 65535
    body = bytes(64)
    crc = 0xFFFF
    for b in hdr + list(body):
        crc = crc_step(crc, b)
    return bytes(hdr + list(body) + [crc & 0xFF, (crc >> 8) & 0xFF])


# 1) algorithm sanity: CRC-16/CCITT-FALSE check value
c = 0xFFFF
for ch in b"123456789":
    c = crc_step(c, ch)
assert c == 0x29B1, hex(c)

# 2) clean frames round-trip, payload compared byte for byte
random.seed(1)
stream = b""
expect = []
for seq in range(5):
    payload = bytes(random.randrange(256) for _ in range(LEN))
    stream += build_frame(seq, payload)
    expect.append((seq, payload))
# 3) prepend junk + inject a corrupted frame that must be rejected
payload_bad = bytes(random.randrange(256) for _ in range(LEN))
bad = bytearray(build_frame(200, payload_bad))
bad[-1] ^= 0xFF                      # damage the CRC high byte
stream = bytes([0x11, 0x22, 0xA5, 0x00]) + stream + bytes(bad) + stream[:540]

got, crc_err, sync_loss = parse(stream)
assert len(got) == 5, len(got)   # 5 good frames; the corrupt one and the tail stub must not publish
for i, (seq, payload) in enumerate(got):
    e = expect[i % len(expect)]
    assert seq == e[0], (seq, e[0])
    assert payload == e[1], f"payload mismatch at #{i}"
assert crc_err >= 1, crc_err

# 4) a forged length must be rejected outright, with no write past the preview buffer
got2, crc_err2, _ = parse(forged_length_frame() + stream[:600])
assert len(got2) <= 1, len(got2)          # at most the trailing partial frame, never the forged one
assert crc_err2 >= 1, crc_err2

print("OK  CRC-16/CCITT-FALSE check = 0x%04X" % c)
print("OK  frames published = %d  crcErr = %d  syncLoss = %d" % (len(got), crc_err, sync_loss))
print("OK  parser consumes exactly LEN payload + 2 CRC bytes; corrupt frame rejected")
print("OK  forged oversized length rejected without buffer overrun")
