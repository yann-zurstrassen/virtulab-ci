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
