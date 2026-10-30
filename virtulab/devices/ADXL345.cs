//
// VirtuLab device library: Analog Devices ADXL345 3-axis accelerometer (SPI).
//
// Written from the ADXL345 datasheet, SPI 4-wire interface (checked against Rev. 0):
//   - first byte of a transaction: bit 7 = read, bit 6 = multiple bytes
//     (address auto-increments), bits 5..0 = register address
//   - DEVID (0x00) reads 0xE5
//   - DATAX0..DATAZ1 (0x32..0x37): 16-bit little-endian two's complement
//   - scale: 256 LSB/g in full-resolution mode (DATA_FORMAT bit 3) at any range,
//     otherwise 10-bit with 256/128/64/32 LSB/g for +-2/4/8/16 g
//   - output registers are read-only; the others are plain storage
// Not modelled: SPI mode (CPOL/CPHA), interrupts and FIFO, tap/activity
// detection, offset registers, output data rate and self-test, and the
// justify bit. Output reads as zero until POWER_CTL.Measure is set.
// Chip select is handled by the SPI multiplexer in front of the device: it calls
// FinishTransmission() when the line goes high, which ends a transaction.
//
// Usage in a peripherals .repl:   accel: VirtuLab.ADXL345 @ mux 0   (mux: SPI.SPIMultiplexer @ spi1)
// Set the reading from firmware:  vl_sim("sysbus.spi1.accel AccelerationX 0.5")
// Fault injection:                vl_sim("sysbus.spi1.accel Responding false")
//                                 (a disconnected sensor leaves MISO high: every read is 0xFF)
//
using System;

using Antmicro.Renode.Logging;
using Antmicro.Renode.Peripherals.SPI;

namespace Antmicro.Renode.Peripherals.VirtuLab
{
    public class ADXL345 : ISPIPeripheral
    {
        public ADXL345()
        {
            Reset();
        }

        public decimal AccelerationX { get => acceleration[0]; set => acceleration[0] = value; }
        public decimal AccelerationY { get => acceleration[1]; set => acceleration[1] = value; }
        public decimal AccelerationZ { get => acceleration[2]; set => acceleration[2] = value; }

        public bool Responding { get; set; }

        public byte Transmit(byte data)
        {
            if(!Responding)
            {
                return 0xFF;
            }
            if(expectCommand)
            {
                expectCommand = false;
                reading = (data & 0x80) != 0;
                multiple = (data & 0x40) != 0;
                address = data & 0x3F;
                bytesAfterCommand = 0;
                return 0x00;
            }
            var firstData = bytesAfterCommand == 0;
            bytesAfterCommand++;
            if(reading)
            {
                if(!multiple && !firstData)
                {
                    return 0x00;
                }
                var value = ReadRegister(address);
                address = (address + 1) & 0x3F;
                return value;
            }
            if(multiple || firstData)
            {
                WriteRegister(address, data);
                address = (address + 1) & 0x3F;
            }
            return 0x00;
        }

        public void FinishTransmission()
        {
            expectCommand = true;
        }


        public void Reset()
        {
            expectCommand = true;
            Responding = true;
            Array.Clear(registers, 0, registers.Length);
            registers[BwRate] = 0x0A;
            for(var i = 0; i < 3; i++)
            {
                acceleration[i] = 0;
            }
        }

        private byte ReadRegister(int register)
        {
            if(register == DevId)
            {
                return 0xE5;
            }
            if(register >= DataX0 && register <= DataZ1)
            {
                return DataByte(register - DataX0);
            }
            return registers[register];
        }

        private void WriteRegister(int register, byte value)
        {
            if(register == DevId || (register >= DataX0 && register <= DataZ1))
            {
                this.Log(LogLevel.Warning, "Write to read-only register {0:X2} ignored", register);
                return;
            }
            registers[register] = value;
        }

        private byte DataByte(int index)
        {
            if((registers[PowerCtl] & MeasureBit) == 0)
            {
                return 0;
            }
            var axis = index / 2;
            var fullResolution = (registers[DataFormat] & FullResBit) != 0;
            var range = registers[DataFormat] & 0x3;
            var lsbPerG = fullResolution ? 256 : 256 >> range;
            var lowest = fullResolution ? -4096 : -512;
            var highest = fullResolution ? 4095 : 511;
            var raw = (int)Math.Round(acceleration[axis] * lsbPerG, MidpointRounding.AwayFromZero);
            raw = Math.Max(lowest, Math.Min(highest, raw));
            var word = (ushort)(short)raw;
            return index % 2 == 0 ? (byte)(word & 0xFF) : (byte)(word >> 8);
        }

        private bool expectCommand;
        private bool reading;
        private bool multiple;
        private int address;
        private int bytesAfterCommand;
        private readonly byte[] registers = new byte[64];
        private readonly decimal[] acceleration = new decimal[3];

        private const int DevId = 0x00;
        private const int BwRate = 0x2C;
        private const int PowerCtl = 0x2D;
        private const int DataFormat = 0x31;
        private const int DataX0 = 0x32;
        private const int DataZ1 = 0x37;
        private const byte MeasureBit = 0x08;
        private const byte FullResBit = 0x08;
    }
}
