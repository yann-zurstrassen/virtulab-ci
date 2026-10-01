//
// VirtuLab device library: TI TMP108 digital temperature sensor (I2C).
//
// Renode's built-in Sensors.TMP108 is a TMP103 stub: an 8-bit register with
// 1 °C resolution, so a driver written against the TMP108 datasheet reads the
// wrong value. This model follows the TMP108 datasheet:
//   - pointer register selects one of four 16-bit registers, sent MSB first
//   - temperature: 12-bit two's complement, left-justified, 0.0625 °C per LSB
//   - the pointer persists across transactions
// Not modelled: conversion modes, ALERT pin, and the configuration/limit
// registers' reset values and behaviour (they are plain read/write storage).
//
// Usage in a peripherals .repl:   tmp108: VirtuLab.TMP108 @ i2c1 0x48
// Set the reading from firmware:  vl_sim("sysbus.i2c1.tmp108 Temperature 21.5")
//
using System;

using Antmicro.Renode.Logging;
using Antmicro.Renode.Peripherals.I2C;
using Antmicro.Renode.Peripherals.Sensor;

namespace Antmicro.Renode.Peripherals.VirtuLab
{
    public class TMP108 : II2CPeripheral, ITemperatureSensor
    {
        public TMP108()
        {
            Reset();
        }

        public decimal Temperature
        {
            get => temperatureCounts * Resolution;
            set
            {
                if(value < MinOperating || value > MaxOperating)
                {
                    this.Log(LogLevel.Warning, "{0} °C is outside the TMP108 operating range ({1} to {2} °C)",
                        value, MinOperating, MaxOperating);
                }
                var counts = (int)Math.Round(value / Resolution, MidpointRounding.AwayFromZero);
                temperatureCounts = (short)Math.Max(MinCounts, Math.Min(MaxCounts, counts));
            }
        }

        public void Write(byte[] data)
        {
            if(data.Length == 0)
            {
                return;
            }
            pointer = data[0] & 0x3;
            byteIndex = 0;
            if(data.Length == 2)
            {
                this.Log(LogLevel.Warning, "Partial register write ignored: registers are 16-bit");
            }
            else if(data.Length >= 3)
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
            temperatureCounts = 0;
            configuration = 0;
            lowLimit = 0;
            highLimit = 0;
        }

        private ushort ReadRegister(int register)
        {
            switch(register)
            {
            case TemperatureRegister:
                return (ushort)(temperatureCounts << 4);
            case ConfigurationRegister:
                return configuration;
            case LowLimitRegister:
                return lowLimit;
            default:
                return highLimit;
            }
        }

        private void WriteRegister(int register, ushort value)
        {
            switch(register)
            {
            case TemperatureRegister:
                this.Log(LogLevel.Warning, "Write to the read-only temperature register ignored");
                break;
            case ConfigurationRegister:
                configuration = value;
                break;
            case LowLimitRegister:
                lowLimit = value;
                break;
            default:
                highLimit = value;
                break;
            }
        }

        private int pointer;
        private int byteIndex;
        private short temperatureCounts;
        private ushort configuration;
        private ushort lowLimit;
        private ushort highLimit;

        private const decimal Resolution = 0.0625m;
        private const decimal MinOperating = -40m;
        private const decimal MaxOperating = 125m;
        private const int MinCounts = -2048;
        private const int MaxCounts = 2047;

        private const int TemperatureRegister = 0;
        private const int ConfigurationRegister = 1;
        private const int LowLimitRegister = 2;
    }
}
