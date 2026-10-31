//
// VirtuLab device library: Sensirion SHT31 temperature and humidity sensor (I2C).
//
// Written from the SHT3x datasheet and checked against Sensirion's own driver
// (github.com/Sensirion/embedded-i2c-sht3x), which caught a wrong command code. The chip has no
// register pointer: the host writes a 16-bit command, most significant byte first, and then
// reads the answer.
//   single shot, clock stretching off   0x2400 high, 0x240B medium, 0x2416 low repeatability
//                                       (up to 15.5, 6.5 and 4.5 ms)
//   single shot, clock stretching on    0x2C06 high, 0x2C0D medium, 0x2C10 low
//   periodic measurement                0x2032 / 0x2024 / 0x202F  0.5 per second (high / medium / low)
//                                       0x2130 / 0x2126 / 0x212D  1 per second
//                                       0x2236 / 0x2220 / 0x222B  2 per second
//                                       0x2334 / 0x2322 / 0x2329  4 per second
//                                       0x2737 / 0x2721 / 0x272A  10 per second
//   0xE000 fetch the latest periodic result, 0x3093 stop periodic measurement
//   0xF32D read status register  -> 2 bytes + CRC       0x3041 clear status register
//   0x306D / 0x3066 heater on / off (status bit 13)     0x30A2 soft reset
// A measurement answers six bytes: temperature (2) + CRC, humidity (2) + CRC.
//   temperature in degrees C = -45 + 175 * raw / 65535
//   relative humidity in %   = 100 * raw / 65535
// CRC-8: polynomial 0x31, initial value 0xFF, over the two data bytes (CRC of 0xBEEF is 0x92).
// The status register reads 0x8010 after a reset (alert pending, reset detected); the
// clear command resets bits 15, 11, 10 and 4.
// A single-shot result is ready ConversionTime (15.5 ms by default) after its command, on the
// emulator's virtual clock; an earlier read gets 0xFF bytes instead of the NACK real silicon gives.
// With clock stretching the chip holds the clock line until it is done, which the emulator cannot
// do: the result is available at once and the waiting time is not charged. In periodic mode a
// result is ready ConversionTime after the start command and then once per period; a fetch
// consumes it, and a fetch with nothing new reads as 0xFF bytes.
// Not modelled: alert thresholds, the other status bits, ART mode, the repeatability differences in
// accuracy and the real heater's effect on the readings. ConversionTime is the high-repeatability time; medium and low scale with it (6.5 / 15.5 and 4.5 / 15.5).
//
// Usage in a peripherals .repl:   air: VirtuLab.SHT31 @ i2c1 0x44
// Set the air from firmware:      vl_sim("sysbus.i2c1.air Temperature 23.5")
//                                 vl_sim("sysbus.i2c1.air Humidity 40")
//
using System;

using Antmicro.Renode.Core;
using Antmicro.Renode.Logging;
using Antmicro.Renode.Peripherals.I2C;
using Antmicro.Renode.Time;

namespace Antmicro.Renode.Peripherals.VirtuLab
{
    public class SHT31 : II2CPeripheral
    {
        public SHT31()
        {
            Reset();
        }

        public decimal Temperature { get; set; }  // degrees C
        public decimal Humidity { get; set; }     // % relative humidity

        // Send a wrong CRC with every answer, as a noisy bus would.
        public bool CorruptCrc { get; set; }

        // Milliseconds from a measurement command until the result can be read. The datasheet
        // gives 15.5 ms as the maximum for high repeatability; 0 makes the answer ready at once.
        // Measured on the emulator's virtual clock, so it follows the firmware's own SysTick time.
        public decimal ConversionTime { get; set; }

        public void Write(byte[] data)
        {
            if(data.Length < 2)
            {
                return;
            }
            var command = (data[0] << 8) | data[1];
            switch(command)
            {
            case 0xE000:
                Fetch();
                break;
            case 0x3093:
                periodMs = 0;
                Answer(new byte[0]);
                break;
            case 0xF32D:
                Answer(Word((ushort)status));
                break;
            case 0x3041:
                status &= ~0x8C10;
                Answer(new byte[0]);
                break;
            case 0x306D:
                status |= HeaterBit;
                Answer(new byte[0]);
                break;
            case 0x3066:
                status &= ~HeaterBit;
                Answer(new byte[0]);
                break;
            case 0x30A2:
                status = 0x8010;  // the chip resets, the air around it does not change
                periodMs = 0;
                Answer(new byte[0]);
                break;
            default:
                if(!StartMeasurement(command))
                {
                    this.Log(LogLevel.Warning, "Unknown command {0:X4}", command);
                    Answer(new byte[0]);
                }
                break;
            }
            index = 0;
        }

        public byte[] Read(int count = 1)
        {
            var result = new byte[count];
            var ready = responseAvailable && Now >= availableAt;
            if(!ready)
            {
                this.Log(LogLevel.Warning, "Read before the measurement is done: the chip would not acknowledge");
            }
            for(var i = 0; i < count; i++, index++)
            {
                // An unfinished conversion is a NACK on real silicon; the emulator cannot refuse a
                // read, so the bytes read as 0xFF, which no valid answer's CRC accepts.
                result[i] = ready && index < response.Length ? response[index] : (byte)0xFF;
            }
            return result;
        }

        public void FinishTransmission()
        {
            index = 0;
        }

        public void Reset()
        {
            status = 0x8010;
            response = new byte[0];
            index = 0;
            Temperature = 25;
            Humidity = 50;
            CorruptCrc = false;
            ConversionTime = 15.5m;
            availableAt = new TimeInterval();
            nextResultAt = new TimeInterval();
            responseAvailable = false;
            periodMs = 0;
        }

        private TimeInterval Now => this.GetMachine().LocalTimeSource.ElapsedVirtualTime;

        // A result that can be read at once.
        private void Answer(byte[] bytes)
        {
            response = bytes;
            responseAvailable = true;
            availableAt = Now;
        }

        // Repeatability of each measurement command: 0 high, 1 medium, 2 low.
        private static readonly int[] HighCommands = { 0x2400, 0x2C06, 0x2032, 0x2130, 0x2236, 0x2334, 0x2737 };
        private static readonly int[] MediumCommands = { 0x240B, 0x2C0D, 0x2024, 0x2126, 0x2220, 0x2322, 0x2721 };
        private static readonly int[] LowCommands = { 0x2416, 0x2C10, 0x202F, 0x212D, 0x222B, 0x2329, 0x272A };

        // Periodic commands by rate: 0.5, 1, 2, 4 and 10 results per second (high, medium, low each).
        private static readonly int[][] PeriodicCommands =
        {
            new[] { 0x2032, 0x2024, 0x202F }, new[] { 0x2130, 0x2126, 0x212D }, new[] { 0x2236, 0x2220, 0x222B },
            new[] { 0x2334, 0x2322, 0x2329 }, new[] { 0x2737, 0x2721, 0x272A },
        };
        private static readonly int[] PeriodsMs = { 2000, 1000, 500, 250, 100 };

        private bool StartMeasurement(int command)
        {
            var level = Array.IndexOf(HighCommands, command) >= 0 ? 0
                      : Array.IndexOf(MediumCommands, command) >= 0 ? 1
                      : Array.IndexOf(LowCommands, command) >= 0 ? 2 : -1;
            if(level < 0)
            {
                return false;
            }
            var periodic = -1;
            for(var i = 0; i < PeriodicCommands.Length; i++)
            {
                if(Array.IndexOf(PeriodicCommands[i], command) >= 0)
                {
                    periodic = i;
                }
            }
            if(periodic >= 0)
            {
                periodMs = PeriodsMs[periodic];
                nextResultAt = Now + ConversionDelay(level);
                response = new byte[0];
                responseAvailable = false;
                return true;
            }
            periodMs = 0;
            response = Measurement();
            responseAvailable = true;
            var clockStretching = (command & 0xFF00) == 0x2C00;
            availableAt = clockStretching ? Now : Now + ConversionDelay(level);
            return true;
        }

        // The latest periodic result, once per period; nothing new yet reads as 0xFF.
        private void Fetch()
        {
            if(periodMs == 0 || Now < nextResultAt)
            {
                response = new byte[0];
                responseAvailable = false;
                return;
            }
            response = Measurement();
            responseAvailable = true;
            availableAt = Now;
            var period = TimeInterval.FromMicroseconds((ulong)periodMs * 1000);
            do
            {
                nextResultAt = nextResultAt + period;
            }
            while(nextResultAt <= Now);
        }

        private TimeInterval ConversionDelay(int level)
        {
            var scale = level == 0 ? 1m : level == 1 ? 6.5m / 15.5m : 4.5m / 15.5m;
            return TimeInterval.FromMicroseconds((ulong)(ConversionTime * scale * 1000m));
        }

        private byte[] Measurement()
        {
            var t = Counts((Temperature + 45m) * 65535m / 175m);
            var h = Counts(Humidity * 65535m / 100m);
            var a = Word(t);
            var b = Word(h);
            return new[] { a[0], a[1], a[2], b[0], b[1], b[2] };
        }

        private static ushort Counts(decimal value)
        {
            var rounded = (int)Math.Round(value, MidpointRounding.AwayFromZero);
            return (ushort)Math.Max(0, Math.Min(65535, rounded));
        }

        // Two data bytes followed by their CRC.
        private byte[] Word(ushort value)
        {
            var high = (byte)(value >> 8);
            var low = (byte)(value & 0xFF);
            var crc = Crc8(high, low);
            return new[] { high, low, CorruptCrc ? (byte)(crc ^ 0xFF) : crc };
        }

        private static byte Crc8(byte high, byte low)
        {
            byte crc = 0xFF;
            foreach(var b in new[] { high, low })
            {
                crc ^= b;
                for(var bit = 0; bit < 8; bit++)
                {
                    crc = (crc & 0x80) != 0 ? (byte)((crc << 1) ^ 0x31) : (byte)(crc << 1);
                }
            }
            return crc;
        }

        private int status;
        private TimeInterval availableAt;
        private TimeInterval nextResultAt;
        private bool responseAvailable;
        private int periodMs;
        private const int HeaterBit = 0x2000;
        private byte[] response;
        private int index;
    }
}
