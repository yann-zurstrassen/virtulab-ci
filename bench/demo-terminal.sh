#!/bin/sh
# Fallback for the call demo, in the terminal: a wearable patch on a virtual STM32F4, with an accelerometer and a skin
# temperature sensor on I2C. Press Enter between steps, so you set the pace.
#   sh bench/demo.sh --prepare   before the call: records every scenario and runs both glitch
#                                sweeps (about 7 minutes), so the demo never waits on them
#   sh bench/demo.sh             the demo itself
set -u
cd "$(dirname "$0")/.."
repo="$PWD"
ex=examples/wearable-patch
saved="$ex/.virtulab/demo"
plain="--cflags=-std=c99 -Wall -Wextra -DPATCH_HARDENED=0"

if [ -z "${VIRTULAB_HOME:-}" ]; then
    if [ -d "$HOME/.virtulab/tools/renode-1.17.0" ]; then VIRTULAB_HOME="$HOME/.virtulab"
    elif [ -d /tmp/vl-test/tools/renode-1.17.0 ]; then VIRTULAB_HOME=/tmp/vl-test
    else echo "No tools found. Run: python3 -m virtulab setup"; exit 1; fi
fi
export VIRTULAB_HOME

vl() { PYTHONPATH="$repo" python3 -m virtulab "$@"; }
step() { printf '\n\033[1m── %s\033[0m\n' "$1"; }
pause() { printf '\033[2m   [Enter]\033[0m'; read -r _; }
record() {  # record one scenario and keep its pages
    vl trace -C "$ex" --case "$1" > /dev/null 2>&1 || { echo "   ❌ could not record $1"; return 1; }
    rm -rf "$saved/$1"; mkdir -p "$saved"; cp -R "$ex/.virtulab/trace" "$saved/$1"
    # `open` cannot pass #play to a file, so a one-line page does it
    echo '<script>location.replace("board.html#play")</script>' > "$saved/$1/play.html"
}
sweep() {   # run the glitch sweep and keep its result and findings
    name="$1"; shift
    rm -f "$ex/.virtulab/report.md"
    vl run -C "$ex" --only scenarios "$@" > "$saved/sweep_$name.log" 2>&1
    [ -f "$ex/.virtulab/report.md" ] || { echo "   ❌ the $name sweep did not run, see $saved/sweep_$name.log"; return 1; }
    { grep -E '^\| Physical scenarios' "$ex/.virtulab/report.md" | cut -d'|' -f4 | sed 's/^ *//'
      grep -E '^patient_falls after' "$ex/.virtulab/report.md"; } > "$saved/sweep_$name.txt"
    cp "$ex/.virtulab/scenarios/sweep.html" "$saved/sweep_$name.html"
    cp "$ex/.virtulab/scenarios/sweep.json" "$saved/sweep_$name.json"
}
replay_glitch() {  # record the fall again, with the first fatal skip of the plain sweep applied
    skip=$(python3 - "$saved/sweep_plain.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
text = {i["address"]: i["instruction"] for i in d["instructions"]}
bad = sorted((r for r in d["runs"] if r["result"] == "broken"), key=lambda r: not text[r["address"]].startswith("str"))
print("%#x@%gms" % (bad[0]["address"], bad[0]["at"]) if bad else "")
PY
)
    [ -n "$skip" ] || { echo "   the plain sweep found nothing to replay"; return 1; }
    vl trace -C "$ex" --case patient_falls "$plain" --skip "$skip" | grep '⚡'
    rm -rf "$saved/glitch_replay"; cp -R "$ex/.virtulab/trace" "$saved/glitch_replay"
    echo '<script>location.replace("board.html#play")</script>' > "$saved/glitch_replay/play.html"
}

if [ "${1:-}" = "--prepare" ]; then
    for c in daily_life patient_falls fever damaged_sensor_cable; do echo "recording $c"; record "$c"; done
    echo "glitch sweep, plain firmware (about 2 min)"; sweep plain "$plain"
    echo "the fatal glitch, replayed on the board"; replay_glitch
    echo "glitch sweep, hardened firmware (about 5 min)"; sweep hardened
    echo; cat "$saved/sweep_plain.txt"; cat "$saved/sweep_hardened.txt"
    echo "Ready. Run: sh bench/demo.sh"
    exit 0
fi
[ -f "$saved/sweep_hardened.txt" ] || { echo "Run sh bench/demo.sh --prepare first."; exit 1; }

step "0. Set up a board: pick the chip, plug in two sensors, run"
setup_dir="$(mktemp -d "${TMPDIR:-/tmp}/virtulab-new-board.XXXXXX")"
echo "   The setup page opens in your browser. On it:"
echo "     1. the board is already STM32F4: point at the chip"
echo "     2. under Protocols and sensors, click I2C, then MPU-6050, then SHT31: watch them plug in"
echo "     3. click Create project files: drivers, tests, CI and virtulab.yml are written"
echo "     4. click Run the selected tests now: about 20 s on the virtual board"
PYTHONPATH="$repo" python3 -m virtulab ui -C "$setup_dir" --port 8765 > "$setup_dir.log" 2>&1 &
ui_pid=$!
trap 'kill $ui_pid 2>/dev/null' EXIT
pause
kill $ui_pid 2>/dev/null; wait $ui_pid 2>/dev/null
echo "   Next: the same board, with the application your team writes on top of it."

step "1. The project: a wearable patch, described in one file"
echo "   Two real sensor chips, plugged on the chip's I2C bus, emulated from their datasheets:"
sed -n '/^modules:/,/^tests:/p' "$ex/virtulab.yml" | grep -v '^tests:' | sed 's/^/      /'
echo "   And the situations it must survive, each with what must and must never happen:"
sed -n '/patient_falls:/,/faults:/p' "$ex/virtulab.yml" | sed 's/^/   /'
pause

step "2. A patient falls: watch the virtual board (recorded live now, about 10 s)"
record patient_falls && open "$saved/patient_falls/play.html"
echo "   Orange dots: the firmware asks a sensor. Green: the sensor answers."
pause

step "3. A damaged sensor cable: garbled readings must not fake a fever"
[ -f "$saved/damaged_sensor_cable/play.html" ] || echo '<script>location.replace("board.html#play")</script>' > "$saved/damaged_sensor_cable/play.html"
open "$saved/damaged_sensor_cable/play.html"
pause

step "4. A glitch at the worst moment: remove one processor instruction, see what breaks"
echo "   (Recorded before the call: a sweep runs the firmware 40 to 80 times and takes a few minutes.)"
echo "   The firmware as most people would write it. The page explains one glitched run in 4 steps,"
echo "   then shows the C code next to the instructions it compiles to, and what each skip did."
open "$saved/sweep_plain.html"
sed -n '1p' "$saved/sweep_plain.txt" | sed 's/^/      ❌ /'
echo "   Point at line 78, fall = true; : skip it once and the alarm is lost forever."
pause

step "5. The same fall, with that one instruction removed: watch the alarm never come"
open "$saved/glitch_replay/play.html"
echo "   At the impact the chip flashes ⚡, the ALARM LED stays dark, and the patch reports FALL=NO."
pause

step "6. The fix: re-read the last second on every poll, so no single skip can lose a fall"
open "$saved/sweep_hardened.html"
sed 's/^/      ✅ /' "$saved/sweep_hardened.txt"
echo
echo "   Every run also writes evidence: $ex/.virtulab/evidence (JUnit, SARIF, evidence.json)"
