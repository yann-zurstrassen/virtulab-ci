#!/usr/bin/env bash
# Single-instruction-skip fault injection with QEMU + GDB.
#
# For every instruction of the functions defined in --source (or just --address),
# boot the probe image paused under QEMU's gdbstub, stop at that instruction the
# first time it is reached, move the PC past it and let the firmware finish.
# The probe fails only if a wrong PIN is granted, so FAIL means "bypass".
#
# Fails closed: a sweep that could not apply its faults is `inconclusive` (exit 2), never
# a pass. That covers no instructions found, no fault applied, and a run where a fault was
# not applied and the firmware did not finish either (gdb or QEMU did not work).
#
# Scope: instruction skip, first execution only, one fault per run. It does not
# model bit flips, multi-fault glitches, or real voltage/clock glitch behaviour.
set -euo pipefail

usage() {
    echo "usage: $0 --elf FILE --board NAME --source FILE [--address 0xADDR] [--functions a,b] [--timeout SECONDS] [--verbose]" >&2
    exit 2
}

elf="" board="" source_file="" only_address="" only_functions="" timeout_s=10 verbose=no
while [ $# -gt 0 ]; do
    if [ "$1" = "--verbose" ]; then verbose=yes; shift; continue; fi
    [ $# -ge 2 ] || usage
    case "$1" in
        --elf) elf="$2" ;;
        --board) board="$2" ;;
        --source) source_file="$2" ;;
        --address) only_address="$2" ;;
        --functions) only_functions=",$2," ;;
        --timeout) timeout_s="$2" ;;
        *) usage ;;
    esac
    shift 2
done
[ -n "$elf" ] && [ -n "$board" ] && [ -n "$source_file" ] || usage

qemu="${QEMU:-qemu-system-arm}"
gdb="${GDB:-}"
if [ -z "$gdb" ]; then
    for candidate in arm-none-eabi-gdb gdb-multiarch; do
        if command -v "$candidate" > /dev/null; then gdb="$candidate"; break; fi
    done
fi
[ -n "$gdb" ] || { echo "fault_inject: no arm-capable gdb found (set GDB=...)" >&2; exit 2; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# Runs "$@" in the background and kills it after $timeout_s seconds. stdin is
# detached so children cannot swallow the instruction list read by the sweep loop.
run_bounded() {
    "$@" < /dev/null &
    local pid=$!
    ( sleep "$timeout_s"; kill "$pid" 2> /dev/null ) &
    local watchdog=$!
    wait "$pid" 2> /dev/null || true
    kill "$watchdog" 2> /dev/null || true
    wait "$watchdog" 2> /dev/null || true
}

qemu_args() {
    echo "-M $board -nographic -monitor none -semihosting-config enable=on,target=native -kernel $elf"
}

classify() {
    local out="$1"
    if grep -q 'auth bypass' "$out"; then echo "BYPASS"
    elif grep -q ':PASS' "$out"; then echo "denied"
    elif grep -q 'VIRTULAB_FAULT' "$out"; then echo "crash"
    else echo "hang"
    fi
}

run_original() {
    # shellcheck disable=SC2046
    run_bounded "$qemu" $(qemu_args) > "$work/original.out" 2>&1  # semihosting console output can be on stderr
    classify "$work/original.out"
}

# Waits up to $2 seconds for process $1 to exit on its own, then kills it. QEMU
# exits by itself when the firmware does; killing it earlier loses its buffered output.
wait_or_kill() {
    local pid="$1" ticks=$(($2 * 10))
    while kill -0 "$pid" 2> /dev/null && [ "$ticks" -gt 0 ]; do
        sleep 0.1
        ticks=$((ticks - 1))
    done
    kill "$pid" 2> /dev/null || true
    wait "$pid" 2> /dev/null || true
}

# Prints "<result> <applied>" for a skip at $1 that resumes at $2. If the breakpoint is
# never reached, the first `continue` runs to exit and gdb aborts the script at `set $pc`.
# Straight-line commands, not a breakpoint `commands` block: gdb would end the batch
# (and kill the target) before the firmware finished.
# The operating system picks a free port for each run, so two sweeps on one machine cannot
# collide. QEMU needs a moment before it listens; a refused connection costs nothing, so retry.
# If it never connects, the run ends as a hang and the sweep fails.
free_port() {
    python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])'
}

run_faulted() {
    local at="$1" resume="$2" port tries=0
    port="$(free_port)"
    cat > "$work/gdb.cmd" <<EOF
set pagination off
set confirm off
target remote 127.0.0.1:$port
break *$at
continue
set \$pc = $resume
printf "FAULT_APPLIED\\n"
continue
EOF
    # shellcheck disable=SC2046
    "$qemu" $(qemu_args) -S -gdb "tcp:127.0.0.1:$port" < /dev/null > "$work/faulted.out" 2>&1 &
    local qemu_pid=$!
    while :; do
        run_bounded "$gdb" -batch -nx "$elf" -x "$work/gdb.cmd" > "$work/gdb.out" 2>&1
        if grep -q 'Connection refused' "$work/gdb.out" && [ "$tries" -lt 50 ]; then
            tries=$((tries + 1)); sleep 0.1; continue
        fi
        break
    done
    wait_or_kill "$qemu_pid" 3
    local applied=no
    grep -q FAULT_APPLIED "$work/gdb.out" && applied=yes
    echo "$(classify "$work/faulted.out") $applied"
}

# One line per instruction: "<address> <size> <function> <offset> <text>".
list_instructions() {
    arm-none-eabi-nm -l -S --defined-only "$elf" | awk -F'\t' -v src="/$source_file:" '
        index($2, src) { split($1, f, " "); if (f[3] ~ /^[Tt]$/) print f[1], f[2], f[4] }' |
    while read -r start size name; do
        stop=$(printf '0x%x' $((0x$start + 0x$size)))
        arm-none-eabi-objdump -d --start-address="0x$start" --stop-address="$stop" "$elf" |
            awk -v name="$name" -v base="$((0x$start))" '
                /^[ ]+[0-9a-f]+:\t/ {
                    split($0, parts, "\t")
                    addr = strtonum_hex($1); raw = parts[2]; gsub(/ /, "", raw)
                    text = parts[3]; if (text ~ /^\.(word|short|byte)/) next
                    if (parts[4] != "") text = text " " parts[4]
                    sub(/ +@.*$/, "", text)
                    printf "%x %d %s 0x%x %s\n", addr, length(raw) / 2, name, addr - base, text
                }
                function strtonum_hex(s,   i, c, v, digits) {
                    sub(/:$/, "", s); v = 0; digits = "0123456789abcdef"
                    for (i = 1; i <= length(s); i++) { c = index(digits, substr(s, i, 1)) - 1; v = v * 16 + c }
                    return v
                }'
    done
}

original="$(run_original)"
echo "== Fault injection: single instruction skip =="
echo "image: $elf  board: $board  gdb: $gdb"
echo "original run (no fault): $original"
[ "$original" = "denied" ] || { echo "VERDICT: baseline run is not clean ($original); refusing to inject" ; exit 2; }
inconclusive() {
    echo "VERDICT: inconclusive, $1"
    echo "FAULT status=inconclusive swept=${applied_count:-0} bypass=${bypass:-0} crashed=${crashed:-0}"
    exit 2
}
list_instructions > "$work/instructions" || inconclusive "the instructions of $source_file could not be listed"
[ -s "$work/instructions" ] || inconclusive "no instructions found for $source_file (does the path match the build?)"
printf '%-12s %-26s %-28s %-9s %s\n' "tampered" "function+offset" "instruction" "original" "faulted"

swept=0 applied_count=0 bypass=0 denied=0 crashed=0 not_reached=0
while read -r addr size name offset text; do
    if [ -n "$only_address" ] && [ "$((0x$addr))" -ne "$((only_address))" ]; then continue; fi
    if [ -n "$only_functions" ] && [[ "$only_functions" != *",$name,"* ]]; then continue; fi
    resume=$(printf '0x%x' $((0x$addr + size)))
    read -r result applied <<< "$(run_faulted "0x$addr" "$resume")"
    swept=$((swept + 1))
    if [ "$verbose" = yes ]; then printf 'sweep 0x%s %s+%s applied=%s result=%s\n' "$addr" "$name" "$offset" "$applied" "$result"; fi
    if [ "$applied" = no ]; then
        # A firmware that ran to the end never reached this instruction. Anything else is a broken run.
        [ "$result" = denied ] || inconclusive "no fault applied at 0x$addr and the firmware did not finish ($result)"
        not_reached=$((not_reached + 1)); continue
    fi
    applied_count=$((applied_count + 1))
    case "$result" in
        BYPASS) bypass=$((bypass + 1))
                printf '0x%08x   %-26s %-28s %-9s %s\n' "0x$addr" "$name+$offset" "$text" "$original" "BYPASS (property broken)" ;;
        denied) denied=$((denied + 1)) ;;
        *) crashed=$((crashed + 1)) ;;
    esac
done < "$work/instructions"

echo "swept=$swept applied=$applied_count not_reached=$not_reached denied=$denied crashed_or_hung=$crashed bypass=$bypass"
[ "$applied_count" -gt 0 ] || inconclusive "no instruction of $source_file was reached by the probe"
if [ "$bypass" -gt 0 ]; then
    verdict="auth bypass reachable by single instruction skip"
    status=bypass
else
    verdict="no auth bypass found by single instruction skip ($applied_count instructions tried, first execution only)"
    status=survived
fi
echo "VERDICT: $verdict"
echo "FAULT status=$status swept=$applied_count bypass=$bypass crashed=$crashed"
[ "$bypass" -eq 0 ]
