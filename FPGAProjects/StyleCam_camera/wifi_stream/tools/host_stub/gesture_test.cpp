/*
 * gesture_test.cpp - host self-test for the ESP32-side hand-gesture logic.
 *
 * Compiles the real esp32s3_stream.ino and drives gestureCentroid / gestureStep,
 * which are plain C, so the shipped threshold table and state machine are tested as
 * built rather than re-implemented.  A broken threshold or a gesture that can never
 * fire fails here instead of on the demo table.
 */
#include "Arduino.h"
#include "../../esp32s3_stream/esp32s3_stream.ino"

static int failures = 0;
#define CHECK(cond, what)                                \
  do {                                                   \
    if (cond) printf("  ok    %s\n", what);              \
    else      { printf("  FAIL  %s\n", what); failures++; } \
  } while (0)

int main() {
  printf("\ngesture (motion centroid + state machine)\n");

  /* ---- centroid: a 2x2 moving block in the middle of an 8x4 frame ---- */
  {
    const int w = 8, h = 4;
    uint8_t prev[8 * 4] = {0};              /* previous frame: all zero luma */
    uint8_t frame[8 * 4 * 2] = {0};         /* RGB565, little-endian */
    uint16_t green = 31u << 5;              /* green channel = 31 -> diff 31 */
    for (int y = 1; y <= 2; y++)
      for (int x = 2; x <= 3; x++) {
        size_t o = ((size_t)y * w + x) * 2;
        frame[o] = green & 0xFF; frame[o + 1] = green >> 8;
      }
    int cx = -1, cy = -1;
    uint32_t cnt = gestureCentroid(frame, prev, w, h, 18, &cx, &cy);
    CHECK(cnt == 4, "centroid: counts only pixels above the motion threshold");
    CHECK(cx == 2 && cy == 1, "centroid: centroid of the moving block");
  }

  /* ---- centroid: a still scene reports no motion ---- */
  {
    const int w = 4, h = 4;
    uint8_t prev[16] = {0}, frame[32] = {0};   /* identical frames */
    int cx = -1, cy = -1;
    CHECK(gestureCentroid(frame, prev, w, h, 18, &cx, &cy) == 0,
          "centroid: identical frames have no motion");
  }

  /* ---- state machine: three on-frames then a right wave fires '+' ---- */
  {
    gestureFsm_t g; gestureReset(&g);
    CHECK(gestureStep(&g, 1, 5, 0) == 0, "fsm: first frame does not track yet");
    CHECK(gestureStep(&g, 1, 5, 100) == 0, "fsm: second frame does not track yet");
    CHECK(gestureStep(&g, 1, 5, 200) == 0, "fsm: third frame enters tracking");
    CHECK(gestureStep(&g, 1, 20, 300) == '+', "fsm: a +15px drift is a right wave");
    CHECK(gestureStep(&g, 1, 20, 400) == 0, "fsm: no repeat while the hand stays");
    CHECK(gestureStep(&g, 0, 0, 500) == 0, "fsm: hand leaving re-arms");
  }

  /* ---- hold: hand still for the hold window cycles the view ---- */
  {
    gestureFsm_t g; gestureReset(&g);
    gestureStep(&g, 1, 5, 0); gestureStep(&g, 1, 5, 100); gestureStep(&g, 1, 5, 200);
    CHECK(gestureStep(&g, 1, 5, 300) == 0, "hold: not long enough yet");
    CHECK(gestureStep(&g, 1, 5, 200 + 1500) == 'v', "hold: held still long enough");
  }

  /* ---- cooldown: a second gesture inside the cooldown window is ignored ---- */
  {
    gestureFsm_t g; gestureReset(&g);
    gestureStep(&g, 1, 5, 0); gestureStep(&g, 1, 5, 100); gestureStep(&g, 1, 5, 200);
    CHECK(gestureStep(&g, 1, 20, 300) == '+', "cooldown: first wave fires");
    gestureStep(&g, 0, 0, 400);                    /* hand leaves */
    gestureStep(&g, 1, 5, 500); gestureStep(&g, 1, 5, 600); gestureStep(&g, 1, 5, 700);
    CHECK(gestureStep(&g, 1, 20, 800) == 0, "cooldown: second wave inside window ignored");
    CHECK(gestureStep(&g, 1, 20, 300 + 900 + 1) == '+', "cooldown: wave after window fires");
  }

  /* ---- small drift is not a wave and does not hold-cycle early ---- */
  {
    gestureFsm_t g; gestureReset(&g);
    gestureStep(&g, 1, 5, 0); gestureStep(&g, 1, 5, 100); gestureStep(&g, 1, 5, 200);
    CHECK(gestureStep(&g, 1, 7, 300) == 0, "fsm: +2px drift is neither wave nor hold");
  }

  printf("\n%s\n", failures ? "GESTURE TEST FAILED" : "gesture PASS");
  return failures ? 1 : 0;
}
