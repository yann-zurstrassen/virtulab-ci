# 🧭 Where emulation stops and HIL starts

Test pyramid for firmware: more tests at the bottom, fewer at the top. Each layer is slower and more
realistic than the one below.

```
        ▲  realism, cost, time per run
        │
   ┌────┴────┐  HIL / bench      real silicon, real timing, real analog.   FINAL GATE
   ├─────────┤
   │  Emulation (QEMU / Renode)   same binary, virtual CPU + peripherals.   FAST LAYER, runs on every PR
   ├─────────┤
   │  Unit tests on the host      logic only, native compiler.              FASTEST
   └─────────┘
```

Emulation does not replace HIL. It moves bugs left, so the bench time goes to what only the bench can find.

## Which layer catches which bug class

✅ = a good place to catch it · 🟡 = partly, with limits · ❌ = cannot

| Bug class | Host unit test | Emulation (this repo) | HIL / bench |
| :--- | :---: | :---: | :---: |
| Algorithm and logic errors (CRC, state machines) | ✅ | ✅ | ✅ |
| Integer width, alignment, endianness on the real CPU | 🟡 (host differs) | ✅ (target instruction set) | ✅ |
| Flash/RAM budget regressions | ❌ | ✅ (footprint from the real ELF) | ✅ |
| Boot, vector table, linker-script mistakes | ❌ | ✅ | ✅ |
| Hard faults, null and wild pointers on the target | 🟡 | ✅ (fault handler reports PC) | ✅ |
| Parser memory-safety bugs from untrusted input | ✅ with fuzzing | 🟡 (fuzzing is host-side here) | ❌ impractical |
| Missing or skippable security checks (single instruction skip) | ❌ | ✅ (QEMU + GDB sweep) | 🟡 (needs glitching equipment) |
| Behaviour when a sensor misbehaves | 🟡 (mock) | ✅ (swappable model, HAL level here) | 🟡 (hard to provoke on demand) |
| Peripheral register-level driver bugs | ❌ | 🟡 (only for peripherals the emulator models correctly) | ✅ |
| Interrupt timing, race conditions that depend on cycles | ❌ | ❌ | ✅ |
| Real-time deadlines, WCET | ❌ | ❌ | ✅ |
| Flash wear, erase/program timing, power-fail | ❌ | ❌ | ✅ |
| Clock tree, low-power modes, brown-out | ❌ | ❌ | ✅ |
| Analog behaviour, noise, EMC, thermal | ❌ | ❌ | ✅ |
| Physical fault injection (voltage, clock, EM glitches) | ❌ | ❌ (software skip model only) | ✅ |
| Silicon errata | ❌ | ❌ | ✅ |

## How this repo uses each layer

| Layer | What runs | Where |
| :--- | :--- | :--- |
| Host | Coverage build (`make coverage`) and parser fuzzing (`make fuzz`) | any machine with a C compiler |
| Emulation | Unit tests, footprint (`make test`, `make footprint`), fault injection (`make fault`) | QEMU `lm3s6965evb` |
| HIL | **Not part of this repository.** Run it as the last gate before release | your bench |

For emulator limits on the one target that runs here, see [FIDELITY.md](FIDELITY.md).
