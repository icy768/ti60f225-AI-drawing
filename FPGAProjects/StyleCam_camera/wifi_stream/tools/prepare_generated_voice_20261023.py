"""Review and package downloaded VC-02 artifacts; never access hardware."""
import hashlib
import json
import re
import shutil
import tarfile
from pathlib import Path

BASE = Path(__file__).resolve().parents[3] / "tools/vc02/stylecam_sdk_20261023001"
SDK = BASE / "uni_hb_m_solution/unione_lite_app_hb_m"
PACKAGE = Path(__file__).resolve().parents[3] / "烧录文件/20261021_ESP32_VC02_J7_Integration"
EXPECTED = [
    ("Style0", "切换梵高", "一", "A1 00 01 01 FF", "0"),
    ("Style1", "切换浮世绘", "二", "A1 00 02 01 FF", "1"),
    ("Style2", "切换水墨", "三", "A1 00 03 01 FF", "2"),
    ("ViewNext", "切换画面", "四", "A1 00 04 01 FF", "v"),
]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


config_path = SDK / "tools/scripts/custom_config.json"
config = json.loads(config_path.read_text("utf-8"))
replies = json.loads((SDK / "tools/scripts/cmd_reply_data.json").read_text("utf-8"))
assert config["version"] == "20261023001"
assert config["appType"] == "hb_m-offline-thirdparty"
assert config["local"]["wakeup"]["keyword"] == ["小安小安"]
assert config["local"]["wakeup_command"] == []
assert config["local"]["cmd"] == {"sensitivity": "middle", "selfstudy": "disable"}
assert config["local"]["micarray"] == {
    "field": "far", "aec": "disable", "number": "1", "ssnr": "disable"
}
pins = {str(p["pin"]): p for p in config["local"]["pin_config"]}
assert pins["7"]["function"] == "UART1_RX"
assert pins["8"]["function"] == "UART1_TX"
assert pins["8"]["params"] == {
    "baud_rate": 115200, "parity_bits": "none", "stop_bits": 1, "data_bits": 8
}
assert pins["6"]["function"] == "GPIO_A28" and pins["6"]["params"]["def_voltage"] == "low"
assert pins["1"]["function"] == "SW_CLK" and pins["2"]["function"] == "SW_D"
assert pins["21"]["function"] == "GPIO_B2" and pins["22"]["function"] == "GPIO_B3"
actions = {a["action"]: a["ctrl_items"] for a in config["local"]["action_config"]}
assert set(actions) == {e[0] for e in EXPECTED}
auto = (SDK / "user/src/examples/hb_auto_gpio.c").read_text("utf-8")
header = (SDK / "user/inc/user_config.h").read_text("utf-8")
nlu = (SDK / "include/uni_nlu_content.h").read_text("utf-8")
for key, value in [
    ("USE_UNIONE_PROTOCOL", "0"), ("USE_SAMPLE_PROTOCOL", "0"),
    ("USER_UART_DEVICE_NUM", "1"), ("USER_UART_PIN_SELECT", "0"),
    ("USER_UART_BAUD_RATE", "115200"), ("USER_UART_PARITY", "0"),
    ("USER_UART_STOP_BIT", "1"), ("USER_UART_DATA_BIT", "8"),
    ("USER_RUN_DEMO", "1"), ("USER_RUN_DEMO_SELECT", "USER_DEMO_AUTO_GPIO")
]:
    assert re.search(r"^\s*#define\s+" + key + r"\s+" + value + r"\s", header, re.M), key
assert "user_gpio_set_value(GPIO_NUM_A28, 0);" in auto
commands = []
for i, (action, word, reply, frame, char) in enumerate(EXPECTED):
    controls = actions[action]
    assert len(controls) == 1
    assert controls[0]["function"] == "UART1_TX" and controls[0]["command"] == "send"
    assert controls[0]["params"]["data"] == frame
    matching = [r for r in replies if r["cmd"] == action]
    assert len(matching) == 1 and matching[0]["cmd_word"] == [word] and matching[0]["reply"] == [reply]
    assert word in nlu
    assert "{{" + ", ".join("0x" + x for x in frame.split()) + "}, 5}, //" + action in auto
    pattern = (r'uni_strcmp\(setting->cmd, "' + action + r'"\)\) \{\s*'
               r'user_uart_send\(g_uart_buf\[' + str(i) + r'\]\.data, '
               r'g_uart_buf\[' + str(i) + r'\]\.len\);')
    assert re.search(pattern, auto), action
    commands.append(dict(action=action, word=word, reply=reply, uart_hex=frame, fpga_character=char))

with tarfile.open(BASE / "archives/output.tar.gz", "r:gz") as archive:
    firmware = archive.extractfile("./output/uni_app_release_update.bin").read()
sdk_image = (BASE / "uni_hb_m_solution/image_demo/Hummingbird-M-Update-Tool/uni_app_release_update.bin").read_bytes()
assert len(firmware) == len(sdk_image) == 1217688
# These two downloads were built separately. Require that their sole difference
# is the ASCII compile timestamp, rather than accepting arbitrary binary changes.
stamp_pattern = rb"2026-10-23 \d{2}:\d{2}:\d{2}"
stamp = re.search(stamp_pattern, firmware)
assert stamp is not None
start, end = stamp.span()
assert re.fullmatch(stamp_pattern, sdk_image[start:end])
assert firmware[:start] == sdk_image[:start] and firmware[end:] == sdk_image[end:]
vendor = (BASE.parent / "serial-update-tool/Hummingbird-M-Update-Tool/uni_app_release_update.bin").read_bytes()
assert firmware != vendor
frame_offsets = {e[0]: firmware.find(bytes.fromhex(e[3])) for e in EXPECTED}
frame_counts = {e[0]: firmware.count(bytes.fromhex(e[3])) for e in EXPECTED}
assert all(c == 1 for c in frame_counts.values())
word_offsets = {word: firmware.find(word.encode("utf-8")) for word in ["小安小安"] + [e[1] for e in EXPECTED]}
assert all(offset >= 0 for offset in word_offsets.values())
# Verify the actual firmware's compiled NLU JSON links each word to its action.
for action, word, _, _, _ in EXPECTED:
    assert ('{"asr":"' + word + '","cmd":"' + action + '"').encode("utf-8") in firmware
assert '{"asr":"小安小安","cmd":"wakeup_uni"'.encode("utf-8") in firmware

voice = PACKAGE / "voice"
evidence = voice / "sdk_evidence_20261023001"
evidence.mkdir(parents=True, exist_ok=True)
target = voice / "uni_app_release_update.bin"
if target.exists():
    assert target.read_bytes() == firmware, "Existing package firmware differs"
else:
    target.write_bytes(firmware)
source_evidence = []
for rel in [
    "tools/scripts/cmd_reply_data.json", "user/inc/user_config.h",
    "user/src/examples/hb_auto_gpio.c", "include/uni_nlu_content.h", "include/uni_cust_config.h"
]:
    src = SDK / rel
    out = evidence / src.name
    shutil.copyfile(src, out)
    source_evidence.append({
        "sdk_path": rel, "source_sha256": digest(src.read_bytes()),
        "packaged_path": out.relative_to(PACKAGE).as_posix(),
        "packaged_sha256": digest(out.read_bytes()),
    })
safe_config = {k: v for k, v in config.items() if k not in ["appKey", "appSecret"]}
write_json(evidence / "custom_config.redacted.json", safe_config)
record = {
    "verified_date": "2026-10-23", "platform_version": "20261023001", "sdk_build_id": "279107",
    "offline_app_type": config["appType"],
    "source_archives": [{"path": str(p), "bytes": p.stat().st_size, "sha256": digest(p.read_bytes())}
                        for p in [BASE / "archives/output.tar.gz", BASE / "archives/uni_hb_m_solution-279107-20261023.tar.gz"]],
    "sdk_root": str(SDK), "wake_word": "小安小安", "wake_replies": config["local"]["wakeup"]["reply"],
    "custom_command_count": 4, "commands": commands,
    "uart": {"port": 1, "baud": 115200, "data_bits": 8, "stop_bits": 1, "parity": "none",
             "rx_platform_pin": 7, "rx_gpio": "B6", "tx_platform_pin": 8, "tx_gpio": "B7"},
    "checks": {
        "generated_source_and_config_match": True, "single_raw_uart_send_per_custom_action": True,
        "unione_and_sample_protocol_disabled": True, "a28_output_low": True,
        "sw_programming_pins_preserved": True, "wake_action_has_no_uart_output": True,
        "wake_free_commands_empty": True, "firmware_matches_sdk_except_compile_timestamp": True,
        "firmware_differs_from_vendor_stock_image": True, "firmware_has_all_four_raw_frame_sequences": True,
        "firmware_compiled_nlu_words_and_actions_match": True,
    },
    "binary_comparison": {"exact_sha_match": firmware == sdk_image,
                          "sdk_update_sha256": digest(sdk_image), "excluded_region": [start, end],
                          "firmware_build_stamp": firmware[start:end].decode("ascii"),
                          "sdk_build_stamp": sdk_image[start:end].decode("ascii"),
                          "all_other_bytes_equal": True},
    "frame_byte_offsets": frame_offsets, "frame_byte_occurrences": frame_counts,
    "compiled_nlu_word_offsets": word_offsets,
    "update_firmware": {"path": "voice/uni_app_release_update.bin", "bytes": len(firmware), "sha256": digest(firmware)},
    "source_evidence": source_evidence, "custom_config_original_sha256": digest(config_path.read_bytes()),
    "hardware_programmed_this_run": False, "voice_recognition_runtime_verified": False,
    "uart_output_runtime_verified": False,
    "scope": "Static review of downloaded platform configuration, generated C code, compiled NLU, and binary comparison. On-device speech/UART acceptance remains pending.",
}
write_json(voice / "generated_sdk_verification_20261023.json", record)
print(json.dumps({"passed": True, "version": record["platform_version"], "wake_word": record["wake_word"],
                  "wake_replies": record["wake_replies"], "commands": commands,
                  "firmware_bytes": len(firmware), "firmware_sha256": digest(firmware),
                  "binary_comparison": record["binary_comparison"]}, ensure_ascii=False, indent=2))
