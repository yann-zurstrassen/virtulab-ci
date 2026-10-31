# Sensirion's own SHT3x driver on a virtual board

This is real, unmodified vendor code: [Sensirion's SHT3x driver](https://github.com/Sensirion/embedded-i2c-sht3x)
(BSD 3-Clause), running on an emulated STM32F4 board against VirtuLab's SHT31 model. No SHT31 hardware is
involved. The question it answers is: *does code the chip maker wrote, knowing nothing about VirtuLab, work
against our model?*

```sh
./run.sh        # from this folder; builds VirtuLab's Docker image first if you have no local Renode
```

```
✅ Sensirion's driver is unmodified
...
test_vendor_driver_resets_the_sensor_and_reads_its_status:PASS
test_vendor_single_shot_in_every_mode:PASS
test_vendor_formulas_at_the_ends_of_the_range:PASS
test_vendor_periodic_measurement:PASS
test_vendor_heater_switches_status_bit_13:PASS
test_vendor_driver_refuses_a_corrupted_answer:PASS
test_vendor_driver_reports_a_chip_slower_than_its_datasheet:PASS
test_vendor_driver_reports_a_missing_sensor:PASS
✅ PASSED — 8/8 tests passed
```

## What is here

| Path | What it is | Whose |
| :-- | :-- | :-- |
| `vendor/sensirion/` | `sht3x_i2c.c`, `sensirion_i2c.c`, ... exactly as published (checksums in `SHA256SUMS`, source and commit in `VENDORED.md`) | Sensirion |
| `hal/sensirion_i2c_hal.c` | The six functions the vendor driver asks for (read, write, sleep, init...), 50 lines on top of this project's I²C and clock drivers | ours, the only glue |
| `src/`, `include/` | A polled I²C driver and a SysTick millisecond clock for the STM32F4 (from VirtuLab's starter template) | ours |
| `test/test_sht3x_vendor.c` | Eight tests that call the vendor's API like a product would | ours |
| `virtulab.yml` | The board, the sensor on I²C1 at 0x44 and the tests to run: this is all VirtuLab needs | ours |

## What the tests do

They use Sensirion's calls (`sht3x_measure_single_shot`, `sht3x_start_periodic_measurement`,
`sht3x_read_status_register`, heater and reset commands) and set what the emulated sensor measures from the test
with `vl_sim()`. Three of them break the sensor on purpose:

- a **corrupted checksum** must make the vendor driver return `CRC_ERROR`, not a wrong temperature;
- a chip **slower than its datasheet** (40 ms against the 16 ms the driver waits) must be an error;
- a **missing sensor** (nothing at 0x45) must be reported as a NACK.

## What the vendor driver taught us about our model

Running unchanged vendor code against our model found real mistakes in the model, which a test written by us
would not have caught, because we wrote the model and the test from the same understanding:

1. **A wrong command code.** We had medium repeatability as `0x2432`. Sensirion's driver sends `0x240B`.
2. **One conversion time for everything.** The vendor driver waits 16, 7 and 5 ms for high, medium and low
   repeatability. Our model made every measurement take 15.5 ms, so low and medium reads came back not ready.
   They now take 15.5, 6.5 and 4.5 ms, the datasheet maxima.
3. **Clock stretching, periodic mode and the heater were missing.** All three are used by the vendor driver. The
   model now accepts them. With clock stretching the emulator cannot hold the clock line, so the result is simply
   available at once.

The same run also showed two things about the vendor code that we did not change and cannot judge:

- The enum in `sht3x_i2c.h` lists `0x273A` for 10 results per second at low repeatability, while the code uses
  `0x272A`. The enum value appears unused. The model accepts the one the code sends.
- `sht3x_blocking_read_measurement()` waits for bits 9 to 6 of the status register to become non-zero. Our model never
  sets them, so that function would wait forever against it, and it is not tested here. We could not tell from the
  datasheet we have whether a real chip sets those bits.

## What this does not show

- The model has still never been compared with a real SHT31. It now agrees with the chip maker's driver, which is
  strong evidence about the commands, the checksums and the waiting times, and says nothing about electrical
  behaviour or accuracy.
- The tests cover single shot (all modes), periodic mode at 10 results per second, status, heater and reset. They do
  not cover ART mode, alerts, or the other periodic rates.
- Time is the emulator's virtual clock, so "waits 16 ms" is exact. Bus transfer time is not modelled.
