#!/bin/sh
# The call demo, in one browser window: VirtuLab Studio on the wearable patch.
#   sh bench/demo.sh --prepare   before the call: records every scenario, both glitch sweeps and the
#                                fault scenarios and the findings' replays (about 10 minutes), so nothing waits during the call
#   sh bench/demo.sh             opens the studio and prints the talk track here
# Fallback without the studio: sh bench/demo-terminal.sh
set -u
cd "$(dirname "$0")/.."
repo="$PWD"
ex=examples/wearable-patch
variant="plain=-DPATCH_HARDENED=0"

if [ -z "${VIRTULAB_HOME:-}" ]; then
    if [ -d "$HOME/.virtulab/tools/renode-1.17.0" ]; then VIRTULAB_HOME="$HOME/.virtulab"
    elif [ -d /tmp/vl-test/tools/renode-1.17.0 ]; then VIRTULAB_HOME=/tmp/vl-test
    else echo "No tools found. Run: python3 -m virtulab setup"; exit 1; fi
fi
export VIRTULAB_HOME
vl() { PYTHONPATH="$repo" python3 -m virtulab "$@"; }

if [ "${1:-}" = "--prepare" ]; then
    vl studio -C "$ex" --variant "$variant" --prepare
    exit $?
fi
[ -d "$ex/.virtulab/studio/sweeps" ] || { echo "Run sh bench/demo.sh --prepare first."; exit 1; }

cat <<'TALK'
VirtuLab Studio opens in its own window. Keys 1, 2, 3 switch tabs. Talk track:

 1 BOARD   "An STM32F4 with two real sensor chips on I2C: a motion sensor and a skin
           temperature sensor, each emulated from its datasheet."
           Click "Datasheet map" on a sensor: every datasheet fact, where it is in the model.
           Try it: remove the SHT31 and add it back: it plugs in. (Nothing is saved.)

 2 CODE    Amber virtulab.yml: the setup VirtuLab wrote, and the scenarios we wrote.
           Blue: the firmware (src/patch.c, the fall and fever logic). Purple: the drivers
           VirtuLab generated. Teal: VirtuLab's runtime and the sensor models.

 3 TEST    patient falls > Watch on the board: free fall, impact, ALARM lights, FALL=YES.
           damaged sensor cable > Watch: garbled readings, no false fever, FAULT warning.

           Fault scenarios > Open: "we wrote 4 scenarios; VirtuLab generated 71 more by
           breaking each sensor, one fault at a time, at the moments the inputs change."
           Point at the red box: the motion sensor stuck during the fall -> fall missed,
           and the patch still says SENSOR=OK. Click Watch on the board.
           "Your firmware passes every test you wrote. These are the ones you didn't."

           Glitch sweep: switch the build to "plain", open the sweep: line 78 is red.
           Replay on the board: one instruction skipped, no alarm. Click src/patch.c:78.
           Switch back to "as written": the glitch sweep finds nothing.

Press Ctrl+C here to stop the studio after the call.
TALK
vl studio -C "$ex" --variant "$variant" --app
