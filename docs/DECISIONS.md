# Decisions, assumptions and gaps

Everything below was decided without asking, picking the most conservative option.
Sections are appended as the work progresses.

## Recon (what existed before this branch)

Measured on the starting commit `95c6ad3` (branch `mvp`), machine: Apple M-series, macOS (Darwin 25.6.0 arm64),
Python 3.14.7, arm-none-eabi-gcc 15.3.1, QEMU 11.1.1. Raw output: [`baseline-run.txt`](baseline-run.txt).

- The repo is a **Python engine** (`virtulab/`) plus a bundled bare-metal runtime (`virtulab/runtime/`:
  startup, linker script template, Unity-compatible test framework, semihosting exit). There was **no Makefile**.
- Firmware lives only in `examples/crc` (CRC-32 / CRC-16, 4 tests) and `examples/thermostat` (STM32F4 + I2C sensor, Renode).
- Baseline that built and passed: `python3 -m virtulab run -C examples/crc -b lm3s6965evb ...` → 4/4 tests, Flash 1,904 B, RAM 188 B.
- `.github/workflows/firmware-ci.yml` ran three jobs (engine unit tests, `examples/crc` on QEMU, `examples/thermostat` on Renode) via a Docker image.
- The README claimed "Vercel for Firmware" and mentioned replacing the bench; no timing claims were backed by a measurement.

### Mismatches between the task text and the repo

| Task assumption | Reality | What I did |
| :--- | :--- | :--- |
| Existing Makefile, `make test` | None | Added a top-level `Makefile`; `make test` drives the existing engine on QEMU |
| Existing flash driver | Does not exist | Not invented. The CRC module is kept as is (`examples/crc`) and reused |
| Throw-the-Switch Unity | Not vendored; the repo ships a Unity-compatible `virtulab_test.h` | Tests use that header (same macros and output format). Real Unity was not added, to keep the checkout offline-buildable |
| `src/` + `test/` at the repo root | Only under `examples/` | New demo firmware at the root (`src/`, `test/`, `include/`); `examples/` untouched |
| CRC naming with the module prefix | Existing API is `crc32()`, `crc16_ccitt()` | Kept as is ("keep the existing CRC code") |

### Working tree

`ROADMAP.md` had uncommitted edits by the repo owner when I started. They are left uncommitted and untouched on every branch.

## Branches and where things live

- Everything is on `feat/security-positioning`, branched from `mvp` (the checked-out branch), **not** from `main`. `main` was not touched.
- Demo branches `demo/pr1-passing` … `demo/pr5-fault-injection` are each one code commit (PR 4: two) plus its `docs/demo-prs/prN.md`, off the base commit `a39c1bb`. The base later gained docs-only commits; the compiled firmware is unchanged by them.
- **The fuzz harness (`fuzz/parser_fuzz.c`) and `tools/fault_inject.sh` are in the base branch, not only on `demo/pr4` / `demo/pr5`.** Reason: the task needs the CI `fuzz` and `fault-injection` jobs and a working `make fuzz` / `make fault` from a clean checkout. PR 4 therefore contributes the seeded bug and the crash input, PR 5 flips `AUTH_HARDENED` in `include/auth.h` to 0.
- **The hardened PIN comparison is the default in the base** (`AUTH_HARDENED 1`), as requested ("hardened variant on the main demo branch").

## Not done: skipped, planned or mocked

| Item | Status | Why |
| :--- | :--- | :--- |
| Opening the five PRs on GitHub | 🚧 skipped | `gh` is not installed. PR text and real sticky comments are in `docs/demo-prs/` |
| Running the CI workflow | 🚧 not executed | Cannot run GitHub Actions locally. Validated only with Ruby's YAML parser (`actionlint` and PyYAML are not installed). apt package names for Ubuntu (`gdb-multiarch`, `binutils-arm-none-eabi`) and Linux gcc/gcov behaviour (coverage awk, ASan) are untested |
| AFL++ / libFuzzer | 🚧 PLANNED | Not installed. Replaced by a deterministic mutation loop written in C, as the task allows |
| Full-system fuzzing | 🚧 PLANNED | Fuzzing is **host-side**, of the parser logic only, and is documented that way |
| MC/DC | 🚧 not measured | Only gcov line and branch coverage. Branch counts are gcov's, at `-O0`, and include compiler-generated branches |
| Renode / `examples/thermostat` | 🚧 not run | Renode is not installed. All Renode statements in `docs/ENGINE.md` are carried over, unverified |
| FIDELITY table for other boards | 🚧 not assessed | Only `lm3s6965evb` was inspected (QEMU's own device dump). The other QEMU boards were only exercised through the engine's CRC e2e test |
| Sensor models (`sensor_nominal`, `sensor_faulty`) | 🧪 MOCKED | Software HAL models, swapped at link time. Not QEMU devices, not the same ELF. QEMU cannot attach devices to `lm3s6965evb` from the command line the engine uses |
| Fault injection beyond single skip | 🚧 PLANNED | No bit flips, multi-fault, or repeated-execution (loop iteration) skips. Each instruction is skipped on its **first** execution only. The probe's wrong PIN differs in byte 0, the worst case for that |
| Flash driver | not present | The task says "keep the existing flash driver"; the repo never had one, so none was invented |
| Real Unity | not vendored | The repo's Unity-compatible `virtulab_test.h` is used (same macros and output format) |

## Assumptions and judgment calls

- **Footprint is measured on the test image**, as the existing engine does (tests are linked in). The baseline is built from the PR's base ref with the same source globs. When the base ref lacks those files (for example `main`), the engine reports "no footprint delta".
- **Budgets:** `MAX_FLASH_INCREASE ?= 4K` (the old workflow's value) and `MAX_RAM_INCREASE ?= 2K` (my choice) in the `Makefile`.
- **Fuzz time:** 10 s by default locally, 60 s in CI. Seed 1. The loop is deterministic for a fixed seed up to the time cut-off.
- **Parser design:** the parser copies the payload before the CRC check and zeroes the frame on any error. That ordering is what makes the seeded off-by-one reachable without a valid CRC. It is a legitimate pattern, but I chose it partly for the demo.
- **Seeded bug detection:** the write overflow is caught by a guard canary behind the frame (plus ASan/UBSan for other memory errors), not by a hardware fault. A 1-byte over-read is not reliably caught.
- **Unit tests deliberately do not test a payload length of exactly 33.** That is why PR 4's unit tests stay green. A fix for PR 4 should add that regression test.
- **Fault classification:** `BYPASS` = the probe test fails with "auth bypass". `denied` = probe passes. `crashed_or_hung` = no PASS/FAIL line (HardFault, infinite loop, 10 s timeout). `not_reached` = the breakpoint never fired. Crashes and hangs are reported but are neither counted as bypass nor as safe.
- **Hardening claim:** the hardened build had 0 bypasses over 56 applied skips (78 instructions located, 22 never reached). The plain build had 2 bypasses over 36 applied skips. Both sweeps gave identical per-instruction results across repeated runs (3 runs of the plain build, 2 of the hardened build). A clean sweep is evidence, not proof.
- **ROI inputs** in the README are illustrative. `tools/roi.py` only does arithmetic.
- **Timing claims:** only the four measured wall times in the README (one run each, Apple M4 Pro, clean clone, `docs/runs/`). "less than 5 seconds" and every other earlier timing claim was removed.
- **Sticky comments in `docs/demo-prs/` are assembled by `tools/ci_report.py` from local runs** (`make -k footprint coverage fuzz fault report`). They were not posted by CI. `BASELINE=feat/security-positioning` was passed explicitly; locally the default `main` has no `src/`.
- The five PR checks were run in parallel git worktrees to save time. That affects `execs` counts (fuzz throughput), not results.
- **Old README:** the "Vercel for Firmware" tagline, "replaces the bench" phrasing and the "more accurate than the emulators" line were removed. The previous engine reference moved to `docs/ENGINE.md` unchanged apart from relative links.
- `README.md` on `main` still contains the garbled `google.com/search?q=` link wrappers; the `mvp` README this work started from already had plain URLs, and the new README has none. `main` was left alone.
- `ROADMAP.md` (owner's uncommitted edits) was left uncommitted on every branch.
- Commits carry a `Co-Authored-By` trailer as requested by the session instructions.

## Bugs I found in my own tooling while verifying

Recorded because they would have produced wrong results silently.

1. **GNU make 3.81 (macOS) ignores `.SHELLFLAGS`.** `-o pipefail` was never applied, so `make fuzz | tee` exited 0 on a crash. Fixed with a per-recipe `STRICT` prefix.
2. **`AUTH_HARDENED` was defined twice** (Makefile default `1` overrode the header), so PR 5's one-line change did nothing. The header is now the single default.
3. **The fault sweep was non-deterministic:** a fixed `sleep` before GDB connected, QEMU killed before its stdout was flushed, and a breakpoint `commands { continue }` block that let GDB end the batch early. Fixed (retry on refused connection, wait for QEMU to exit, straight-line GDB script). Results were stable over repeated runs afterwards. The first, flaky numbers were discarded.
4. All five `docs/demo-prs/prN.md` files were regenerated from fresh runs after items 1 to 3, in clean worktrees on the final base, so every recorded sha and number matches it.

## Pre-existing engine quirk, not fixed

The "Largest symbol size changes" table can list `__preinit_array_start` with a huge "before/after" size (for example 536,865,004). It comes from `nm --print-size` output in `virtulab/build.py::symbol_sizes`. It is visible in the PR 2 comment. It does not affect the Flash/RAM totals, which come from `arm-none-eabi-size`.

## Product direction (2026-10-30)

- **Evidence files** come from every project run. They record facts and limits, and make no compliance claim. No standard was mapped row by row, because the standards' text was not read.
- **`build.command`** runs through a shell from `virtulab.yml`, which is the project's own file, like a Makefile. Coverage is skipped in that mode.
- **libFuzzer** is used when a real clang can link it. Apple's clang cannot, so the probe compiles a small harness rather than trusting the flag. The Docker image grew to 2.15 GB for it.
- **Third-party code** was run with the owner's approval, in a network-isolated container. Details stay in the git-ignored `.private/` folder until the maintainers have them.

- **Fault sweep ports:** each run now asks the operating system for a free port instead of picking one at random. Before that, about 1 in 3 to 6 Docker suite runs took 680 s and failed. Seven full runs since took about 175 s with no stall. That points to the fix, but the original cause was never confirmed.
- **Rejected for the sweep:** a gdb pipe, because QEMU writes firmware output to the same stdout, and Unix sockets, which this macOS gdb does not support.
- **`examples/secure-boot`** is a CMake project with no VirtuLab code. Building it exposed that the sweep discarded firmware output on stderr, which is where `SYS_WRITE0` output lands, and that the image lacked `make`.

## Peripherals and sensor input (2026-10-31)

- **Why now:** the owner said this is very important, because it lets test benches drop analog rigs for scenarios like a temperature environment.
- **Own ADC model rather than Renode's:** Renode's `STM32_ADC` queues samples through `FeedSample`. A bench source holds a voltage, so a small generated model does that. Register offsets and bits come from ST's STM32F40x SVD file.
- **Time zero** values are monitor commands, so they apply before the firmware starts. Later values apply on a 1 ms virtual tick, so finer timing than 1 ms is rounded up.
- **Failed model compilation** is now reported at once, not after the timeout.

## Review fixes (2026-10-30)

- **Checks fail closed.** A fault sweep that applied no fault is `inconclusive` and fails. Zero tests fails. A budget that cannot be compared fails, except when there is no ref, or the baseline lacks these sources because the code is new.
- **One check path.** `make` and CI run `virtulab.yml` through `suite.py`. `tools/ci_report.py`, `tools/gcov_summary.awk` and `tools/fault_inject.sh` were removed, and the numbers in `docs/demo-prs/`, `docs/runs/` and the README's recorded runs predate this.
- **PR code never sits next to a write token.** Checks run in a read-only job. A second job holds the token, never checks out the PR and posts the report with `gh`. The PR-built image is not used there, because a PR can edit the `Dockerfile`.
- **The baseline fetch no longer uses `--depth` on a full clone.** It truncated local history to one commit.
- **Hardened `auth.c` charges the attempt before comparing,** over two routes to the counter, and checks the lockout twice. Three probes state one property each. The result is for `-Os`-style builds of these two configurations: at `-O0` the first sweep found bypasses, so other flags need their own sweep.
- **Datasheet citations:** each row was applied only if a text snippet was found on the cited page. Weak snippets for the AT and NMEA rows were then read by hand. A match shows the page supports the row; it was not a line-by-line audit of every number.
