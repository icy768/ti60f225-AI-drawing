"""Forward StyleCam ESP32 command logs to the existing FPGA USB console.

No FPGA daughterboard is needed for this PC-assisted control-only bring-up.
Run --self-test without opening any ports. Normal use requires two explicit ports.
"""
from pathlib import Path
import argparse
import re
import sys
import threading

COMMAND = re.compile(rb"\[cmd\] -> FPGA console: '([012vs])'\r?\n?\Z")


def command_from_line(line):
    match = COMMAND.fullmatch(line)
    return match.group(1) if match else None


def self_test():
    for command in b"012vs":
        assert command_from_line(b"[cmd] -> FPGA console: '" + bytes([command]) + b"'\r\n") == bytes([command])
    for line in (b"[voice] unmatched: A1 00 01 01 FF\n", b"[cmd] -> FPGA console: 'w'\n",
                 b"junk [cmd] -> FPGA console: '0'\n", b"[cmd] -> FPGA console: '0' trailing\n",
                 b"[cmd] -> FPGA console: '01'\n", b"[cmd] -> FPGA console: '\x00'\n"):
        assert command_from_line(line) is None
    print('PASS: five allowed commands; unrelated, unsafe and malformed logs rejected. No ports opened.')


def open_port(serial, name):
    port = serial.Serial(port=None, baudrate=115200, timeout=0.2, write_timeout=1)
    port.dtr = False
    port.rts = False
    port.port = name
    port.open()
    return port


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--esp-port', help='ESP32 USB log port, e.g. COM20')
    parser.add_argument('--fpga-port', help='Existing FPGA USB console port, e.g. COM19')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.esp_port or not args.fpga_port:
        parser.error('Specify --esp-port and --fpga-port; --self-test opens no ports.')
    if args.esp_port.upper() == args.fpga_port.upper():
        parser.error('ESP32 and FPGA ports must differ.')
    for wheel in Path(__file__).parent.glob('pyserial-*.whl'):
        sys.path.insert(0, str(wheel))
    try:
        import serial
    except ImportError:
        parser.error('Install pyserial 3.5 or place its wheel next to this script.')
    stop = threading.Event()
    with open_port(serial, args.fpga_port) as fpga, open_port(serial, args.esp_port) as esp:
        def read_fpga():
            try:
                while not stop.is_set():
                    data = fpga.read(1024)
                    if data:
                        sys.stdout.write('[FPGA] ' + data.decode('utf8', errors='replace'))
                        sys.stdout.flush()
            except serial.SerialException as error:
                print('\nFPGA serial error:', error, file=sys.stderr)
                stop.set()
        thread = threading.Thread(target=read_fpga, daemon=True)
        thread.start()
        print(f'ESP32 {args.esp_port} -> FPGA {args.fpga_port}, 115200 8N1. Ctrl+C stops.')
        pending = bytearray()
        try:
            while not stop.is_set():
                data = esp.read(1024)
                if not data:
                    continue
                pending.extend(data)
                while b'\n' in pending:
                    line, _, pending = pending.partition(b'\n')
                    line += b'\n'
                    print('[ESP] ' + line.decode('utf8', errors='replace').rstrip())
                    command = command_from_line(line)
                    if command:
                        fpga.write(command)
                        fpga.flush()
                        print('[bridge] sent ' + command.decode('ascii'))
                if len(pending) > 2048:
                    # Discard an overlong line entirely, including its remainder.
                    while b'\n' not in pending and not stop.is_set():
                        pending = bytearray(esp.read(1024))
                    pending = bytearray(pending.partition(b'\n')[2])
        except KeyboardInterrupt:
            pass
        finally:
            stop.set()
            thread.join(timeout=1)


if __name__ == '__main__':
    main()
