# PR 5: perf(auth): drop the redundant PIN comparison

| | |
| :--- | :--- |
| Branch | `demo/pr5-fault-injection` |
| Base | `feat/security-positioning` |
| GitHub PR | not opened: the `gh` CLI is not installed on the authoring machine (see [DECISIONS.md](../DECISIONS.md)) |
| Checked at commit | `f93c40b` |

## Title

`perf(auth): drop the redundant PIN comparison`

## Description

Sets `AUTH_HARDENED` to 0 in `include/auth.h`, which drops the redundant second PIN comparison "to save flash". The plain comparison is still constant-time, and all 28 unit tests pass.

Flash drops by 56 B and line coverage goes up a little, because less code is left to cover. Both look like a good change. The fault-injection job disagrees: skipping the single instruction that accumulates the first byte's mismatch (`orr.w`), or the final `cbnz` that tests the result, makes a **wrong PIN** get granted. The hardened variant (the base of this branch) survives the same sweep with no bypass.

Scope: one skipped instruction per run, first execution only, on the emulated Cortex-M3. A clean sweep is evidence, not proof; a physical glitch can do things this model does not. See [FIDELITY.md](../FIDELITY.md).

## Sticky comment (real output)

Produced locally with `make -k footprint coverage fuzz fault report BASELINE=feat/security-positioning FUZZ_SECONDS=10`.
`tools/ci_report.py` assembled it, the same script the CI `report` job runs. Machine: Apple Silicon Mac, macOS,
QEMU 11.1.1, arm-none-eabi-gcc 15.3.1, Apple clang 21. The CI workflow itself has not been run on GitHub.

````markdown
<!-- virtulab-ci-report:default -->
### 🤖 VirtuLab CI Report — `lm3s6965evb` (Cortex-M3, QEMU)

**Status:** ✅ PASSED · Emulation `0.05s`

| Metric | Current | Δ vs `a39c1bb` | Usage |
| :--- | ---: | ---: | :--- |
| **Flash** | `5,856 B` | -56 B 📉 | 2.2% of 256 KiB |
| **RAM** | `236 B` | ±0 B | 0.4% of 64 KiB (static) |
| **Unit tests** | `28 / 28` | — | ✅ 0 failed |

<details>
<summary>📊 Largest symbol size changes</summary>

| Symbol | Before | After | Δ |
| :--- | ---: | ---: | ---: |
| `__preinit_array_start` | 536,865,004 | 536,865,060 | +56 |
| `auth_verify` | 156 | 100 | -56 |

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
| Coverage (unit tests) | `93.9%` lines · `81.3%` branches | 138/147 lines, 65/80 branches taken at least once (gcov, native build) |
| Fuzzing (`parser`) | ✅ 0 crashes | 53,908,480 execs in 10.0s, seed 1; 0 known crash input(s) reproduced. Host-side parser fuzzing. |
| Fault injection (`auth`) | ❌ auth bypass reachable by single instruction skip | 2 of 36 skipped instructions grant a wrong PIN |

Fidelity: see [docs/FIDELITY.md](docs/FIDELITY.md). Emulation is the fast layer; hardware-in-the-loop stays the final gate.
````

## Same sweep, hardened variant (the base of this branch)

Real output of `make fault AUTH_HARDENED=1` on `feat/security-positioning`, for comparison:

```text
$ make fault AUTH_HARDENED=1   (sweep output only)
== Fault injection: single instruction skip ==
image: .virtulab/fault/build/firmware.elf  board: lm3s6965evb  gdb: arm-none-eabi-gdb
original run (no fault): denied
tampered     function+offset            instruction                  original  faulted
swept=78 applied=56 not_reached=22 denied=50 crashed_or_hung=6 bypass=0
VERDICT: no auth bypass found by single instruction skip (56 instructions tried, first execution only)
FAULT status=survived swept=56 bypass=0 crashed=6
real 39.68
user 32.20
sys 5.64
```

## This branch

Real output of `make fault` on this branch (`AUTH_HARDENED` is 0 in the header):

```text
== Fault injection: single instruction skip ==
image: .virtulab/fault/build/firmware.elf  board: lm3s6965evb  gdb: arm-none-eabi-gdb
original run (no fault): denied
tampered     function+offset            instruction                  original  faulted
0x000000fc   auth_verify+0x30           orr.w r4, r4, r2             denied    BYPASS (wrong PIN granted)
0x00000102   auth_verify+0x36           cbnz r4, 10a <auth_verify+0x3e> denied    BYPASS (wrong PIN granted)
swept=51 applied=36 not_reached=15 denied=31 crashed_or_hung=3 bypass=2
VERDICT: auth bypass reachable by single instruction skip
FAULT status=bypass swept=36 bypass=2 crashed=3
```

The two tampered addresses, disassembled from this branch's ELF (`arm-none-eabi-objdump -d`):

```text
000000f6 <auth_verify+0x2a>:
  f6:	ea82 0207 	eor.w	r2, r2, r7
  fa:	b2d2      	uxtb	r2, r2
  fc:	ea44 0402 	orr.w	r4, r4, r2
 100:	d1f4      	bne.n	ec <auth_verify+0x20>
 102:	b914      	cbnz	r4, 10a <auth_verify+0x3e>
 104:	7184      	strb	r4, [r0, #6]
```
