# A motor and a limit switch

"The motor runs, then a switch trips." No test code in the firmware decides that. A rule in [`virtulab.yml`](virtulab.yml) watches the firmware's motor pin, and after 100 ms of virtual time closes the switch input:

```yaml
rules:
  - { when: PA1, is: high, for: 100ms, set: PA2, to: 1 }
```

Rules can also set a sensor input, such as `tank.LEVEL`. Each rule fires once.

- `switch_trips_in_time` shows the firmware reacting to the world.
- `switch_never_trips` is a jammed gate. The firmware must time out and stop the motor, and the fault sweep checks that one skipped instruction cannot leave it running.

Add `-DGATE_HARDENED=0` to `cflags` to see what the sweep finds with a single stop write.

Anything rules cannot express can be a normal Renode model. Point to your own files, and VirtuLab loads them as they are:

```yaml
models: [models/MyDevice.cs]
repl: models/mydevice.repl
```
