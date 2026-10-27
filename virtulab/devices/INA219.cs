//
// VirtuLab device library: TI INA219 current and power monitor (I2C).
//
// Written from the INA219 datasheet. Six 16-bit registers, sent most significant
// byte first, selected by a pointer byte that persists between transactions:
//   0x00 Configuration  (reset 0x399F; bit 15 RST resets the chip)
//   0x01 Shunt voltage  (signed, 10 uV per count)
//   0x02 Bus voltage    (bits 15..3 = voltage in 4 mV steps, bit 1 CNVR conversion ready)
//   0x03 Power          (= current register x bus-voltage register / 5000)
//   0x04 Current        (= shunt voltage register x calibration / 4096)
//   0x05 Calibration    (reset 0; current and power read 0 until it is written)
// The shunt-voltage range follows the PGA bits of the configuration register
// (+-40, 80, 160 or 320 mV): larger voltages saturate at the end of the range.
// Not modelled: conversion time, averaging and operating modes, the bus-voltage
// range bit, the overflow flag (OVF) and the alert behaviour of the calibration bit 0.
//
// Usage in a peripherals .repl:   power: VirtuLab.INA219 @ i2c1 0x40
// Set the load from firmware:     vl_sim("sysbus.i2c1.power BusVoltage 12.0")
//                                 vl_sim("sysbus.i2c1.power Current 1.5")
//
using System;

using Antmicro.Renode.Logging;
using Antmicro.Renode.Peripherals.I2C;

namespace Antmicro.Renode.Peripherals.VirtuLab
{
    public class INA219 : II2CPeripheral
    {
        public INA219()
        {
            Reset();
        }

        // Volts on the monitored bus, 0 to 32.
        public decimal BusVoltage { get; set; }

        // Amps flowing through the shunt, negative = reverse.
        public decimal Current { get; set; }

        // Ohms; the 0.1 ohm shunt of the common breakout boards by default.
        public decimal ShuntResistance { get; set; }

        public void Write(byte[] data)
        {
            if(data.Length == 0)
            {
                return;
            }
            pointer = data[0] & 0x7;
            byteIndex = 0;
            if(data.Length >= 3)
            {
                WriteRegister(pointer, (ushort)((data[1] << 8) | data[2]));
            }
        }

        public byte[] Read(int count = 1)
        {
            var value = ReadRegister(pointer);
            var result = new byte[count];
            for(var i = 0; i < count; i++, byteIndex++)
            {
                result[i] = byteIndex % 2 == 0 ? (byte)(value >> 8) : (byte)value;
            }
            return result;
        }

        public void FinishTransmission()
        {
            byteIndex = 0;
        }

        public void Reset()
        {
            pointer = 0;
            byteIndex = 0;
            configuration = ConfigurationReset;
            calibration = 0;
            BusVoltage = 0;
            Current = 0;
            ShuntResistance = 0.1m;
        }

        private ushort ReadRegister(int register)
        {
            switch(register)
            {
            case ConfigurationRegister:
                return configuration;
            case ShuntVoltageRegister:
                return (ushort)ShuntCounts();
            case BusVoltageRegister:
                return (ushort)((BusCounts() << 3) | ConversionReady);
            case PowerRegister:
                return (ushort)Math.Abs(CurrentCounts() * BusCounts() / 5000);
            case CurrentRegister:
                return (ushort)CurrentCounts();
            case CalibrationRegister:
                return calibration;
            default:
                return 0;
            }
        }

        private void WriteRegister(int register, ushort value)
        {
            switch(register)
            {
            case ConfigurationRegister:
                if((value & ResetBit) != 0)
                {
                    configuration = ConfigurationReset;
                    calibration = 0;
                }
                else
                {
                    configuration = value;
                }
                break;
            case CalibrationRegister:
                calibration = value;
                break;
            default:
                this.Log(LogLevel.Warning, "Write to read-only register {0} ignored", register);
                break;
            }
        }

        // 10 uV per count, limited to the range the PGA bits select.
        private int ShuntCounts()
        {
            var counts = (int)Math.Round(Current * ShuntResistance / 0.00001m, MidpointRounding.AwayFromZero);
            var limit = 4000 << ((configuration >> 11) & 0x3);
            return Math.Max(-limit, Math.Min(limit, counts));
        }

        // 4 mV per count, 13 bits.
        private int BusCounts()
        {
            var counts = (int)Math.Round(BusVoltage / 0.004m, MidpointRounding.AwayFromZero);
            return Math.Max(0, Math.Min(0x1FFF, counts));
        }

        // Current register: shunt register x calibration / 4096 (signed, truncated).
        private int CurrentCounts()
        {
            return ShuntCounts() * calibration / 4096;
        }

        private int pointer;
        private int byteIndex;
        private ushort configuration;
        private ushort calibration;

        private const ushort ConfigurationReset = 0x399F;
        private const ushort ResetBit = 0x8000;
        private const int ConversionReady = 0x2;

        private const int ConfigurationRegister = 0;
        private const int ShuntVoltageRegister = 1;
        private const int BusVoltageRegister = 2;
        private const int PowerRegister = 3;
        private const int CurrentRegister = 4;
        private const int CalibrationRegister = 5;
    }
}
