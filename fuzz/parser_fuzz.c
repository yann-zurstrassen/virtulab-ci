/*
 * Host-side fuzzing of parser_parse(). This runs the parser LOGIC natively on the
 * build machine; it is not full-system fuzzing of the firmware image, and it does
 * not model the target's memory map, interrupts or peripherals.
 *
 * The mutation loop is deterministic for a given --seed (up to the time budget),
 * so a crash found in CI reproduces on a laptop. AFL++/libFuzzer were not
 * available when this was written; parser_fuzz_one() has the right shape to be
 * wrapped as LLVMFuzzerTestOneInput() later.
 *
 * A run fails when an input
 *   - writes past parser_frame_t (detected with a guard canary after the frame),
 *   - is accepted but does not re-encode to the same bytes (round-trip property),
 *   - trips AddressSanitizer or UBSan (the input is saved from a death callback).
 */
#include <dirent.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include "parser.h"

#define FUZZ_MAX_INPUT 64u
#define FUZZ_GUARD_BYTES 16u
#define FUZZ_GUARD_FILL 0xCDu
#define FUZZ_TIME_CHECK_MASK 0xFFu
#define FUZZ_PATH_MAX 512u
#define FUZZ_CRASH_SUFFIX ".crash"

typedef enum {
    FUZZ_OK = 0,
    FUZZ_GUARD_OVERWRITTEN,
    FUZZ_ROUNDTRIP_MISMATCH
} fuzz_result_t;

typedef struct {
    uint8_t data[FUZZ_MAX_INPUT];
    size_t len;
} fuzz_input_t;

typedef struct {
    unsigned seconds;
    uint32_t seed;
    const char *crash_dir;
    const char *replay_file;
} fuzz_options_t;

/* The guard sits right behind the frame, so an overflow of payload[] lands in it. */
static struct {
    parser_frame_t frame;
    uint8_t guard[FUZZ_GUARD_BYTES];
} sandbox;

static fuzz_input_t current_input;
static const char *current_crash_dir = "fuzz/crashes";

extern void __sanitizer_set_death_callback(void (*callback)(void)) __attribute__((weak));

static uint32_t fuzz_hash(const fuzz_input_t *in)
{
    uint32_t hash = 2166136261u;

    for (size_t i = 0; i < in->len; i++) {
        hash = (hash ^ in->data[i]) * 16777619u;
    }
    return hash;
}

static uint32_t fuzz_next(uint32_t *state)
{
    uint32_t x = *state;

    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    *state = x;
    return x;
}

static uint32_t fuzz_below(uint32_t *state, uint32_t bound)
{
    return fuzz_next(state) % bound;
}

static fuzz_result_t fuzz_check_roundtrip(const fuzz_input_t *in)
{
    uint8_t again[PARSER_MAX_FRAME];
    size_t again_len = 0;

    if (parser_encode(sandbox.frame.payload, sandbox.frame.length, again, sizeof(again),
                      &again_len) != PARSER_OK) {
        return FUZZ_ROUNDTRIP_MISMATCH;
    }
    if (again_len > in->len || memcmp(again, in->data, again_len) != 0) {
        return FUZZ_ROUNDTRIP_MISMATCH;
    }
    return FUZZ_OK;
}

static fuzz_result_t parser_fuzz_one(const fuzz_input_t *in)
{
    memset(&sandbox.frame, 0, sizeof(sandbox.frame));
    memset(sandbox.guard, FUZZ_GUARD_FILL, sizeof(sandbox.guard));

    parser_status_t status = parser_parse(in->data, in->len, &sandbox.frame);

    for (size_t i = 0; i < sizeof(sandbox.guard); i++) {
        if (sandbox.guard[i] != FUZZ_GUARD_FILL) {
            return FUZZ_GUARD_OVERWRITTEN;
        }
    }
    return (status == PARSER_OK) ? fuzz_check_roundtrip(in) : FUZZ_OK;
}

static const char *fuzz_result_name(fuzz_result_t result)
{
    return (result == FUZZ_GUARD_OVERWRITTEN) ? "write past parser_frame_t"
                                              : "accepted frame does not re-encode";
}

static int fuzz_save(const char *dir, const char *kind, const fuzz_input_t *in)
{
    char path[FUZZ_PATH_MAX];

    (void)snprintf(path, sizeof(path), "%s/parser-%s-%08x" FUZZ_CRASH_SUFFIX, dir, kind,
                   (unsigned)fuzz_hash(in));
    int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd < 0) {
        return -1;
    }
    ssize_t written = write(fd, in->data, in->len);
    (void)close(fd);
    if (written != (ssize_t)in->len) {
        return -1;
    }
    (void)fprintf(stderr, "fuzz: saved %s (%zu bytes)\n", path, in->len);
    return 0;
}

/* Runs in the dying process after the sanitizer report, so the failing input is not lost. */
static void fuzz_on_sanitizer_death(void)
{
    (void)fuzz_save(current_crash_dir, "sanitizer", &current_input);
}

static void fuzz_print_hex(const fuzz_input_t *in)
{
    (void)printf("fuzz: input (%zu bytes):", in->len);
    for (size_t i = 0; i < in->len; i++) {
        (void)printf(" %02X", in->data[i]);
    }
    (void)printf("\n");
}

/* Shrink to the shortest input that still fails, so the committed file is readable. */
static void fuzz_minimize(fuzz_input_t *in, fuzz_result_t kind)
{
    while (in->len > 0) {
        fuzz_input_t shorter = *in;
        shorter.len--;
        if (parser_fuzz_one(&shorter) != kind) {
            break;
        }
        *in = shorter;
    }
    for (size_t i = 0; i < in->len; i++) {
        fuzz_input_t simpler = *in;
        simpler.data[i] = 0;
        if (parser_fuzz_one(&simpler) == kind) {
            *in = simpler;
        }
    }
}

static void fuzz_set_length_byte(fuzz_input_t *in, uint32_t *rng)
{
    static const uint8_t interesting[] = {0x00u, 0x01u, 0x1Fu, 0x20u, 0x21u, 0x22u, 0x7Fu, 0xFFu};

    if (in->len > 1) {
        in->data[1] = interesting[fuzz_below(rng, sizeof(interesting))];
    }
}

static void fuzz_extend(fuzz_input_t *in, uint32_t *rng)
{
    uint32_t extra = 1u + fuzz_below(rng, 8u);

    for (uint32_t i = 0; i < extra && in->len < FUZZ_MAX_INPUT; i++) {
        in->data[in->len++] = (uint8_t)fuzz_next(rng);
    }
}

static void fuzz_mutate_once(fuzz_input_t *in, uint32_t *rng)
{
    if (in->len == 0) {
        fuzz_extend(in, rng);
        return;
    }
    size_t pos = fuzz_below(rng, (uint32_t)in->len);

    switch (fuzz_below(rng, 6u)) {
    case 0: in->data[pos] ^= (uint8_t)(1u << fuzz_below(rng, 8u)); break;
    case 1: in->data[pos] = (uint8_t)fuzz_next(rng); break;
    case 2: fuzz_set_length_byte(in, rng); break;
    case 3: in->len = 1u + (size_t)fuzz_below(rng, (uint32_t)in->len); break;
    case 4: fuzz_extend(in, rng); break;
    default: in->data[pos] = (uint8_t)(in->data[pos] + 1u); break;
    }
}

static void fuzz_load_seed(fuzz_input_t *in, uint32_t index)
{
    static const size_t payload_sizes[] = {0u, 1u, 3u, 16u, PARSER_MAX_PAYLOAD};
    uint8_t payload[PARSER_MAX_PAYLOAD];
    size_t size = payload_sizes[index % (sizeof(payload_sizes) / sizeof(payload_sizes[0]))];

    for (size_t i = 0; i < sizeof(payload); i++) {
        payload[i] = (uint8_t)(0x10u + i);
    }
    (void)parser_encode(payload, size, in->data, sizeof(in->data), &in->len);
}

static int fuzz_report_crash(fuzz_input_t *in, fuzz_result_t kind, const char *dir)
{
    (void)printf("fuzz: CRASH: %s\n", fuzz_result_name(kind));
    fuzz_minimize(in, kind);
    fuzz_print_hex(in);
    (void)fuzz_save(dir, (kind == FUZZ_GUARD_OVERWRITTEN) ? "overflow" : "roundtrip", in);
    return 1;
}

static int fuzz_has_suffix(const char *name, const char *suffix)
{
    size_t name_len = strlen(name);
    size_t suffix_len = strlen(suffix);

    return name_len >= suffix_len && strcmp(name + name_len - suffix_len, suffix) == 0;
}

static int fuzz_replay_file(const char *path)
{
    fuzz_input_t in;
    FILE *file = fopen(path, "rb");

    if (file == NULL) {
        (void)fprintf(stderr, "fuzz: cannot open %s\n", path);
        return 0;
    }
    in.len = fread(in.data, 1u, sizeof(in.data), file);
    (void)fclose(file);
    current_input = in;
    fuzz_result_t result = parser_fuzz_one(&in);
    if (result != FUZZ_OK) {
        (void)printf("fuzz: REGRESSION: %s reproduces (%s)\n", path, fuzz_result_name(result));
    }
    return result != FUZZ_OK;
}

static unsigned fuzz_replay_dir(const char *dir)
{
    DIR *handle = opendir(dir);
    unsigned reproduced = 0;

    if (handle == NULL) {
        return 0;
    }
    for (struct dirent *entry = readdir(handle); entry != NULL; entry = readdir(handle)) {
        char path[FUZZ_PATH_MAX];
        if (!fuzz_has_suffix(entry->d_name, FUZZ_CRASH_SUFFIX)) {
            continue;
        }
        (void)snprintf(path, sizeof(path), "%s/%s", dir, entry->d_name);
        reproduced += (unsigned)fuzz_replay_file(path);
    }
    (void)closedir(handle);
    return reproduced;
}

static double fuzz_elapsed(const struct timespec *start)
{
    struct timespec now;

    (void)clock_gettime(CLOCK_MONOTONIC, &now);
    return (double)(now.tv_sec - start->tv_sec) + (double)(now.tv_nsec - start->tv_nsec) / 1e9;
}

static unsigned long fuzz_loop(const fuzz_options_t *opts, unsigned *crashes, double *elapsed)
{
    struct timespec start;
    uint32_t rng = opts->seed ? opts->seed : 1u;
    unsigned long execs = 0;

    (void)clock_gettime(CLOCK_MONOTONIC, &start);
    *elapsed = 0.0;
    while (*elapsed < (double)opts->seconds && *crashes == 0) {
        fuzz_load_seed(&current_input, fuzz_below(&rng, 5u));
        for (uint32_t rounds = 1u + fuzz_below(&rng, 4u); rounds > 0; rounds--) {
            fuzz_mutate_once(&current_input, &rng);
        }
        fuzz_result_t result = parser_fuzz_one(&current_input);
        execs++;
        if (result != FUZZ_OK) {
            *crashes += (unsigned)fuzz_report_crash(&current_input, result, opts->crash_dir);
        }
        if ((execs & FUZZ_TIME_CHECK_MASK) == 0) {
            *elapsed = fuzz_elapsed(&start);
        }
    }
    *elapsed = fuzz_elapsed(&start);
    return execs;
}

static int fuzz_parse_args(int argc, char **argv, fuzz_options_t *opts)
{
    for (int i = 1; i + 1 < argc; i += 2) {
        if (strcmp(argv[i], "--seconds") == 0) {
            opts->seconds = (unsigned)strtoul(argv[i + 1], NULL, 10);
        } else if (strcmp(argv[i], "--seed") == 0) {
            opts->seed = (uint32_t)strtoul(argv[i + 1], NULL, 10);
        } else if (strcmp(argv[i], "--crash-dir") == 0) {
            opts->crash_dir = argv[i + 1];
        } else if (strcmp(argv[i], "--replay") == 0) {
            opts->replay_file = argv[i + 1];
        } else {
            return -1;
        }
    }
    return (argc % 2 == 1) ? 0 : -1;
}

int main(int argc, char **argv)
{
    fuzz_options_t opts = {10u, 1u, "fuzz/crashes", NULL};
    unsigned crashes = 0;
    double elapsed = 0.0;

    if (fuzz_parse_args(argc, argv, &opts) != 0) {
        (void)fprintf(stderr, "usage: %s [--seconds N] [--seed N] [--crash-dir DIR] [--replay FILE]\n",
                      argv[0]);
        return 2;
    }
    current_crash_dir = opts.crash_dir;
    if (__sanitizer_set_death_callback != NULL) {
        __sanitizer_set_death_callback(fuzz_on_sanitizer_death);
    }
    if (opts.replay_file != NULL) {
        return fuzz_replay_file(opts.replay_file);
    }

    unsigned regressions = fuzz_replay_dir(opts.crash_dir);
    unsigned long execs = 0;
    if (regressions == 0) {
        execs = fuzz_loop(&opts, &crashes, &elapsed);
    }
    (void)printf("FUZZ execs=%lu crashes=%u regressions=%u seed=%u seconds=%.1f\n", execs,
                 crashes, regressions, (unsigned)opts.seed, elapsed);
    return (crashes + regressions) ? 1 : 0;
}
