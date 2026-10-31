//
// VirtuLab device library: a generic AT-command cellular modem (UART).
//
// Follows the AT command interface of ITU-T V.250 and 3GPP TS 27.007 that cellular modems
// (SIMCom, Quectel, u-blox and others) share. Commands end with CR. With echo on (the power-up
// state) the modem repeats every character it receives. A reply is
//   <CR><LF>information<CR><LF>   (zero or more lines)   then   <CR><LF>OK<CR><LF>
// or <CR><LF>ERROR<CR><LF> for a command it does not know.
//   AT           -> OK                     ATE0 / ATE1  echo off / on
//   AT+CSQ       -> +CSQ: <rssi>,99        rssi 0..31 (-113 dBm + 2 dB per step), 99 = unknown
//   AT+CREG?     -> +CREG: 0,<stat>        0 not registered, 1 home, 2 searching, 3 denied, 4 unknown, 5 roaming
//   AT+CPIN?     -> +CPIN: READY, or +CPIN: SIM PIN when the SIM still needs its PIN
//   AT+CGMI      -> the manufacturer name
// Not modelled: data connections, SMS, network timing (a reply comes at once), command
// chaining with ';', S-registers, and the many vendor commands.
//
// Usage in a peripherals .repl:   modem: VirtuLab.ATModem @ sysbus
// Set the network from firmware:  vl_sim("sysbus.modem Signal 20")
//                                 vl_sim("sysbus.modem Registration 5")
// Fault injection:                Silent (no answer), Failing (every command answers ERROR)
//
using System;
using System.Text;

using Antmicro.Renode.Core;
using Antmicro.Renode.Peripherals.UART;

namespace Antmicro.Renode.Peripherals.VirtuLab
{
    public class ATModem : IUART
    {
        public ATModem()
        {
            Reset();
        }

        public int Signal { get; set; }        // +CSQ rssi, 0..31 or 99
        public int Registration { get; set; }  // +CREG stat
        public bool SimReady { get; set; }
        public bool Silent { get; set; }
        public bool Failing { get; set; }

        public void WriteChar(byte value)
        {
            if(Silent)
            {
                return;
            }
            if(echo)
            {
                Send(new[] { value });
            }
            if(value == (byte)'\r')
            {
                var command = line.ToString().Trim().ToUpperInvariant();
                line.Clear();
                if(command.Length > 0)
                {
                    Answer(command);
                }
            }
            else if(value != (byte)'\n')
            {
                line.Append((char)value);
            }
        }

        public void Reset()
        {
            line = new StringBuilder();
            echo = true;
            Signal = 20;
            Registration = 1;
            SimReady = true;
            Silent = false;
            Failing = false;
        }

        public uint BaudRate => 115200;
        public Bits StopBits => Bits.One;
        public Parity ParityBit => Parity.None;

        public event Action<byte> CharReceived;

        private void Answer(string command)
        {
            if(Failing)
            {
                Reply("ERROR");
                return;
            }
            switch(command)
            {
            case "AT":
                Reply();
                break;
            case "ATE0":
                echo = false;
                Reply();
                break;
            case "ATE1":
                echo = true;
                Reply();
                break;
            case "AT+CSQ":
                Reply("+CSQ: " + Signal + ",99");
                break;
            case "AT+CREG?":
                Reply("+CREG: 0," + Registration);
                break;
            case "AT+CPIN?":
                Reply(SimReady ? "+CPIN: READY" : "+CPIN: SIM PIN");
                break;
            case "AT+CGMI":
                Reply("VirtuLab");
                break;
            default:
                Reply("ERROR");
                break;
            }
        }

        // Information lines first, then the final result code.
        private void Reply(params string[] information)
        {
            var text = new StringBuilder();
            var final = "OK";
            foreach(var item in information)
            {
                if(item == "ERROR")
                {
                    final = "ERROR";
                }
                else
                {
                    text.Append("\r\n").Append(item).Append("\r\n");
                }
            }
            text.Append("\r\n").Append(final).Append("\r\n");
            Send(Encoding.ASCII.GetBytes(text.ToString()));
        }

        private void Send(byte[] bytes)
        {
            var handler = CharReceived;
            if(handler == null)
            {
                return;
            }
            foreach(var b in bytes)
            {
                handler(b);
            }
        }

        private StringBuilder line;
        private bool echo;
    }
}
