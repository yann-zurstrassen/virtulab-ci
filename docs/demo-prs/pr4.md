# PR 4: fix(parser): relax payload length check

| | |
| :--- | :--- |
| Branch | `demo/pr4-fuzz-overflow` |
| Base | `feat/security-positioning` |
| GitHub PR | not opened: the `gh` CLI is not installed on the authoring machine (see [DECISIONS.md](../DECISIONS.md)) |
| Checked at commit | `89bcf02` |

## Title

`fix(parser): relax payload length check`

## Description

Relaxes the payload length check in `parser_parse()` from `> PARSER_MAX_PAYLOAD` to `> PARSER_MAX_PAYLOAD + 1u`.

This is a deliberately seeded off-by-one for the demo. All 28 unit tests and the footprint check stay green, because none of them sends a payload length of exactly 33. A frame with length byte `0x21` copies 33 bytes into the 32-byte `payload[]`.

The fuzz job finds it. The deterministic mutation loop (seed 1) hits it after 135 executions, minimises it to 37 bytes, and the input is committed as `fuzz/crashes/parser-overflow-a525b991.crash`. From now on `make fuzz` replays every committed crash input first, so the regression cannot come back unnoticed.

Scope: this is host-side fuzzing of the parser logic, compiled natively with ASan and UBSan. It is not full-system fuzzing of the firmware image on the emulated target. The write is detected by a guard canary placed behind the frame, not by a hardware fault.

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
| **Flash** | `5,912 B` | ±0 B | 2.3% of 256 KiB |
| **RAM** | `236 B` | ±0 B | 0.4% of 64 KiB (static) |
| **Unit tests** | `28 / 28` | — | ✅ 0 failed |

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
| Fuzzing (`parser`) | ❌ 1 crash found | 0 execs in 0.0s, seed 1; 1 known crash input(s) reproduced. Host-side parser fuzzing. |
| Fault injection (`auth`) | ✅ no bypass found | 56 single-instruction skips tried, first execution only |

Fidelity: see [docs/FIDELITY.md](docs/FIDELITY.md). Emulation is the fast layer; hardware-in-the-loop stays the final gate.
````

## Discovery run

Before the crash input existed, `make fuzz` found it from scratch. Real output:

```text
$ make fuzz FUZZ_SECONDS=10   (discovery run, before the crash input was committed)
fuzz: saved fuzz/crashes/parser-overflow-a525b991.crash (37 bytes)
fuzz: CRASH: write past parser_frame_t
fuzz: input (37 bytes): A5 21 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
FUZZ execs=135 crashes=1 regressions=0 seed=1 seconds=0.0
make: *** [fuzz] Error 1

$ build/fuzz/parser_fuzz --replay fuzz/crashes/parser-overflow-a525b991.crash
fuzz: REGRESSION: fuzz/crashes/parser-overflow-a525b991.crash reproduces (write past parser_frame_t)
exit code: 1

$ xxd fuzz/crashes/parser-overflow-a525b991.crash
00000000: a521 0000 0000 0000 0000 0000 0000 0000  .!..............
00000010: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000020: 0000 0000 00                             .....
```

The committed input is 37 bytes: SOF `A5`, length `21` (33), then zeros. A 36-byte version no longer crashes, because the truncation check rejects it before the copy.
