# VirtuLab: pitch draft (for refining)

---

## The one-liner

**Security and safety evidence for your firmware on every pull request, without waiting for the bench.**

VirtuLab runs your firmware on a virtual board on every change. It then adds the checks that are too slow to repeat on real hardware: fuzzing, fault injection, coverage and memory budgets. Results land in one comment on the pull request. Hardware-in-the-loop (HIL) testing stays the final gate.

---

## Where we sit, and what is different

Running chip designs and firmware without hardware is an old idea, and its history shapes this pitch. There have been three waves:

| Wave | What it did | Who paid | How it ended |
| :-- | :-- | :-- | :-- |
| **Chip emulation** | Run a chip design before it is manufactured | Chip companies, six or seven figures, because a respin costs millions | It worked. Nearly every startup was bought by one of the big three EDA vendors |
| **Virtual prototypes** | Software models of a chip so firmware can start before boards exist | Large chip and system companies | Mostly bought (Synopsys, Intel/Wind River) |
| **Board simulation for developers** (Renode, Wokwi, "virtual lab" startups) | Simulate a dev board and its sensors | Firmware teams on small budgets | Mostly stayed small or open source. A $50 dev kit is the competitor |

VirtuLab is built on the third wave (it runs on Renode and QEMU). **The emulation is not the product.** Two things are different:

1. **We sell evidence, not a substitute for the board.** "Write firmware before the board arrives" loses to a cheap dev kit. "Fuzz the parser and try 36 instruction skips through the PIN check on every PR" does not, because nobody does that on a shared bench.
2. **Our buyer is closer to the first wave's buyer.** Medical, automotive and industrial teams pay for late bugs in recalls, failed certification and security incidents. They pay for evidence, and they ask how far to trust it. That is why every sensor model is mapped to its datasheet ([`DATASHEETS.md`](DATASHEETS.md)) and every limit is written down ([`FIDELITY.md`](FIDELITY.md), [`WHERE_EMULATION_STOPS.md`](WHERE_EMULATION_STOPS.md)).

Two lessons from that history still apply to us:

- **Building models is the bottleneck.** The CPU emulator is the easy part. Every sensor needs a model someone writes and checks. Earlier companies that could not automate this stalled. We treat the sensor catalogue as a cost to keep small, not as the moat.
- **The usual exit is acquisition.** If the security angle works, we become a target for EDA or security tool vendors. That is a plan, not a risk.

---

## The problem, in plain words

Companies that build connected devices (medical, industrial, automotive) write software that runs on a small chip, "firmware". The bugs that hurt most are the ones normal tests miss:

- **Malformed input that crashes the device.** A bench run rarely sends a 33-byte message where 32 is the limit.
- **A security check that can be skipped.** A glitch or an attacker skips one instruction, and a wrong PIN is accepted.
- **Memory that quietly grows too large**, until the device runs out on a customer's site.

These bugs are found late, on the bench, or by customers and auditors. Security evidence usually arrives after hardware testing, when changes are most expensive. The bench is shared and slow, so these checks are not repeated on every change.

---

## What VirtuLab does

1. **On every pull request**, it builds the firmware and runs its tests on a virtual Cortex-M board.
2. **It runs the security and safety checks**: fuzzing, fault injection, coverage, and flash and RAM budgets against the base branch.
3. **It posts one comment** on the pull request: what ran, what failed, on which machine, and where emulation stops.

Unit tests and footprint tracking are what bring a team in. The security evidence is why they stay.

---

## The tests

| Test | Plain-language question it answers | Typical bug it catches |
| :-- | :-- | :-- |
| **Fuzzing** | What happens when we throw millions of malformed inputs at the parser? | Crashes and memory errors from bad data |
| **Fault injection** | If one instruction is skipped, does a security check still hold? | A weakened PIN or authentication check |
| **Coverage** | How much of the code do our tests actually exercise? | Untested code hiding in plain sight |
| **Footprint** | Did this change make the program bigger or hungrier than allowed? | "Someone added a huge buffer and we ran out of memory" |
| **Unit tests** | Does the code do what it should, on the virtual device? | Logic errors, wrong sensor handling |

The first two are the differentiator: ordinary unit tests pass, and these checks fail.

---

## The demo (about 3 minutes, start to finish)

Command: `virtulab demo`. Transcript: [`demo-run.txt`](demo-run.txt). The same story, as five pull requests with their real report comments: [`demo-prs/`](demo-prs/).

1. A project is created, and every test goes **green**.
2. Three "bad changes" are made, one at a time. Each is the kind of mistake a real developer makes:
   - a big memory buffer added → **caught by the footprint budget**
   - a one-character off-by-one in a data parser → **caught by fuzzing**
   - a redundant PIN check removed "to save flash" → **caught by fault injection**
3. Every ordinary unit test **still passes** in all three cases. Those bugs would have shipped.

> Suggested story for a live pitch: "Everything is green. Someone makes a small change. Their tests are still green. VirtuLab goes red. Here is why."

---

## Who it's for

- **Firmware teams in medical, automotive and industrial products**, where a late bug costs a recall, a failed certification or a security incident.
- **Teams of 20+ engineers** where the bench is shared and slow.
- **Security and compliance owners** who need evidence that checks hold up, on every change rather than once before release.

*Open question: who signs the purchase, the firmware team lead or the security/compliance owner? The pitch and the price differ.*

---

## Supporting: setup in minutes

Setup is what makes a trial cheap. It supports the pitch but it is not the lead message.

One file, `virtulab.yml`, describes the board, the sensors, how they are wired and which tests run. It can be written by hand, through a guided page in the browser (`virtulab ui`) or through a terminal questionnaire (`virtulab init`):

```yaml
board: stm32f4_discovery
modules:
  temp:     { model: tmp108, bus: i2c1, address: 0x48 }
  pressure: { model: bmp180, bus: i2c1 }
tests:
  unit: {}
  footprint: { flash_increase: 4K, ram_increase: 2K }
  fuzz: { harness: fuzz/fuzz.c, sources: [src/parser.c], seconds: 20 }
```

A **board check** catches impossible setups before anything runs: a sensor wired to the wrong bus, two sensors on the same address, a test that needs a different board. One command writes the CI file for GitHub or GitLab.

**Sensor models** let firmware talk to sensors over I²C, SPI and UART on the virtual board. Each model shows how far to trust it:

- *Datasheet model*: written against the manufacturer's datasheet, with every behaviour mapped to the datasheet section and the line of code ([`DATASHEETS.md`](DATASHEETS.md)).
- *Built-in model*: provided by the emulator, partial, and the tool says what is missing.

---

## What exists today (the MVP)

- Five test types, run together, reported in one PR comment
- Five demo pull requests with real results, including two where all unit tests pass and the security checks fail
- 11 sensor models on I²C, SPI and UART, each mapped to its datasheet
- A real vendor driver (Sensirion SHT3x) running unchanged against our model
- Guided setup in the browser and in the terminal, with a board checker
- CI files generated for GitHub and GitLab, and a Docker image when tools are missing

## What does not exist yet (be honest in front of customers)

- **Own builds are supported, but unproven on real firmware.** `build.command` and fault `functions` work on test projects only. No customer or open-source project has been run end to end. *This is the biggest gap relative to the pitch.* Market reasoning is in [`MARKET.md`](MARKET.md).
- **The generated GitHub workflow has not run on GitHub yet**, and the one-line CI action needs a published Docker image before outsiders can use it.
- **Fuzzing runs on the host**, on the parser logic, not on the virtual device.
- **Fault injection tests one kind of attack** (skipping a single instruction, first execution only).
- **Coverage is line and branch only, no MC/DC**, which safety standards ask for.
- **No sensor model has been compared with real hardware.** They are checked against documents, not silicon.
- Not started: importing chip definitions, debugging and flashing.

---

## Focus now

The history says the buyer decides the business. The security angle is our answer, but so far it is only proven on our own demo. The next steps, in order:

1. **Run the generated workflow on GitHub for real**, and open the five demo PRs as actual pull requests.
2. **Try the existing-build path on a real project,** and fix what breaks.
3. **Find something in firmware we did not write.** Pick an open-source project with a bootloader or authentication check and run the checks on it unchanged. A real finding there is the pitch.
4. **Show that result to 3 to 5 teams in regulated industries** before building more. What they ask for (MC/DC, multi-instruction glitches, reports a certifier accepts) sets the next quarter.

**Priority:** teams defining their own peripherals and scripting sensor input, so bench scenarios become files in the repository.

**Paused:** adding sensors to the catalogue by hand, and replacing vendor IDEs ([`ROADMAP.md`](../ROADMAP.md)). The datasheet mapping stays the quality bar for the 11 models we have.

---

## Questions to refine the pitch

1. **Who signs**: the firmware team lead, or the security/compliance owner?
2. **What would a regulated team need to see** to trust the evidence: a finding in real firmware, a report format their certifier accepts, or MC/DC coverage?
3. **Which security checks matter most to them** after fuzzing and single-skip fault injection?
4. **Open-source core vs. paid service?** Today everything is local and free to run. A likely split: the CI and engine open, the evidence reports and advanced checks paid.
5. **What would a customer need to see in a 10-minute call to say "I'd try this"?** Step 3 above is our best guess.

---

## Glossary (for quick reference)

- **Firmware**: the software that runs inside a device (thermostat, pacemaker, car module).
- **Emulator / virtual board**: a program that behaves like the real chip, so firmware can run on a normal computer.
- **HIL (hardware-in-the-loop)**: testing the firmware on the real board, connected to real or simulated inputs. The final gate before release.
- **Protocol (I²C, SPI, UART)**: the "language" two chips use to talk over wires. I²C and SPI are common for sensors; UART is simple serial.
- **CI (continuous integration)**: automatic checks that run every time someone changes the code.
- **Fuzzing**: automatically feeding a program huge amounts of weird input to see if it breaks.
- **Fault injection**: simulating a hardware glitch or attack, such as skipping one instruction, to see if security holds.
- **MC/DC**: a strict coverage measure that safety standards for aviation and automotive ask for.
- **EDA**: electronic design automation, the software chip designers use. Synopsys, Cadence and Siemens (formerly Mentor) are the big three.
