#!/bin/sh
# Run Sensirion's SHT3x driver, unchanged, on a virtual board through VirtuLab.
#   ./run.sh            run the tests
#   ./run.sh --help     the options of `virtulab run`
# Needs Python 3 and either Renode plus the Arm toolchain, or Docker (used automatically).
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)

# The vendor's files must be exactly what Sensirion published.
(cd "$HERE/vendor/sensirion" && shasum -a 256 -c SHA256SUMS --quiet) && echo "✅ Sensirion's driver is unmodified"

export PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}"
if ! command -v renode >/dev/null 2>&1; then
    # No local emulator: VirtuLab runs the tests in its Docker image. Build it from this checkout so
    # the image holds the same VirtuLab (and the same sensor models) as the code next to this file.
    export VIRTULAB_IMAGE="${VIRTULAB_IMAGE:-virtulab-ci:mvp}"
    echo "🐳 Building $VIRTULAB_IMAGE (quick when cached)"
    docker build -q -t "$VIRTULAB_IMAGE" "$REPO" >/dev/null
fi
exec python3 -m virtulab run -C "$HERE" "$@"
