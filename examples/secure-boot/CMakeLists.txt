# A plain CMake firmware project: its own startup code, linker script and test runner.
# Nothing here comes from VirtuLab.
cmake_minimum_required(VERSION 3.16)
set(CMAKE_SYSTEM_NAME Generic)
set(CMAKE_SYSTEM_PROCESSOR arm)
set(CMAKE_C_COMPILER arm-none-eabi-gcc)
set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)
project(secure_boot C)

set(CPU -mcpu=cortex-m3 -mthumb)
add_compile_options(${CPU} -std=c99 -Wall -Wextra -Os -g -ffunction-sections)
add_link_options(${CPU} -nostartfiles --specs=nano.specs --specs=nosys.specs -T${CMAKE_SOURCE_DIR}/layout.ld -Wl,--gc-sections -Wl,--no-warn-rwx-segments)
include_directories(include)

# OFF shows what the fault sweep finds in a plain check.
option(BOOT_HARDENED "Redundant digest comparison" ON)
if(BOOT_HARDENED)
    add_compile_definitions(BOOT_HARDENED=1)
endif()

add_executable(boot_tests.elf src/startup.c src/boot.c test/test_boot.c)
add_executable(boot_probe_tampered.elf src/startup.c src/boot.c fault/probe_tampered.c)
