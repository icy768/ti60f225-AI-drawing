"""Listen for the four StyleCam VC-02 command frames; never transmit or reset."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

PROJECT = Path(__file__).resolve().parents[3]
WHEEL = PROJECT / "烧录文件/20261020_ESP32S3_VC02_Prepare/pyserial-3.5-py2.py3-none-any.whl"
if WHEEL.is_file():
    sys.path.insert(0, str(WHEEL))
import serial
from serial.tools import list_ports

EXPECTED = {
    bytes.fromhex("A1 00 01 01 FF"): ("Style0", "切换梵高"),
    bytes.fromhex("A1 00 02 01 FF"): ("Style1", "切换浮世绘"),
    bytes.fromhex("A1 00 03 01 FF"): ("Style2", "切换水墨"),
    bytes.fromhex("A1 00 04 01 FF"): ("ViewNext", "切换画面"),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--seconds", type=float, default=120)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    ports = [p for p in list_ports.comports() if p.device.upper() == args.port.upper()]
    if len(ports) != 1 or (ports[0].vid, ports[0].pid) != (0x1A86, 0x7523):
        parser.error("Expected the user-identified VC-02 CH340 port (VID_1A86/PID_7523).")
    if not 1 <= args.seconds <= 300:
        parser.error("Capture duration must be between 1 and 300 seconds.")
    args.output.mkdir(parents=True, exist_ok=True)
    counts = {frame: 0 for frame in EXPECTED}
    stream = bytearray()
    pending = bytearray()
    events = []
    started = datetime.now(timezone.utc).isoformat()
    port = serial.Serial(port=None, baudrate=115200, timeout=0.2)
    port.dtr = False
    port.rts = False
    port.port = ports[0].device
    try:
        port.open()
        print(f"ARMED: {port.port}, 115200 8N1, receive only. Say 小安小安, then each of the four commands.", flush=True)
        deadline = time.monotonic() + args.seconds
        next_status = time.monotonic() + 15
        while time.monotonic() < deadline and not all(counts.values()):
            data = port.read(max(1, min(port.in_waiting, 4096)))
            if data:
                stream.extend(data)
                pending.extend(data)
                print("RX: " + data.hex(" ").upper(), flush=True)
                while len(pending) >= 5:
                    candidate = bytes(pending[:5])
                    if candidate in EXPECTED:
                        counts[candidate] += 1
                        action, word = EXPECTED[candidate]
                        events.append({"time_utc": datetime.now(timezone.utc).isoformat(),
                                       "action": action, "word": word,
                                       "hex": candidate.hex(" ").upper()})
                        print(f"MATCH: {action} {word} => {candidate.hex(' ').upper()}", flush=True)
                        del pending[:5]
                    else:
                        del pending[0]
            if time.monotonic() >= next_status:
                print("WAITING: " + ", ".join(EXPECTED[k][1] for k, v in counts.items() if not v), flush=True)
                next_status = time.monotonic() + 15
    finally:
        port.close()
        (args.output / "received.bin").write_bytes(stream)
        result = {
            "started_utc": started,
            "port": args.port, "baud": 115200, "bytes_received": len(stream),
            "frames": [{"action": EXPECTED[k][0], "word": EXPECTED[k][1],
                        "hex": k.hex(" ").upper(), "count": v} for k, v in counts.items()],
            "events": events, "all_four_raw_frames_observed": all(counts.values()),
            "transmitted_bytes": 0, "reset_requested": False,
            "firmware_flash_readback_performed": False,
        }
        (args.output / "uart_capture.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if all(counts.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
