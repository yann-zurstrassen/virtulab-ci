# PR 2: feat(parser): keep an 8 KiB history of accepted payloads

| | |
| :--- | :--- |
| Branch | `demo/pr2-memory-regression` |
| Base | `feat/security-positioning` |
| GitHub PR | not opened: the `gh` CLI is not installed on the authoring machine (see [DECISIONS.md](../DECISIONS.md)) |
| Checked at commit | `b40aabb` |

## Title

`feat(parser): keep an 8 KiB history of accepted payloads`

## Description

Keeps the payload bytes of recently accepted frames in an 8 KiB ring buffer, for post-mortem debugging. All unit tests pass.

The footprint check is what catches it: RAM grows by 8,200 B, over the 2 KiB budget (`MAX_RAM_INCREASE`), and the job fails.
Fuzzing and fault injection are unaffected. The numbers in the comment below are real measurements, not estimates.

## Sticky comment (real output)

Produced locally with `make -k footprint coverage fuzz fault report BASELINE=feat/security-positioning FUZZ_SECONDS=10`.
`tools/ci_report.py` assembled it, the same script the CI `report` job runs. Machine: Apple Silicon Mac, macOS,
QEMU 11.1.1, arm-none-eabi-gcc 15.3.1, Apple clang 21. The CI workflow itself has not been run on GitHub.

````markdown
<!-- virtulab-ci-report:default -->
### 🤖 VirtuLab CI Report — `lm3s6965evb` (Cortex-M3, QEMU)

**Status:** ⚠️ MEMORY BUDGET EXCEEDED · Emulation `0.05s`

| Metric | Current | Δ vs `a39c1bb` | Usage |
| :--- | ---: | ---: | :--- |
| **Flash** | `6,160 B` | +248 B 📈 | 2.3% of 256 KiB |
| **RAM** | `8,436 B` | +8,200 B 📈 | 12.9% of 64 KiB (static) |
| **Unit tests** | `29 / 29` | — | ✅ 0 failed |

> [!WARNING]
> RAM grew by 8,200 B, above the allowed 2,048 B increase.

<details>
<summary>📊 Largest symbol size changes</summary>

| Symbol | Before | After | Δ |
| :--- | ---: | ---: | ---: |
| `parser_history` | 0 | 8,192 | +8,192 |
| `__preinit_array_start` | 536,865,004 | 536,864,756 | -248 |
| `test_parser_records_accepted_payload_in_history` | 0 | 80 | +80 |
| `parser_parse` | 114 | 164 | +50 |
| `parser_history_clear` | 0 | 32 | +32 |
| `test_parser_run` | 200 | 220 | +20 |
| `parser_history_at` | 0 | 16 | +16 |
| `parser_history_next` | 0 | 4 | +4 |

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
test/test_parser.c:111:test_parser_accepts_known_frame:PASS
test/test_parser.c:112:test_parser_extracts_payload_of_known_frame:PASS
test/test_parser.c:113:test_parser_roundtrips_max_payload:PASS
test/test_parser.c:114:test_parser_accepts_empty_payload:PASS
test/test_parser.c:115:test_parser_rejects_bad_start_byte:PASS
test/test_parser.c:116:test_parser_rejects_corrupted_payload:PASS
test/test_parser.c:117:test_parser_rejects_truncated_frame:PASS
test/test_parser.c:118:test_parser_rejects_length_byte_far_above_maximum:PASS
test/test_parser.c:119:test_parser_clears_frame_on_error:PASS
test/test_parser.c:120:test_parser_records_accepted_payload_in_history:PASS
test/test_parser.c:121:test_parser_rejects_null_arguments:PASS

-----------------------
11 Tests 0 Failures 0 Ignored
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
| Coverage (unit tests) | `92.9%` lines · `80.7%` branches | 158/170 lines, 71/88 branches taken at least once (gcov, native build) |
| Fuzzing (`parser`) | ✅ 0 crashes | 53,948,160 execs in 10.0s, seed 1; 0 known crash input(s) reproduced. Host-side parser fuzzing. |
| Fault injection (`auth`) | ✅ no bypass found | 56 single-instruction skips tried, first execution only |

Fidelity: see [docs/FIDELITY.md](docs/FIDELITY.md). Emulation is the fast layer; hardware-in-the-loop stays the final gate.
````
