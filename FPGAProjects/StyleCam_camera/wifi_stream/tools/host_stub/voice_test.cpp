/*
 * voice_test.cpp - host self-test for the VC-02 frame matching in the sketch.
 *
 * It compiles the real esp32s3_stream.ino into this translation unit and calls the
 * matching helpers directly, so the rule syntax and the burst rules are exercised as
 * shipped rather than re-implemented here.  A wrong table edit or a broken wildcard
 * fails this test instead of failing silently on the demo table.
 *
 * Build and run through tools/check_host.sh.
 */
#include "Arduino.h"

/* Pull in the sketch itself; setup()/loop() come along but stay unused. */
#include "../../esp32s3_stream/esp32s3_stream.ino"

static int failures = 0;

#define CHECK(cond, what)                        \
  do {                                           \
    if (cond) { printf("  ok    %s\n", what); }  \
    else      { printf("  FAIL  %s\n", what); failures++; } \
  } while (0)

/* An independent table so wildcards and short frames are covered; the shipped
 * VOICE_RULES is checked separately below. */
static const voiceRule_t testRules[] = {
  { "A1 00 01 01 FF", '0' },
  { "A1 ?? 02 ?? FF", '1' },   /* two wildcards */
  { "5A",            's' },    /* a one-byte module */
};
#define TEST_RULE_COUNT (sizeof(testRules) / sizeof(testRules[0]))

int main() {
  uint16_t pat[VOICE_BURST_MAX];
  char txt[4 * VOICE_BURST_MAX];

  printf("\nvoice frame matching\n");

  /* ---- rendering: the log line is meant to be pasted straight into config.h ---- */
  {
    const uint8_t b[] = {0xA1, 0x00, 0x01, 0x01, 0xFF};
    fmtBurst(txt, sizeof(txt), b, 5);
    CHECK(strcmp(txt, "A1 00 01 01 FF") == 0, "fmtBurst renders a pastable hex string");
  }
  {
    const uint8_t b[] = {0x0A};
    fmtBurst(txt, sizeof(txt), b, 1);
    CHECK(strcmp(txt, "0A") == 0, "fmtBurst zero-pads single digits");
  }

  /* ---- pattern syntax ---- */
  CHECK(patParse("A1 00 01 01 FF", pat) == 5 && pat[0] == 0xA1 && pat[4] == 0xFF,
        "pattern: five explicit bytes");
  CHECK(patParse("A1 00 ?? FF", pat) == 4 && pat[2] == 0x100 && pat[3] == 0xFF,
        "pattern: ?? is exactly one wildcard byte");
  CHECK(patParse(" a1 00 ff ", pat) == 3 && pat[0] == 0xA1 && pat[2] == 0xFF,
        "pattern: lowercase and stray spaces accepted");
  CHECK(patParse("A1 ZZ FF", pat) == 0, "pattern: non-hex rejected");
  CHECK(patParse("A1 0? FF", pat) == 0, "pattern: half a wildcard rejected");
  CHECK(patParse("", pat) == 0, "pattern: empty rejected");

  /* ---- matching ---- */
  {
    const uint8_t b[] = {0xA1, 0x00, 0x01, 0x01, 0xFF};
    CHECK(ruleMatchIn(testRules, TEST_RULE_COUNT, b, 5) == '0', "match: exact hit");
  }
  {
    const uint8_t b[] = {0xA1, 0x7F, 0x02, 0x00, 0xFF};
    CHECK(ruleMatchIn(testRules, TEST_RULE_COUNT, b, 5) == '1', "match: wildcards accept any byte");
  }
  {
    const uint8_t b[] = {0xA1, 0x00, 0x01, 0x02, 0xFF};
    CHECK(ruleMatchIn(testRules, TEST_RULE_COUNT, b, 5) == 0, "match: one wrong byte is a miss");
  }
  {
    const uint8_t b[] = {0xA1, 0x00, 0x01, 0x01};
    CHECK(ruleMatchIn(testRules, TEST_RULE_COUNT, b, 4) == 0,
          "match: a truncated frame is a miss, not a partial hit");
  }
  {
    const uint8_t b[] = {0xE7, 0xA1, 0x00, 0x01, 0x01, 0xFF};
    CHECK(ruleMatchIn(testRules, TEST_RULE_COUNT, b, 6) == 0,
          "match: leading junk is a miss, not a shifted hit");
  }
  {
    const uint8_t b[] = {0x5A};
    CHECK(ruleMatchIn(testRules, TEST_RULE_COUNT, b, 1) == 's', "match: one-byte modules work");
  }
  {
    /* Every shipped rule must be reachable, so a typo in the table is caught here
     * rather than during the demo.  Wildcards round-trip as an all-zero byte. */
    int live = 0;
    for (unsigned r = 0; r < VOICE_RULE_COUNT; r++) {
      uint16_t p[VOICE_BURST_MAX];
      uint8_t b[VOICE_BURST_MAX];
      int pn = patParse(VOICE_RULES[r].pat, p);
      bool ok = false;
      if (pn > 0) {
        for (int i = 0; i < pn; i++) b[i] = (p[i] == 0x100) ? 0x00 : (uint8_t)p[i];
        ok = ruleMatch(b, pn) == VOICE_RULES[r].cmd;
      }
      if (ok) live++;
      else printf("  FAIL  shipped rule %u (%s) is unreachable\n", r, VOICE_RULES[r].pat);
    }
    CHECK(live == (int)VOICE_RULE_COUNT, "shipped VOICE_RULES are all well formed and reachable");
  }

  /* ---- burst delimiting ---- */
  CHECK(!burstDone(0, 1000, 1000), "burst: nothing buffered is not a frame");
  CHECK(!burstDone(3, 1010, 1000), "burst: a short gap keeps the frame open");
  CHECK(burstDone(3, 1000 + VOICE_GAP_MS, 1000), "burst: the silent gap closes the frame");
  CHECK(burstDone(VOICE_BURST_MAX, 1000, 1000), "burst: a full buffer closes the frame");

  printf("\n%s\n", failures ? "VOICE TEST FAILED" : "voice frame matching PASS");
  return failures ? 1 : 0;
}
