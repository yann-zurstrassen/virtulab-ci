# Sums gcov's per-file "Lines executed" / "Taken at least once" lines into one total.
# Input: concatenated `gcov -b` output for the files under test.
/^File '/ { in_project = ($0 !~ /\/(usr|Library|Applications|opt)\//) }
in_project && /^Lines executed:/ {
    split($0, parts, /[:% ]+/)
    lines_total += parts[5]
    lines_hit += parts[3] * parts[5] / 100
}
in_project && /^Taken at least once:/ {
    split($0, parts, /[:% ]+/)
    branch_total += parts[6]
    branch_hit += parts[4] * parts[6] / 100
}
END {
    if (lines_total == 0) { print "COVERAGE unavailable"; exit 1 }
    lp = 100 * lines_hit / lines_total
    bp = (branch_total > 0) ? 100 * branch_hit / branch_total : 0
    printf "COVERAGE lines=%.1f%% (%d/%d) branches=%.1f%% (%d/%d)\n", \
        lp, lines_hit + 0.5, lines_total, bp, branch_hit + 0.5, branch_total
}
