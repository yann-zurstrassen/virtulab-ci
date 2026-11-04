# Bench session: STM32F4 Discovery + SHT31 + logic analyser

Goal: run **one firmware image** on a real board and on the twin, record the I²C bus on both, and compare. This is the first real check of a VirtuLab model against silicon.

## What you need

- STM32F4 Discovery board (STM32F407VG) and its USB cable
- SHT31 breakout board. Check that it has pull-up resistors on SDA and SCL. Most breakouts do, and the board needs them.
- Logic analyser with an I²C decoder, such as a Saleae, or a cheap one that sigrok/PulseView supports
- 4 jumper wires, plus 3 probe clips for the analyser
- A reference thermometer and hygrometer, if you also want to compare readings and not just the conversation

## Wiring

| SHT31 | Discovery |
| :-- | :-- |
| VIN | 3V |
| GND | GND |
| SCL | PB6 |
| SDA | PB7 |
| ADDR | GND, which gives address 0x44 |

Logic analyser: channel 0 to SCL (PB6), channel 1 to SDA (PB7), ground to GND.

## Steps

1. **Build the image once**, and use this exact file for both sides:
   ```sh
   docker run --rm -v "$PWD:/workspace" -w /workspace virtulab-review trace
   shasum -a 256 .virtulab/trace/build/firmware.elf     # note this
   ```
2. **Flash it** to the board with whatever you use for ST-LINK. These commands are common, but not tested here:
   ```sh
   openocd -f board/stm32f4discovery.cfg -c "program .virtulab/trace/build/firmware.elf verify reset exit"
   # or: STM32CubeProgrammer, GUI or CLI
   ```
3. **Capture:** start the analyser with an I²C decoder on SCL and SDA, then press the board's reset button. The firmware does one status read, then 10 measurements 100 ms apart, about 1.1 s in all.
4. **Export the analyser's decoded I²C results** to CSV and send me the file. I'll write the converter to VirtuLab's message format from a real export, because Saleae does not document the column layout.
5. **Set the twin to the room:** put the reference thermometer's readings into `virtulab.yml` (`air.Temperature`, `air.Humidity`) and re-run step 1. The firmware stays the same, so check the hash.
6. **Compare:**
   ```sh
   virtulab compare .virtulab/trace/messages.csv real.csv --frame 2+1 --tolerance 75,1311
   ```
   `2+1` means each reply is a 2-byte value plus a checksum. 75 and 1311 counts are the SHT31's typical accuracy, ±0.2 °C and ±2 %RH (SHT3x-DIS datasheet, Version 7, p. 2, Tables 1 and 2). Add your reference instrument's own accuracy to these.

## What the comparison can and cannot show

- **It can show** whether the twin and the chip have the same conversation: same commands, same reply lengths, the same status register (`0x8010` after power-up on the twin), and whether real silicon refuses or stretches anything the model does not.
- **Readings** only check the conversion when the reference instrument is good, and only within the tolerances above.
- **Not tested before:** the I²C driver and the clock setup were written for the emulator and have never run on real silicon. If the bus is silent, suspect the driver first, not the model. That is part of what this session tests.
- **Timing is not compared.** The twin answers a measurement after its conversion time on the virtual clock, and the real chip may take a different time. Note the real delay between `24 00` and the reply in the capture: it is worth recording.

## The twin's side, for reference

Run on the twin at 22.0 °C and 45 %RH: 22 messages, starting with

```
3,i2c1,0x44,F3 2D,            read status command
14,i2c1,0x44,,80 10 E1        status 0x8010, CRC 0xE1
14,i2c1,0x44,24 00,           single shot, high repeatability, no clock stretching
30,i2c1,0x44,,62 03 5E 73 33 01
```
