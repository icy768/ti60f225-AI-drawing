// Exercise the shipped UART configuration and byte parser, including hostile headers.
#include <cassert>
#include <vector>
#include "../../esp32s3_stream/esp32s3_stream.ino"

static std::vector<uint8_t> packet(uint8_t seq, uint8_t value,
                                 uint8_t w = PREVIEW_W, uint8_t h = PREVIEW_H,
                                 uint8_t fmt = 0, uint16_t len = PREVIEW_BYTES) {
  std::vector<uint8_t> p = {0xA5, 0x5A, 1, seq, w, h, fmt, uint8_t(len), uint8_t(len >> 8)};
  p.insert(p.end(), len, value);
  uint16_t crc = 0xffff;
  for (uint8_t b : p) crc = crcStep(crc, b);
  p.push_back(uint8_t(crc)); p.push_back(uint8_t(crc >> 8));
  return p;
}
static void feed(const std::vector<uint8_t>& bytes) {
  for (uint8_t b : bytes) consumeFpgaByte(b);
}
int main() {
  setup();
  assert(Serial1.baud == 3030303 && Serial1.rxPin == 18 && Serial1.txPin == -1);
  assert(Serial2.baud == 115200 && Serial2.rxPin == 16 && Serial2.txPin == 17);
  forwardCommand('2');
  assert(Serial1.writes == 0 && Serial2.writes == 1 && Serial2.lastByte == '2');
  uint16_t check = 0xffff;
  for (const char* p = "123456789"; *p; ++p) check = crcStep(check, *p);
  assert(check == 0x29b1);
  std::vector<uint8_t> snapshot(PREVIEW_BYTES);
  uint32_t seq;
  assert(!copyFrame(snapshot.data(), &seq));
  auto good = packet(42, 0x11);
  // A partial UART read cannot publish; all parser state must survive between calls.
  feed(std::vector<uint8_t>(good.begin(), good.begin() + 123));
  assert(frameCount == 0);
  feed(std::vector<uint8_t>(good.begin() + 123, good.end()));
  assert(frameCount == 1 && copyFrame(snapshot.data(), &seq) && seq == 42);
  for (auto b : snapshot) assert(b == 0x11);
  auto bad = packet(99, 0x22); bad.back() ^= 0x40;
  feed(bad);
  assert(frameCount == 1 && frameSeq == 42 && lastSeq == 42);
  // Correct CRC cannot legitimise a geometry/format/length outside the allocated frame.
  feed(packet(100, 0x33, 255, 255));
  feed(packet(101, 0x33, PREVIEW_W, PREVIEW_H, 1));
  feed(packet(102, 0x33, PREVIEW_W, PREVIEW_H, 0, 65535));
  assert(frameCount == 1 && frameW == PREVIEW_W && frameH == PREVIEW_H);
  feed(packet(255, 0x44)); feed(packet(0, 0x55));
  assert(frameCount == 3 && frameSeq == 0);
  // The caller's snapshot survives both buffer swaps and reuse by the receiver.
  for (auto b : snapshot) assert(b == 0x11);
  assert(copyFrame(snapshot.data(), &seq) && seq == 0);
  for (auto b : snapshot) assert(b == 0x55);
  // All 256 RGB332 codes, including RGB primaries, must expand correctly.
  auto reduced = packet(1, 0, PREVIEW_W, PREVIEW_H, 1, PREVIEW_W * PREVIEW_H);
  for (size_t i = 0; i < PREVIEW_W * PREVIEW_H; ++i) reduced[9+i] = uint8_t(i);
  uint16_t crc = 0xffff;
  for (size_t i = 0; i < reduced.size()-2; ++i) crc=crcStep(crc,reduced[i]);
  reduced[reduced.size()-2]=uint8_t(crc); reduced.back()=uint8_t(crc>>8);
  feed(reduced);
  assert(frameCount==4 && copyFrame(snapshot.data(),&seq) && seq==1);
  for (size_t i=0; i<PREVIEW_W*PREVIEW_H; ++i) {
    unsigned v=uint8_t(i), r=v>>5, g=(v>>2)&7, b=v&3;
    // Independent normalised scaling with rounding equals bit replication.
    uint16_t want=((r*31+3)/7)<<11 | ((g*63)/7)<<5 | ((b*31+1)/3);
    assert((snapshot[2*i] | snapshot[2*i+1]<<8)==want);
  }
  reduced.back()^=1; feed(reduced); assert(frameCount==4);
  feed(packet(2,0x66)); assert(frameCount==5);
  feed(packet(3,0,PREVIEW_W,PREVIEW_H,2,PREVIEW_W*PREVIEW_H));
  assert(frameCount==5);
  printf("PASS real bridge: UART, CRC, malformed headers, wrap, snapshots, RGB565/RGB332 interleaving, 256 colour codes\n");
}
