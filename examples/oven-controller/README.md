# An oven controller, with no analog rig

Firmware reads a temperature sensor through the STM32F4's ADC. On a bench, a source would drive that pin. Here [`inputs/overheat.csv`](inputs/overheat.csv) holds the voltage profile, including a reading at the 3.3 V rail that stands for a broken sensor wire.

```sh
virtulab run
```

- **Unit tests** follow the profile from heating to overheat to sensor fault.
- **Fault injection** runs during the scenario. With a real overheat on the ADC input, it skips one instruction at a time and checks that the controller never reports "heating".

To see what the sweep finds in a plain check, add `-DOVEN_HARDENED=0` to `cflags`. Unit tests still pass, and single skipped instructions hide the overheat. The hardened version reads twice and only reports heating when both reads agree.

Voltages are ideal, so the analog front end and ADC accuracy still need the real bench. A clean sweep is evidence for this build and this fault model, not proof. Each instruction is skipped on its first execution only.
