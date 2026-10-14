# PR 1: feat(sensor): add Celsius to Fahrenheit conversion

| | |
| :--- | :--- |
| Branch | `demo/pr1-passing` |
| Base | `feat/security-positioning` |
| GitHub PR | not opened: the `gh` CLI is not installed on the authoring machine (see [DECISIONS.md](../DECISIONS.md)) |
| Checked at commit | `5cc85e6` |

## Title

`feat(sensor): add Celsius to Fahrenheit conversion`

## Description

Adds `sensor_deci_celsius_to_deci_fahrenheit()` with two tests (room temperature, and −40 where both scales meet).

This is the clean case: all tests pass, the footprint grows by a few hundred bytes, fuzzing and fault injection find nothing.
The table shows the real Flash/RAM delta against `feat/security-positioning`.

## Sticky comment (real output)

Produced locally with `make -k footprint coverage fuzz fault report BASELINE=feat/security-positioning FUZZ_SECONDS=10`.
`tools/ci_report.py` assembled it, the same script the CI `report` job runs. Machine: Apple Silicon Mac, macOS,
QEMU 11.1.1, arm-none-eabi-gcc 15.3.1, Apple clang 21. The CI workflow itself has not been run on GitHub.

````markdown
<!-- virtulab-ci-report:default -->
### 🤖 VirtuLab CI Report — `lm3s6965evb` (Cortex-M3, QEMU)

**Status:** ✅ PASSED · Emulation `0.08s`

| Metric | Current | Δ vs `a39c1bb` | Usage |
| :--- | ---: | ---: | :--- |
| **Flash** | `6,148 B` | +236 B 📈 | 2.3% of 256 KiB |
| **RAM** | `236 B` | ±0 B | 0.4% of 64 KiB (static) |
| **Unit tests** | `30 / 30` | — | ✅ 0 failed |

<details>
<summary>📊 Largest symbol size changes</summary>

| Symbol | Before | After | Δ |
| :--- | ---: | ---: | ---: |
| `__preinit_array_start` | 536,865,004 | 536,864,768 | -236 |
| `test_sensor_fahrenheit_matches_celsius_at_minus_forty` | 0 | 40 | +40 |
| `test_sensor_run` | 76 | 112 | +36 |
| `test_sensor_converts_room_temperature_to_fahrenheit` | 0 | 34 | +34 |
| `sensor_deci_celsius_to_deci_fahrenheit` | 0 | 18 | +18 |

</details>

<details>
<summary>🔍 Emulator output</summary>

```text
test/test_crc.c:35:test_crc_crc32_of_empty_buffer_is_zero:PASS
test/test_crc.c:36:test_crc_crc32_matches_check_value:PASS
test/test_crc.c:37:test_crc_crc32_update_matches_single_pass:PASS
test/test_crc.c:38:test_crc_crc16_ccitt_matches_check_value:PASS

-----------------------
4 Tests 0 Failures 0 Ignored
OK
test/test_parser.c:103:test_parser_accepts_known_frame:PASS
test/test_parser.c:104:test_parser_extracts_payload_of_known_frame:PASS
test/test_parser.c:105:test_parser_roundtrips_max_payload:PASS
test/test_parser.c:106:test_parser_accepts_empty_payload:PASS
test/test_parser.c:107:test_parser_rejects_bad_start_byte:PASS
test/test_parser.c:108:test_parser_rejects_corrupted_payload:PASS
test/test_parser.c:109:test_parser_rejects_truncated_frame:PASS
test/test_parser.c:110:test_parser_rejects_length_byte_far_above_maximum:PASS
test/test_parser.c:111:test_parser_clears_frame_on_error:PASS
test/test_parser.c:112:test_parser_rejects_null_arguments:PASS

-----------------------
10 Tests 0 Failures 0 Ignored
OK
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
test/test_sensor.c:59:test_sensor_first_sample_is_about_room_temperature:PASS
test/test_sensor.c:60:test_sensor_stays_healthy_over_repeated_samples:PASS
test/test_sensor.c:61:test_sensor_converts_room_temperature_to_fahrenheit:PASS
test/test_sensor.c:62:test_sensor_fahrenheit_matches_celsius_at_minus_forty:PASS
test/test_sensor.c:63:test_sensor_rejects_null_arguments:PASS

-----------------------
5 Tests 0 Failures 0 Ignored
OK
```
</details>

### 🛡️ Security & safety checks

| Check | Result | Details |
| :--- | :--- | :--- |
| Coverage (unit tests) | `92.5%` lines · `80.2%` branches | 147/159 lines, 69/86 branches taken at least once (gcov, native build) |
| Fuzzing (`parser`) | ✅ 0 crashes | 53,821,440 execs in 10.0s, seed 1; 0 known crash input(s) reproduced. Host-side parser fuzzing. |
| Fault injection (`auth`) | ✅ no bypass found | 56 single-instruction skips tried, first execution only |

Fidelity: see [docs/FIDELITY.md](docs/FIDELITY.md). Emulation is the fast layer; hardware-in-the-loop stays the final gate.
````
