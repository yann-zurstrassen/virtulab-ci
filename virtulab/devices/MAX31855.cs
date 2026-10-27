//
// VirtuLab device library: Maxim MAX31855 thermocouple-to-digital converter (SPI, read only).
//
// Written from the MAX31855 datasheet. A read clocks out 32 bits, most significant first
// (the chip ignores what it receives):
//   bits 31..18  thermocouple temperature, 14-bit two's complement, 0.25 degrees C per count
//   bit  17      reserved, 0
//   bit  16      fault: set when any of the three fault bits is set
//   bits 15..4   internal (cold junction) temperature, 12-bit two's complement, 0.0625 degrees C per count
//   bit  3       reserved, 0
//   bit  2       SCV  thermocouple shorted to VCC
//   bit  1       SCG  thermocouple shorted to GND
//   bit  0       OC   thermocouple open (not connected)
// Chip select high ends the read; the next read starts again at bit 31. Pulling it high after
// 16 bits gives only the upper half. Not modelled: conversion time (the value is current),
// the 70 ms conversion cycle, and the measurement range limits of the thermocouple types.
//
// Usage in a peripherals .repl:   tc: VirtuLab.MAX31855 @ spi1_mux 1
// Set the reading from firmware:  vl_sim("sysbus.spi1.spi1_mux.tc ThermocoupleTemperature 100.25")
//                                 vl_sim("sysbus.spi1.spi1_mux.tc OpenCircuit true")
//
using System;

using Antmicro.Renode.Peripherals.SPI;

namespace Antmicro.Renode.Peripherals.VirtuLab
{
    public class MAX31855 : ISPIPeripheral
    {
        public MAX31855()
        {
            Reset();
        }

        public decimal ThermocoupleTemperature { get; set; }  // degrees C
        public decimal InternalTemperature { get; set; }      // degrees C
        public bool OpenCircuit { get; set; }
        public bool ShortToGround { get; set; }
        public bool ShortToVcc { get; set; }

        // False = the chip is not connected: the line stays high and every bit reads 1.
        public bool Responding { get; set; }

        public byte Transmit(byte data)
        {
            if(!Responding)
            {
                return 0xFF;
            }
            var frame = Frame();
            var shift = 24 - 8 * position;
            position++;
            return shift >= 0 ? (byte)(frame >> shift) : (byte)0x00;
        }

        public void FinishTransmission()
        {
            position = 0;
        }

        public void Reset()
        {
            position = 0;
            ThermocoupleTemperature = 25;
            InternalTemperature = 25;
            OpenCircuit = ShortToGround = ShortToVcc = false;
            Responding = true;
        }

        private uint Frame()
        {
            var thermocouple = (uint)(Counts(ThermocoupleTemperature / 0.25m, 8191) & 0x3FFF);
            var internalJunction = (uint)(Counts(InternalTemperature / 0.0625m, 2047) & 0xFFF);
            var frame = (thermocouple << 18) | (internalJunction << 4);
            if(OpenCircuit)
            {
                frame |= 1u << 0;
            }
            if(ShortToGround)
            {
                frame |= 1u << 1;
            }
            if(ShortToVcc)
            {
                frame |= 1u << 2;
            }
            if(OpenCircuit || ShortToGround || ShortToVcc)
            {
                frame |= 1u << 16;
            }
            return frame;
        }

        private static int Counts(decimal value, int maximum)
        {
            var rounded = (int)Math.Round(value, MidpointRounding.AwayFromZero);
            return Math.Max(-maximum - 1, Math.Min(maximum, rounded));
        }

        private int position;
    }
}
