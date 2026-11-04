//
// VirtuLab device library: a generic NMEA 0183 GPS receiver (UART).
//
// Follows the NMEA 0183 sentence format that GPS modules (u-blox, MediaTek,
// SiRF and others) emit at 9600 baud, 8N1:
//   $GPGGA,hhmmss.ss,ddmm.mmmm,N|S,dddmm.mmmm,E|W,quality,satellites,hdop,alt,M,geoid,M,,*HH
// where HH is the XOR of every character between '$' and '*', in hex.
// Not modelled: baud-rate pacing (a sentence arrives all at once), the other
// sentence types (RMC, GSA, GSV...), vendor commands sent by the host, and
// timing, so no sentence is sent unless asked.
//
// Usage in a peripherals .repl:   gps: VirtuLab.NMEAGps @ sysbus
// (VirtuLab connects it to the chosen UART with a UART hub.)
// Drive it from firmware:         vl_sim("sysbus.gps Latitude 46.2044")
//                                 vl_sim("sysbus.gps EmitFix")
// Fault injection:                HasFix false      the receiver reports no fix
//                                 CorruptChecksum   sentences carry a wrong checksum
//                                 Silent            nothing is sent (unpowered, wrong wiring)
//
using System;
using System.Globalization;
using System.Text;

using Antmicro.Renode.Core;
using Antmicro.Renode.Peripherals.UART;

namespace Antmicro.Renode.Peripherals.VirtuLab
{
    public class NMEAGps : IUART
    {
        public NMEAGps()
        {
            Reset();
        }

        public decimal Latitude { get; set; }   // degrees, negative = south
        public decimal Longitude { get; set; }  // degrees, negative = west
        public decimal Altitude { get; set; }   // metres
        public int Satellites { get; set; }
        public bool HasFix { get; set; }
        public bool CorruptChecksum { get; set; }
        public bool Silent { get; set; }

        public void EmitFix()
        {
            if(Silent)
            {
                return;
            }
            Send(BuildGga());
        }

        public void WriteChar(byte value)
        {
            // Bytes sent by the host (configuration commands) are ignored.
        }

        public void Reset()
        {
            Latitude = 0;
            Longitude = 0;
            Altitude = 0;
            Satellites = 0;
            HasFix = true;
            CorruptChecksum = false;
            Silent = false;
        }

        public uint BaudRate => 9600;
        public Bits StopBits => Bits.One;
        public Parity ParityBit => Parity.None;

        public event Action<byte> CharReceived;

        private string BuildGga()
        {
            string body;
            if(HasFix)
            {
                body = string.Format(CultureInfo.InvariantCulture,
                    "GPGGA,123519.00,{0},{1},1,{2:00},0.9,{3:0.0},M,0.0,M,,",
                    Coordinate(Latitude, 2, "N", "S"), Coordinate(Longitude, 3, "E", "W"),
                    Satellites, Altitude);
            }
            else
            {
                body = "GPGGA,123519.00,,,,,0,00,99.9,,M,,M,,";
            }
            var sum = 0;
            foreach(var c in body)
            {
                sum ^= c;
            }
            if(CorruptChecksum)
            {
                sum ^= 0x5A;
            }
            return string.Format("${0}*{1:X2}\r\n", body, sum);
        }

        // NMEA coordinates: ddmm.mmmm for latitude, dddmm.mmmm for longitude.
        private static string Coordinate(decimal degrees, int degreeDigits, string positive, string negative)
        {
            var hemisphere = degrees >= 0 ? positive : negative;
            var absolute = Math.Abs(degrees);
            var whole = (int)Math.Floor(absolute);
            var minutes = (absolute - whole) * 60m;
            var text = string.Format(CultureInfo.InvariantCulture, "{0}{1:00.0000}",
                whole.ToString(new string('0', degreeDigits), CultureInfo.InvariantCulture), minutes);
            return text + "," + hemisphere;
        }

        private void Send(string sentence)
        {
            var handler = CharReceived;
            if(handler == null)
            {
                return;
            }
            foreach(var b in Encoding.ASCII.GetBytes(sentence))
            {
                handler(b);
            }
        }
    }
}
