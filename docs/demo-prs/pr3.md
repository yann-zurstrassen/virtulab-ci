# PR 3: refactor(crc): start CRC-16 from zero

| | |
| :--- | :--- |
| Branch | `demo/pr3-failing-test` |
| Base | `feat/security-positioning` |
| GitHub PR | not opened: the `gh` CLI is not installed on the authoring machine (see [DECISIONS.md](../DECISIONS.md)) |
| Checked at commit | `15df7bf` |

## Title

`refactor(crc): start CRC-16 from zero`

## Description

"Simplifies" `crc16_ccitt()` by starting the register at zero instead of `0xFFFF`. That is a different algorithm (CRC-16/XMODEM), so every frame the device sends or accepts changes.

The unit tests catch it, and the engine parses each failure into file and line (table below). The same change also fails the stand-alone CRC example in `examples/crc`.

## Sticky comment (real output)

Produced locally with `make -k footprint coverage fuzz fault report BASELINE=feat/security-positioning FUZZ_SECONDS=10`.
`tools/ci_report.py` assembled it, the same script the CI `report` job runs. Machine: Apple Silicon Mac, macOS,
QEMU 11.1.1, arm-none-eabi-gcc 15.3.1, Apple clang 21. The CI workflow itself has not been run on GitHub.

````markdown
<!-- virtulab-ci-report:default -->
### 🤖 VirtuLab CI Report — `lm3s6965evb` (Cortex-M3, QEMU)

**Status:** ❌ FAILED · Emulation `0.08s`

| Metric | Current | Δ vs `a39c1bb` | Usage |
| :--- | ---: | ---: | :--- |
| **Flash** | `5,908 B` | -4 B 📉 | 2.3% of 256 KiB |
| **RAM** | `236 B` | ±0 B | 0.4% of 64 KiB (static) |
| **Unit tests** | `25 / 28` | — | ❌ 3 failed |

#### ❌ Failing tests

| Test | Location | Message |
| :--- | :--- | :--- |
| `test_crc_crc16_ccitt_matches_check_value` | `test/test_crc.c:29` | Expected 0x000029B1 Was 0x000031C3 |
| `test_parser_accepts_known_frame` | `test/test_parser.c:14` | Expected 0 Was 5 |
| `test_parser_extracts_payload_of_known_frame` | `test/test_parser.c:22` | Expected 3 Was 0 |

<details>
<summary>📊 Largest symbol size changes</summary>

| Symbol | Before | After | Δ |
| :--- | ---: | ---: | ---: |
| `__preinit_array_start` | 536,865,004 | 536,865,008 | +4 |
| `crc16_ccitt` | 50 | 48 | -2 |

</details>

<details>
<summary>🔍 Emulator output</summary>

```text
test/test_crc.c:35:test_crc_crc32_of_empty_buffer_is_zero:PASS
test/test_crc.c:36:test_crc_crc32_matches_check_value:PASS
test/test_crc.c:37:test_crc_crc32_update_matches_single_pass:PASS
test/test_crc.c:29:test_crc_crc16_ccitt_matches_check_value:FAIL: Expected 0x000029B1 Was 0x000031C3

-----------------------
4 Tests 1 Failures 0 Ignored
FAIL
test/test_parser.c:14:test_parser_accepts_known_frame:FAIL: Expected 0 Was 5
test/test_parser.c:22:test_parser_extracts_payload_of_known_frame:FAIL: Expected 3 Was 0
test/test_parser.c:105:test_parser_roundtrips_max_payload:PASS
test/test_parser.c:106:test_parser_accepts_empty_payload:PASS
test/test_parser.c:107:test_parser_rejects_bad_start_byte:PASS
test/test_parser.c:108:test_parser_rejects_corrupted_payload:PASS
test/test_parser.c:109:test_parser_rejects_truncated_frame:PASS
test/test_parser.c:110:test_parser_rejects_length_byte_far_above_maximum:PASS
test/test_parser.c:111:test_parser_clears_frame_on_error:PASS
test/test_parser.c:112:test_parser_rejects_null_arguments:PASS

-----------------------
10 Tests 2 Failures 0 Ignored
FAIL
test/test_auth.c:96:test_auth_grants_correct_pin:PASS
test/test_auth.c:97:test_auth_denies_wrong_pin:PASS
test/test_auth.c:98:test_auth_denies_pin_differing_only_in_last_byte:PASS
test/test_auth.c:99:test_auth_rejects_short_pin_without_reading_past_it:PASS
test/test_auth.c:100:test_auth_rejects_long_pin:PASS
test/test_auth.c:101:test_auth_locks_after_max_wrong_attempts:PASS
test/test_auth.c:102:test_auth_rejects_correct_pin_once_locked:PASS
test/test_auth.c:103:test_auth_success_resets_failure_counter:PASS
test/test_auth.c:104:test_auth_counts_wrong_length_towards_lockout:PASS
test/test_auth.c:105:test_auth_rejects_null_arguments:PASS
test/test_auth.c:106:test_auth_init_rejects_wrong_pin_length:PASS

-----------------------
11 Tests 0 Failures 0 Ignored
OK
test/test_sensor.c:49:test_sensor_first_sample_is_about_room_temperature:PASS
test/test_sensor.c:50:test_sensor_stays_healthy_over_repeated_samples:PASS
test/test_sensor.c:51:test_sensor_rejects_null_arguments:PASS

-----------------------
3 Tests 0 Failures 0 Ignored
OK
```
</details>

### 🛡️ Security & safety checks

| Check | Result | Details |
| :--- | :--- | :--- |
| Coverage (unit tests) | `92.4%` lines · `80.2%` branches | 145/157 lines, 69/86 branches taken at least once (gcov, native build) |
| Fuzzing (`parser`) | ✅ 0 crashes | 53,837,568 execs in 10.0s, seed 1; 0 known crash input(s) reproduced. Host-side parser fuzzing. |
| Fault injection (`auth`) | ✅ no bypass found | 56 single-instruction skips tried, first execution only |

Fidelity: see [docs/FIDELITY.md](docs/FIDELITY.md). Emulation is the fast layer; hardware-in-the-loop stays the final gate.
````

## Raw failing-test lines from the emulator

```text
test/test_crc.c:29:test_crc_crc16_ccitt_matches_check_value:FAIL: Expected 0x000029B1 Was 0x000031C3
test/test_parser.c:14:test_parser_accepts_known_frame:FAIL: Expected 0 Was 5
test/test_parser.c:22:test_parser_extracts_payload_of_known_frame:FAIL: Expected 3 Was 0
```

`Was 5` is `PARSER_ERR_BAD_CRC`. The Unity-format lines are parsed by `virtulab/parse.py`; the table in the comment is built from them.
