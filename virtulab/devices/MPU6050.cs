//
// VirtuLab device library: InvenSense MPU-6050 6-axis motion sensor (I2C).
//
// Written from the MPU-6050 register map and datasheet:
//   - 0x75 WHO_AM_I reads 0x68 whatever the AD0 pin selects
//   - 0x6B PWR_MGMT_1 resets to 0x40: the chip starts in sleep mode
//   - 0x3B..0x40 accelerometer X, Y, Z, 0x41..0x42 temperature, 0x43..0x48 gyroscope X, Y, Z,
//     each a 16-bit two's complement value, high byte first; the register pointer
//     increments after every byte, so one read can fetch all 14 bytes
//   - accelerometer 16384 / 8192 / 4096 / 2048 counts per g for +-2 / 4 / 8 / 16 g
//     (ACCEL_CONFIG 0x1C bits 4..3)
//   - gyroscope 131 / 65.5 / 32.8 / 16.4 counts per degree per second for +-250 / 500 / 1000 / 2000
//     (GYRO_CONFIG 0x1B bits 4..3)
//   - temperature in degrees C = TEMP_OUT / 340 + 36.53
// Not modelled: sample-rate divider, low-pass filter, FIFO, interrupts, the auxiliary I2C master,
// self-test and the other power modes. Sensor registers read as zero while the chip sleeps.
//
// Usage in a peripherals .repl:   imu: VirtuLab.MPU6050 @ i2c1 0x68
// Set the motion from firmware:   vl_sim("sysbus.i2c1.imu AccelerationZ 1")
//
using System;

using Antmicro.Renode.Logging;
using Antmicro.Renode.Peripherals.I2C;

namespace Antmicro.Renode.Peripherals.VirtuLab
{
    public class MPU6050 : II2CPeripheral
    {
        public MPU6050()
        {
            Reset();
        }

        public decimal AccelerationX { get; set; }  // g
        public decimal AccelerationY { get; set; }
        public decimal AccelerationZ { get; set; }
        public decimal AngularRateX { get; set; }   // degrees per second
        public decimal AngularRateY { get; set; }
        public decimal AngularRateZ { get; set; }
        public decimal Temperature { get; set; }    // degrees C

        public void Write(byte[] data)
        {
            if(data.Length == 0)
            {
                return;
            }
            pointer = data[0];
            for(var i = 1; i < data.Length; i++)
            {
                WriteRegister(pointer, data[i]);
                pointer = (pointer + 1) & 0xFF;
            }
        }

        public byte[] Read(int count = 1)
        {
            var result = new byte[count];
            for(var i = 0; i < count; i++)
            {
                result[i] = ReadRegister(pointer);
                pointer = (pointer + 1) & 0xFF;
            }
            return result;
        }

        public void FinishTransmission()
        {
        }

        public void Reset()
        {
            Array.Clear(registers, 0, registers.Length);
            registers[PowerManagement1] = 0x40;
            pointer = 0;
            AccelerationX = AccelerationY = AccelerationZ = 0;
            AngularRateX = AngularRateY = AngularRateZ = 0;
            Temperature = 25;
        }

        private byte ReadRegister(int register)
        {
            if(register == WhoAmI)
            {
                return 0x68;
            }
            if(register >= AccelerationOut && register < AccelerationOut + 14)
            {
                return SensorByte(register - AccelerationOut);
            }
            return registers[register];
        }

        private void WriteRegister(int register, byte value)
        {
            if(register == WhoAmI || (register >= AccelerationOut && register < AccelerationOut + 14))
            {
                this.Log(LogLevel.Warning, "Write to read-only register {0:X2} ignored", register);
                return;
            }
            registers[register] = value;
        }

        // Layout from 0x3B: accel X, Y, Z (2 bytes each), temperature, gyro X, Y, Z.
        private byte SensorByte(int index)
        {
            if((registers[PowerManagement1] & SleepBit) != 0)
            {
                return 0;
            }
            var word = index / 2;
            int raw;
            if(word < 3)
            {
                var axis = word == 0 ? AccelerationX : word == 1 ? AccelerationY : AccelerationZ;
                var lsbPerG = 16384 >> ((registers[AccelConfig] >> 3) & 0x3);
                raw = Clamp(axis * lsbPerG);
            }
            else if(word == 3)
            {
                raw = Clamp((Temperature - 36.53m) * 340m);
            }
            else
            {
                var axis = word == 4 ? AngularRateX : word == 5 ? AngularRateY : AngularRateZ;
                raw = Clamp(axis * GyroCountsPerDegree[(registers[GyroConfig] >> 3) & 0x3]);
            }
            var bits = (ushort)(short)raw;
            return index % 2 == 0 ? (byte)(bits >> 8) : (byte)(bits & 0xFF);
        }

        private static int Clamp(decimal value)
        {
            var rounded = (int)Math.Round(value, MidpointRounding.AwayFromZero);
            return Math.Max(short.MinValue, Math.Min(short.MaxValue, rounded));
        }

        private int pointer;
        private readonly byte[] registers = new byte[256];

        private static readonly decimal[] GyroCountsPerDegree = { 131m, 65.5m, 32.8m, 16.4m };

        private const int GyroConfig = 0x1B;
        private const int AccelConfig = 0x1C;
        private const int AccelerationOut = 0x3B;
        private const int PowerManagement1 = 0x6B;
        private const int WhoAmI = 0x75;
        private const byte SleepBit = 0x40;
    }
}
