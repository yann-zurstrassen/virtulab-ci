# Validating models against real hardware: draft process

**Status: a draft to work through.** The comparison tool exists. The process around it, and every open question at the end, still needs deciding. No model has been compared with hardware yet.

## The idea

Run the same firmware and the same scenario on a real board and on the twin, record the bus traffic on both, and compare. The twin's side already exists: `virtulab trace` writes `.virtulab/trace/messages.csv`.

```sh
virtulab trace -C my-project --case my_scenario
virtulab compare .virtulab/trace/messages.csv real-capture.csv --tolerance 3
```

Both files use one format, so any logic analyser can feed it once its export is converted:

```
time_ms,bus,address,write,read
116,i2c1,0x55,01,03 B6
```

`compare` lines messages up in order, never by time, because emulated and real timing differ. Who was addressed and what was asked must match exactly. The values read may differ by `--tolerance` counts per 16-bit word, for sensors whose readings vary.

## A process per model

1. **Reference rig:** a real board, the real part, a logic analyser, and a way to set the input where it matters, such as a heater or a voltage source.
2. **Same firmware, same scenario** on the rig and the twin.
3. **Compare** with `virtulab compare`, with the tolerance written down in advance.
4. **Record the result** against the rows of the datasheet map it exercised: board, silicon revision, firmware commit, date. Rows nothing exercised stay "not checked".
5. **Keep the recording as a regression test,** so a model change that breaks agreement fails CI.

Possible labels for a model: cited from the datasheet → run against the vendor's driver → checked on hardware for named scenarios → checked continuously.

## Not built yet

- Converters from real logic-analyser exports. Saleae's export page does not document the I²C column layout, so a converter waits for a real capture file to test against.
- SPI and UART messages. The trace decodes I²C only.
- Register-level comparison through a debug probe.
- Linking results to datasheet-map rows.

## Open questions

1. **Who runs rigs:** VirtuLab for catalog models, customers for their own, or a paid service?
2. **Which inputs can be controlled:** temperature and humidity need climate chambers. Which scenarios are worth proving on hardware?
3. **What "matches" means:** exact bytes, value tolerances, and whether timing should ever be compared.
4. **Silicon revisions and errata:** which revision does a model claim to match?
5. **Business model:** part of the product, or sold as validation work?

Suggested first rig: an STM32F4 Discovery, an SHT31 and a logic analyser. VirtuLab already has that model, its datasheet map and Sensirion's own driver running against it.
