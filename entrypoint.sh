#!/bin/bash
set -eo pipefail

# Configuration with fallback defaults
BOARD="${1:-lm3s6965evb}"
TIMEOUT="${2:-30s}"
SOURCE_FILE="${3:-main.c}"
LINKER_SCRIPT="${4:-layout.ld}"
OUTPUT_ELF="firmware.elf"
LOG_FILE="qemu_output.log"

echo "========================================="
echo "🚀 VirtuLab CI — Embedded Test Runner"
echo "========================================="
echo "Target Board:  ${BOARD}"
echo "Source File:   ${SOURCE_FILE}"
echo "Linker Script: ${LINKER_SCRIPT}"
echo "Timeout:       ${TIMEOUT}"
echo "-----------------------------------------"

# 1. Verify Inputs
if [ ! -f "$SOURCE_FILE" ]; then
    echo "❌ Error: Source file '$SOURCE_FILE' not found!"
    exit 1
fi

if [ ! -f "$LINKER_SCRIPT" ]; then
    echo "❌ Error: Linker script '$LINKER_SCRIPT' not found!"
    exit 1
fi

# 2. Compilation
echo "🔨 Compiling firmware..."
arm-none-eabi-gcc -mcpu=cortex-m3 -mthumb -T "$LINKER_SCRIPT" --specs=nosys.specs "$SOURCE_FILE" -o "$OUTPUT_ELF"
echo "✅ Compilation successful."

# 3. Memory Footprint Analysis
echo "-----------------------------------------"
echo "📊 Binary Memory Footprint:"
arm-none-eabi-size "$OUTPUT_ELF"

# Calculate Flash (Text + Data) and RAM (Data + BSS)
SIZE_LINE=$(arm-none-eabi-size "$OUTPUT_ELF" | tail -n 1)
TEXT=$(echo "$SIZE_LINE" | awk '{print $1}')
DATA=$(echo "$SIZE_LINE" | awk '{print $2}')
BSS=$(echo "$SIZE_LINE" | awk '{print $3}')

FLASH_BYTES=$((TEXT + DATA))
RAM_BYTES=$((DATA + BSS))

echo "   Flash (ROM): ${FLASH_BYTES} bytes"
echo "   RAM:         ${RAM_BYTES} bytes"

# Write to GitHub Actions Step Outputs if running in GHA
if [ -n "$GITHUB_OUTPUT" ]; then
    echo "flash_bytes=${FLASH_BYTES}" >> "$GITHUB_OUTPUT"
    echo "ram_bytes=${RAM_BYTES}" >> "$GITHUB_OUTPUT"
fi

# 4. QEMU Execution
echo "-----------------------------------------"
echo "⚡ Executing in QEMU (${BOARD})..."

# Run QEMU with timeout and capture output
set +e
timeout "${TIMEOUT}" qemu-system-arm \
    -M "${BOARD}" \
    -nographic \
    -kernel "$OUTPUT_ELF" \
    -semihosting-config enable=on,target=native > "$LOG_FILE" 2>&1
QEMU_EXIT_CODE=$?
set -e

# Display Logs (Filter out standard QEMU timer warning)
grep -v "Timer with period zero" "$LOG_FILE" || true

# 5. Evaluate Execution Result
echo "-----------------------------------------"
if [ $QEMU_EXIT_CODE -eq 0 ]; then
    echo "✅ Test Passed: Firmware executed and exited cleanly."
elif [ $QEMU_EXIT_CODE -eq 124 ]; then
    echo "❌ Test Failed: Execution timed out after ${TIMEOUT}!"
    exit 124
else
    echo "❌ Test Failed: QEMU exited with code ${QEMU_EXIT_CODE}."
    exit $QEMU_EXIT_CODE
fi

echo "========================================="
