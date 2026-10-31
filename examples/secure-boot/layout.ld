MEMORY
{
    FLASH (rx)  : ORIGIN = 0x00000000, LENGTH = 256K
    RAM   (rwx) : ORIGIN = 0x20000000, LENGTH = 64K
}
ENTRY(reset_handler)
SECTIONS
{
    .text : { KEEP(*(.vectors)) *(.text*) *(.rodata*) } > FLASH
    .data : { _data = .; *(.data*) _edata = .; } > RAM AT > FLASH
    _data_load = LOADADDR(.data);
    .bss (NOLOAD) : { _bss = .; *(.bss*) *(COMMON) _ebss = .; } > RAM
    _stack_top = ORIGIN(RAM) + LENGTH(RAM);
}
