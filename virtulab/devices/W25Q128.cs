//
// VirtuLab device library: Winbond W25Q128 16 MiB SPI NOR flash (SPI).
//
// Written from the W25Q128 datasheet, standard SPI instructions:
//   0x9F  JEDEC ID           -> 0xEF 0x40 0x18 (manufacturer, memory type, capacity)
//   0x05  Read status 1      -> bit 0 BUSY (a program or erase is running), bit 1 WEL (write enable latch)
//   0x06  Write enable       sets WEL; 0x04 Write disable clears it
//   0x03  Read data          24-bit address, then data; the address increments, wrapping at 16 MiB
//   0x02  Page program       24-bit address, then up to 256 bytes; the address wraps inside the page.
//                            Programming can only change bits from 1 to 0 (the stored byte is ANDed)
//   0x20  Sector erase (4 KiB), 0xD8 block erase (64 KiB), 0xC7 / 0x60 chip erase: set bytes to 0xFF
// Program and erase instructions are ignored unless WEL is set, run when chip select goes high,
// and clear WEL. While BUSY is set every instruction except "read status" is ignored.
// An erased chip reads 0xFF; the contents survive a reset.
// Not modelled: real program and erase times (set BusyPolls to hold BUSY for that many status reads),
// the other status and security registers, fast-read, dual and quad modes, suspend, power-down, and the write-protect pin.
//
// Usage in a peripherals .repl:   storage: VirtuLab.W25Q128 @ spi1_mux 2
// Make erases take time:          vl_sim("sysbus.spi1.spi1_mux.storage BusyPolls 5")
//
using System;

using Antmicro.Renode.Logging;
using Antmicro.Renode.Peripherals.SPI;

namespace Antmicro.Renode.Peripherals.VirtuLab
{
    public class W25Q128 : ISPIPeripheral
    {
        public W25Q128()
        {
            for(var i = 0; i < memory.Length; i++)
            {
                memory[i] = 0xFF;
            }
            Reset();
            BusyPolls = 0;
            Responding = true;
        }

        // How many status reads report BUSY after each program or erase.
        public int BusyPolls { get; set; }

        // False = the chip is not connected: the line stays high and every byte reads 0xFF.
        public bool Responding { get; set; }

        public byte Transmit(byte data)
        {
            if(!Responding)
            {
                return 0xFF;
            }
            var index = count++;
            if(index == 0)
            {
                command = data;
                return 0xFF;
            }
            if(busy > 0 && command != ReadStatus)
            {
                return 0xFF;  // the chip ignores everything but "read status" while it works
            }
            switch(command)
            {
            case ReadJedecId:
                return index <= 3 ? JedecId[index - 1] : (byte)0xFF;
            case ReadStatus:
                return (byte)((busy > 0 ? 0x01 : 0x00) | (writeEnabled ? 0x02 : 0x00));
            case ReadData:
                if(index <= 3)
                {
                    address = (address << 8) | data;
                    if(index == 3)
                    {
                        address &= Mask;
                    }
                    return 0xFF;
                }
                var value = memory[address];
                address = (address + 1) & Mask;
                return value;
            case PageProgram:
                if(index <= 3)
                {
                    address = (address << 8) | data;
                }
                else if(programmed < 256)
                {
                    pending[programmed++] = data;
                }
                return 0xFF;
            case SectorErase:
            case BlockErase:
                if(index <= 3)
                {
                    address = (address << 8) | data;
                }
                return 0xFF;
            default:
                return 0xFF;
            }
        }

        public void FinishTransmission()
        {
            if(Responding && count > 0)
            {
                Execute();
            }
            count = 0;
            address = 0;
            programmed = 0;
        }

        public void Reset()
        {
            count = 0;
            address = 0;
            programmed = 0;
            writeEnabled = false;
            busy = 0;
        }

        private void Execute()
        {
            if(command == ReadStatus)
            {
                if(busy > 0)
                {
                    busy--;
                }
                return;
            }
            if(busy > 0)
            {
                return;
            }
            switch(command)
            {
            case WriteEnable:
                writeEnabled = true;
                break;
            case WriteDisable:
                writeEnabled = false;
                break;
            case PageProgram:
                if(count < 4)
                {
                    break;
                }
                if(Require("Page program"))
                {
                    var page = (address & Mask) & ~0xFFu;
                    var offset = address & 0xFFu;
                    for(var i = 0; i < programmed; i++)
                    {
                        memory[page + ((offset + i) & 0xFF)] &= pending[i];
                    }
                    Finish();
                }
                break;
            case SectorErase:
                if(count == 4 && Require("Sector erase"))
                {
                    EraseRange(address & ~0xFFFu, 0x1000);
                }
                break;
            case BlockErase:
                if(count == 4 && Require("Block erase"))
                {
                    EraseRange(address & ~0xFFFFu, 0x10000);
                }
                break;
            case ChipErase:
            case ChipEraseAlternate:
                if(count == 1 && Require("Chip erase"))
                {
                    EraseRange(0, memory.Length);
                }
                break;
            }
        }

        private bool Require(string what)
        {
            if(!writeEnabled)
            {
                this.Log(LogLevel.Warning, "{0} ignored: write enable was not sent first", what);
            }
            return writeEnabled;
        }

        private void EraseRange(uint start, int length)
        {
            for(var i = 0; i < length; i++)
            {
                memory[(start + (uint)i) & Mask] = 0xFF;
            }
            Finish();
        }

        private void Finish()
        {
            writeEnabled = false;
            busy = BusyPolls;
        }

        private byte command;
        private int count;
        private uint address;
        private int programmed;
        private bool writeEnabled;
        private int busy;
        private readonly byte[] pending = new byte[256];
        private readonly byte[] memory = new byte[16 * 1024 * 1024];

        private static readonly byte[] JedecId = { 0xEF, 0x40, 0x18 };

        private const uint Mask = 0xFFFFFF;
        private const byte WriteEnable = 0x06;
        private const byte WriteDisable = 0x04;
        private const byte ReadStatus = 0x05;
        private const byte ReadData = 0x03;
        private const byte PageProgram = 0x02;
        private const byte SectorErase = 0x20;
        private const byte BlockErase = 0xD8;
        private const byte ChipErase = 0xC7;
        private const byte ChipEraseAlternate = 0x60;
        private const byte ReadJedecId = 0x9F;
    }
}
