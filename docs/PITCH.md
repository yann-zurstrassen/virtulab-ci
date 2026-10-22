# VirtuLab: pitch draft (for refining)

---

## The one-liner

**Test your device's software before the hardware exists, on every change, without a lab.**

You describe your hardware in one small file (which board, which sensors, which connections). VirtuLab builds a virtual copy of that device and runs your software on it automatically, every time someone changes the code.

---

## The problem, in plain words

Companies that build connected devices (medical, industrial, automotive, IoT) write software that runs on a small chip, "firmware". Testing it is slow and painful:

- **You need the physical hardware.** Boards arrive late, are expensive, and there are never enough for every developer.
- **Every sensor and connection type is its own mini-project.** Talking to a temperature sensor over one kind of wiring (a "protocol": I²C, SPI, UART) means reading a 60-page datasheet and writing test setups by hand. Add a second sensor and you redo much of it.
- **Tests live on one person's desk.** "It works on Marc's board" is not the same as "it is checked on every change".
- **Setting up automated testing (CI) takes days or weeks** of specialist work, so many teams simply don't, and bugs reach the real device.
- **The worst bugs are the ones normal tests miss**: memory that quietly grows too large, malformed input that crashes the device, a security check that can be skipped.

The result: bugs are found late (expensive), or by customers (very expensive).

---

## What VirtuLab does

1. **You choose your hardware**, not write test infrastructure.
2. **You tick the tests you want.**
3. **You get automated testing** that runs on every code change and tells you pass/fail in plain language.

No lab, no boards on desks, no weeks of setup.

---

## The setup experience (the part we want to insist on)

Everything starts with a short page that opens in the browser (`virtulab ui`). It is a guided form, in four steps:

| Step | What the user does | What they see |
| :-- | :-- | :-- |
| **1. Pick a board** | Choose from a list (e.g. an STM32 Discovery board) | What the board can connect to: its available buses |
| **2. Filter by protocol** | Choose I²C, SPI or UART ("how does my sensor talk?") | Only the sensors that fit that wiring |
| **3. Add sensors** | Click a temperature or pressure sensor, pick where it's plugged in | A live diagram of the board with the sensor attached |
| **4. Pick tests** | Tick the checks they care about | A plain-language explanation of each |

At every moment a **"board check"** tells them whether the setup is possible, *before* anything runs. For example:

- "That sensor speaks I²C, but you plugged it into an SPI connection."
- "Two sensors are using the same address on the same bus."
- "This test needs a different type of board."

Then one click gives them:

- a **project file** (`virtulab.yml`) describing their hardware, readable by a human, saved with their code;
- the **CI setup file** for GitHub or GitLab, already written;
- **sample code** that passes on the first run, so they see green immediately and can replace it with their own.

Not everyone likes browsers. The same flow also works as a **terminal questionnaire** (`virtulab init`) or by editing the file directly. They all produce the same project file.

### What the hardware description looks like

This is roughly everything a user writes to say "STM32 board with a temperature sensor and a pressure sensor":

```yaml
board: stm32f4_discovery
modules:
  temp:     { model: tmp108, bus: i2c1, address: 0x48 }
  pressure: { model: bmp180, bus: i2c1 }
tests: [unit, footprint, coverage, fuzz]
```

Four lines instead of weeks of test infrastructure. (This is the single most important message for the pitch.)

---

## The friction it removes: protocols and sensors

**Today, without VirtuLab**, supporting a new sensor in your tests means:
read the datasheet, write a simulation of the chip, wire it to the emulator, wire the right communication protocol, write the test harness, and repeat for the next sensor.

**With VirtuLab**, a sensor is a catalogue item.
Pick it, say where it's plugged in, done. The catalogue already knows:

- **which protocol it speaks** (so the tool refuses wrong wiring and explains why);
- **which addresses are valid** (so conflicts are caught up front);
- **how trustworthy the simulation is**, shown as one of two labels:
  - *Datasheet model*: written against the manufacturer's datasheet, accurate.
  - *Built-in model*: provided by the emulator, partial, and the tool tells you what's missing.

The long-term value is in the catalogue: **every sensor added once benefits every customer forever.** That is the business moat, and also the thing to size and prioritise.

---

## The tests the user can select

| Test | Plain-language question it answers | Typical bug it catches |
| :-- | :-- | :-- |
| **Unit tests** | Does the code do what it should, on the virtual device? | Logic errors, wrong sensor handling |
| **Footprint** | Did this change make the program bigger or hungrier than allowed? | "Someone added a huge buffer and we ran out of memory" |
| **Coverage** | How much of the code do our tests actually exercise? | Untested code hiding in plain sight |
| **Fuzzing** | What happens when we throw thousands of malformed inputs at it? | Crashes and memory errors from bad data |
| **Fault injection** | If an attacker skips one instruction, does a security check still hold? | A weakened PIN or authentication check |

The last three are the differentiator: ordinary unit tests pass on all of them, and these tests don't.

---

## The demo (about 90 seconds, start to finish)

Command: `virtulab demo`. Transcript: `docs/demo-run.txt`.

1. A project is created, and every test goes **green**.
2. Three "bad changes" are made, one at a time. Each is the kind of mistake a real developer makes:
   - a big memory buffer added → **caught by the footprint budget**
   - a one-character off-by-one in a data parser → **caught by fuzzing**
   - a security check quietly weakened → **caught by fault injection**
3. Every ordinary unit test **still passes** in all three cases, which is the whole point: those bugs would have shipped.

> Suggested story for a live pitch: "Everything is green. Someone makes a small change. Their tests are still green. VirtuLab goes red. Here is why."

---

## Who it's for (to refine)

- **Teams building connected hardware** that cannot test on real devices for every change: startups, and engineering teams in regulated industries (medical, automotive, industrial) where bugs are costly.
- **Teams moving to a "security by default" posture** who need evidence that checks hold up (fuzzing and fault injection give them that).
- **Developers new to embedded**, because the guided setup removes the specialist knowledge needed to start.

*Open question: who is the first paying customer, the individual developer, the team lead, or the company's security/compliance owner?*

---

## What exists today (the MVP)

- Guided setup in the browser and in the terminal
- A board and wiring checker that explains errors in plain language
- Five selectable test types, all verified working together
- Automatic generation of the CI setup for GitHub and GitLab
- Sample code that passes first time
- A scripted end-to-end demo with a recorded run
- If a machine lacks the needed tools, the tests run in a ready-made Docker image

## What does not exist yet (be honest in front of customers)

- **Sensor catalogue is tiny: two sensors** (a temperature one and a pressure one), both on the I²C protocol. No SPI or UART sensors yet, though the board supports those connections. *This is the biggest gap relative to the pitch.*
- **One board** can host sensors. Other boards can run code tests only.
- **Fault injection doesn't combine with sensors** today (it needs a different type of virtual board).
- **The generated GitHub setup has not been run on GitHub yet**, and the one-line CI action needs a new Docker image published before it works for outsiders.
- **Fuzzing runs on the developer's computer**, not on the virtual device, so it tests the logic, not the hardware behaviour.
- **Fault injection tests one kind of attack** (skipping a single instruction).
- Not started: importing chip definitions from vendors, pin/clock planning, debugging/flashing, support for existing build systems, and standard test-report formats.

---

## Questions for you, to refine the pitch

1. **Who feels the pain most**, and who pays: developer, team lead, or security/compliance?
2. **Which message wins**: "no hardware needed" (speed), "setup in minutes" (friction), or "catches the bugs ordinary tests miss" (safety)? The demo supports all three, but a pitch needs one lead.
3. **Which sensors and protocols do your target customers actually use?** This decides what we add next, and it is the strongest lever for credibility.
4. **Is "catalogue of simulated sensors" our product, or is the product the CI automation?** The moat and the pricing differ completely.
5. **Open source core vs. paid service?** Today everything is local and free to run.
6. **What would a customer need to see in a 10-minute call to say "I'd try this"?** We may be able to build exactly that demo.

---

## Glossary (for quick reference)

- **Firmware**: the software that runs inside a device (thermostat, pacemaker, car module).
- **Emulator / virtual board**: a program that behaves like the real chip, so firmware can run on a normal computer.
- **Protocol (I²C, SPI, UART)**: the "language" two chips use to talk over wires. I²C and SPI are common for sensors; UART is simple serial.
- **CI (continuous integration)**: automatic checks that run every time someone changes the code.
- **Fuzzing**: automatically feeding a program huge amounts of weird input to see if it breaks.
- **Fault injection**: simulating a hardware glitch or attack, such as skipping one instruction, to see if security holds.
