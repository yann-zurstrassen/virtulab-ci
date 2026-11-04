//
// VirtuLab device library: a generic Modbus RTU temperature and humidity transmitter (UART).
//
// Follows the Modbus Application Protocol and the Modbus over serial line (RTU) specification.
// A request frame is   address, function, data..., CRC-16 (low byte first).
// CRC-16/MODBUS: polynomial 0xA001 (reflected), initial value 0xFFFF.
//   function 0x03 read holding registers, 0x04 read input registers: start, count (16-bit each)
//            -> address, function, byte count, register values (16-bit, high byte first), CRC
//   function 0x06 write single holding register: address, value -> the request is echoed back
//   any other function -> exception: address, function + 0x80, code 01, CRC
//   exception 02 illegal data address, 03 illegal data value (count 0 or above 125)
// A frame with a wrong CRC, or for another slave address, is silently ignored.
// Register layout of this model (a typical RS-485 sensor, not a specific product):
//   input   0  humidity in 0.1 % RH (unsigned)      input 1  temperature in 0.1 degrees C (signed)
//   holding 0  slave address (1..247)               holding 1  baud-rate code (stored only)
// Not modelled: the 3.5-character silence that really separates frames. This model takes every
// eight received bytes as one request (the length of the functions it supports), so a request
// of another length would put it out of step. Also not modelled: broadcast writes, functions
// 0x10 and 0x17, timing and the diagnostic counters.
//
// Usage in a peripherals .repl:   sensor: VirtuLab.ModbusRtuSlave @ sysbus
// Set the air from firmware:      vl_sim("sysbus.sensor Temperature 23.5")
// Fault injection:                Silent (no answer), CorruptCrc (answers carry a wrong CRC)
//
using System;
using System.Collections.Generic;

using Antmicro.Renode.Core;
using Antmicro.Renode.Peripherals.UART;

namespace Antmicro.Renode.Peripherals.VirtuLab
{
    public class ModbusRtuSlave : IUART
    {
        public ModbusRtuSlave()
        {
            Reset();
        }

        public decimal Temperature { get; set; }  // degrees C
        public decimal Humidity { get; set; }     // % relative humidity
        public int SlaveAddress { get; set; }
        public bool Silent { get; set; }
        public bool CorruptCrc { get; set; }

        public void WriteChar(byte value)
        {
            if(Silent)
            {
                return;
            }
            request.Add(value);
            if(request.Count < RequestLength)
            {
                return;
            }
            var frame = request.ToArray();
            request.Clear();
            Handle(frame);
        }

        public void Reset()
        {
            request = new List<byte>();
            Temperature = 25;
            Humidity = 50;
            SlaveAddress = 1;
            Silent = false;
            CorruptCrc = false;
            baudCode = 0;
        }

        public uint BaudRate => 9600;
        public Bits StopBits => Bits.One;
        public Parity ParityBit => Parity.None;

        public event Action<byte> CharReceived;

        private void Handle(byte[] frame)
        {
            if(frame[0] != SlaveAddress)
            {
                return;
            }
            var crc = Crc16(frame, RequestLength - 2);
            if(frame[RequestLength - 2] != (crc & 0xFF) || frame[RequestLength - 1] != (crc >> 8))
            {
                return;
            }
            var function = frame[1];
            var start = (frame[2] << 8) | frame[3];
            var value = (frame[4] << 8) | frame[5];
            switch(function)
            {
            case 0x03:
            case 0x04:
                ReadRegisters(function, start, value);
                break;
            case 0x06:
                WriteHolding(frame, start, value);
                break;
            default:
                Exception(function, 0x01);
                break;
            }
        }

        private void ReadRegisters(byte function, int start, int count)
        {
            if(count < 1 || count > 125)
            {
                Exception(function, 0x03);
                return;
            }
            var size = function == 0x03 ? HoldingRegisters : 2;
            if(start + count > size)
            {
                Exception(function, 0x02);
                return;
            }
            var data = new List<byte> { (byte)SlaveAddress, function, (byte)(count * 2) };
            for(var i = 0; i < count; i++)
            {
                var register = function == 0x03 ? HoldingRegister(start + i) : InputRegister(start + i);
                data.Add((byte)(register >> 8));
                data.Add((byte)(register & 0xFF));
            }
            Send(data);
        }

        private void WriteHolding(byte[] frame, int register, int value)
        {
            if(register >= HoldingRegisters)
            {
                Exception(0x06, 0x02);
                return;
            }
            if(register == 0 && (value < 1 || value > 247))
            {
                Exception(0x06, 0x03);
                return;
            }
            if(register == 1)
            {
                baudCode = value;
            }
            var echo = new List<byte>(frame);
            echo.RemoveRange(echo.Count - 2, 2);
            Send(echo);
            if(register == 0)
            {
                SlaveAddress = value;  // takes effect after the answer
            }
        }

        private ushort HoldingRegister(int index)
        {
            return (ushort)(index == 0 ? SlaveAddress : baudCode);
        }

        private ushort InputRegister(int index)
        {
            if(index == 0)
            {
                return (ushort)Math.Max(0, Math.Min(0xFFFF, (int)Math.Round(Humidity * 10, MidpointRounding.AwayFromZero)));
            }
            return (ushort)(short)Math.Max(short.MinValue, Math.Min(short.MaxValue, (int)Math.Round(Temperature * 10, MidpointRounding.AwayFromZero)));
        }

        private void Exception(byte function, byte code)
        {
            Send(new List<byte> { (byte)SlaveAddress, (byte)(function | 0x80), code });
        }

        private void Send(List<byte> frame)
        {
            var crc = Crc16(frame.ToArray(), frame.Count);
            if(CorruptCrc)
            {
                crc ^= 0xFFFF;
            }
            frame.Add((byte)(crc & 0xFF));
            frame.Add((byte)(crc >> 8));
            var handler = CharReceived;
            if(handler == null)
            {
                return;
            }
            foreach(var b in frame)
            {
                handler(b);
            }
        }

        private static int Crc16(byte[] data, int length)
        {
            var crc = 0xFFFF;
            for(var i = 0; i < length; i++)
            {
                crc ^= data[i];
                for(var bit = 0; bit < 8; bit++)
                {
                    crc = (crc & 1) != 0 ? (crc >> 1) ^ 0xA001 : crc >> 1;
                }
            }
            return crc;
        }

        private List<byte> request;
        private int baudCode;

        private const int RequestLength = 8;
        private const int HoldingRegisters = 2;
    }
}
