#!/bin/sh
# Runs VirtuLab with ONLY the tools `virtulab setup` installed: Homebrew and other system tools
# are hidden from PATH, so a pass proves the downloaded compiler, GDB, QEMU and Renode work.
#   sh bench/check-native-tools.sh [VIRTULAB_HOME]      (default: /tmp/vl-test)
set -u
cd "$(dirname "$0")/.."
home="${1:-/tmp/vl-test}"
py="$(python3 -c 'import sys; print(sys.executable)')"

vl() {
    env -i HOME="$HOME" VIRTULAB_HOME="$home" PATH=/usr/bin:/bin PYTHONPATH="$PWD" "$py" -m virtulab "$@"
}

rm -rf /tmp/vlq examples/oven-controller/.virtulab
echo "== tools in use"
vl doctor
echo "== QEMU: unit tests and fault injection on a new project"
vl init -C /tmp/vlq -b lm3s6965evb -t unit,fault --template starter --ci none -y > /dev/null && vl run -C /tmp/vlq | grep -E '^(✅|❌) '
echo "== Renode: the oven example, unit tests and scenarios"
start=$(date +%s)
vl run -C examples/oven-controller --only unit,scenarios | grep -E '^(✅|❌) '
echo "   took $(( $(date +%s) - start )) s"
echo "== Why each scenario ended as it did (kept in examples/oven-controller/.virtulab)"
for run in examples/oven-controller/.virtulab/scenarios/runs/*/plain; do
    [ -d "$run" ] || continue
    printf '   %s: ' "$(basename "$(dirname "$run")")"
    tr -d '\r' < "$run/uart.log" 2>/dev/null | grep -E 'HEATER|VIRTULAB_EXIT' | tr '\n' ' '
    grep -aE 'error|Error|Exception' "$run/renode.log" 2>/dev/null | head -1 | cut -c1-120
    echo
done
echo "== Trace with the downloaded register file"
start=$(date +%s)
vl trace -C examples/oven-controller | tail -2
echo "   took $(( $(date +%s) - start )) s"
log=examples/oven-controller/.virtulab/trace/run/renode.log
[ -f "$log" ] && { echo "   renode.log: $(wc -c < "$log") bytes, $(grep -c 'cpu: 0x' "$log") access lines"; grep -aE 'error|Exception' "$log" | head -3 | cut -c1-140; grep -a 'cpu: 0x' "$log" | head -2 | cut -c1-140; }
rm -rf /tmp/vlq
