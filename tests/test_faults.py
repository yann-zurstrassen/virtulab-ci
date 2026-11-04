"""The fault vocabulary and how faults are injected into a scenario's inputs."""

import unittest

from virtulab import config
from virtulab import faults as fv
from virtulab.peripherals import Stimulus

CFG = config.from_dict({
    "board": "stm32f4_discovery",
    "modules": {"imu": {"model": "mpu6050", "bus": "i2c1", "address": 0x68},
                "skin": {"model": "sht31", "bus": "i2c1", "address": 0x44}},
    "peripherals": {"tank": {"bus": "i2c2", "address": 0x55,
                             "registers": [{"name": "LEVEL", "at": 1, "size": 2, "access": "ro"}]}},
    "analog": {"adc1": {"inputs": {"oven": 1}}},
})
FALL = [Stimulus(0, "imu", "AccelerationZ", 1.0), Stimulus(1000, "imu", "AccelerationZ", 0.1),
        Stimulus(1300, "imu", "AccelerationZ", 3.5), Stimulus(1340, "imu", "AccelerationZ", 1.0)]


def at(steps, t, prop="AccelerationZ", module="imu"):
    value = None
    for s in sorted(steps, key=lambda s: s.at_ms):
        if s.module == module and s.prop == prop and s.at_ms <= t:
            value = s.value
    return value


class FaultTest(unittest.TestCase):
    def test_every_kind_of_input_has_the_same_vocabulary(self):
        faults = {f.label for f in fv.faults_for(CFG, [*FALL, Stimulus(0, "tank", "LEVEL", 5),
                                                       Stimulus(0, "adc1", "oven", 1.0)])}
        for label in ("imu.AccelerationZ stuck", "imu.AccelerationZ saturated", "imu.AccelerationZ noisy",
                      "tank.LEVEL stuck", "tank.LEVEL saturated", "adc1.oven noisy",
                      "imu garbled", "skin garbled", "tank garbled"):
            self.assertIn(label, faults)
        # I2C cannot refuse an address in the emulator, and the ADC has no wire to fail
        self.assertFalse(any(f.endswith("silent") for f in faults))
        self.assertFalse(any(f.startswith("adc1 ") for f in faults))

    def test_stuck_hides_the_change_and_then_recovers(self):
        steps = fv.inject(CFG, FALL, fv.Fault("imu", "stuck", "AccelerationZ"), 1300)
        self.assertEqual(at(steps, 1350), 0.1)       # the impact never shows
        self.assertEqual(at(steps, 1900), 1.0)       # back to the scenario after 600 ms

    def test_saturated_pins_the_top_of_the_data_format(self):
        steps = fv.inject(CFG, FALL, fv.Fault("imu", "saturated", "AccelerationZ"), 1000)
        self.assertEqual(at(steps, 1200), 16.0)
        self.assertEqual(at(steps, 1600), 1.0)

    def test_noisy_jitters_around_the_scenario_value(self):
        steps = fv.inject(CFG, FALL, fv.Fault("imu", "noisy", "AccelerationZ"), 200)
        inside = [s.value for s in steps if 200 <= s.at_ms < 800 and s.prop == "AccelerationZ"]
        self.assertEqual(len(inside), 60)
        self.assertAlmostEqual(max(inside), 1.64)
        self.assertAlmostEqual(min(inside), 0.36)

    def test_a_wire_fault_restores_the_scenarios_own_state(self):
        corrupted = [Stimulus(0, "skin", "Temperature", 36.8), Stimulus(400, "skin", "CorruptCrc", 1)]
        labels = {f.label for f in fv.faults_for(CFG, corrupted)}
        self.assertNotIn("skin garbled", labels)
        self.assertNotIn("skin.CorruptCrc stuck", labels)      # a fault switch is not a measurement
        steps = fv.inject(CFG, FALL, fv.Fault("imu", "garbled"), 1300)
        self.assertEqual(at(steps, 1500, "Garbled"), 1.0)
        self.assertEqual(at(steps, 1900, "Garbled"), 0.0)

    def test_moments_follow_the_inputs(self):
        self.assertEqual(fv.moments(FALL, [1300, 1560]), [1000, 1300, 1560])
        many = [Stimulus(t, "imu", "AccelerationZ", 1) for t in range(200, 2000, 200)]
        self.assertEqual(len(fv.moments(many, [])), 4)
        self.assertEqual(fv.moments([Stimulus(0, "imu", "AccelerationZ", 1)], []), [500.0])

    def test_fault_keys_round_trip(self):
        for f in (fv.Fault("imu", "garbled"), fv.Fault("imu", "stuck", "AccelerationZ")):
            self.assertEqual(fv.parse(f.key), f)
        with self.assertRaises(ValueError):
            fv.parse("imu.*.melted")


if __name__ == "__main__":
    unittest.main()
