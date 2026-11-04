/*
 * Fallback for an LLVMFuzzerTestOneInput harness on machines without libFuzzer: blind,
 * deterministic byte mutation with no coverage feedback. It prints the same FUZZ result
 * line as the other harnesses, and a sanitizer abort saves the failing input.
 */
#include <dirent.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define MAX_INPUT 4096u

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size);

static uint32_t next(uint32_t *state)
{
    uint32_t x = *state;

    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    *state = x;
    return x;
}

extern void __sanitizer_set_death_callback(void (*callback)(void)) __attribute__((weak));

static const uint8_t *current;
static size_t current_size;
static const char *crash_dir = "fuzz/crashes";

/* Runs in the dying process, after the sanitizer report, so the failing input is not lost. */
static void save_current(void)
{
    char path[1024];
    uint32_t hash = 2166136261u;

    for (size_t i = 0; i < current_size; i++) {
        hash = (hash ^ current[i]) * 16777619u;
    }
    (void)snprintf(path, sizeof(path), "%s/crash-%08x", crash_dir, (unsigned)hash);
    FILE *file = fopen(path, "wb");
    if (file != NULL) {
        (void)fwrite(current, 1u, current_size, file);
        (void)fclose(file);
    }
}

static unsigned replay(const char *dir)
{
    uint8_t buf[MAX_INPUT];
    char path[1024];
    unsigned count = 0;
    DIR *handle = opendir(dir);

    if (handle == NULL) {
        return 0;
    }
    for (struct dirent *e = readdir(handle); e != NULL; e = readdir(handle)) {
        if (e->d_name[0] == '.') {
            continue;
        }
        (void)snprintf(path, sizeof(path), "%s/%s", dir, e->d_name);
        FILE *file = fopen(path, "rb");
        if (file != NULL) {
            size_t size = fread(buf, 1u, sizeof(buf), file);
            (void)fclose(file);
            current = buf;
            current_size = size;
            (void)LLVMFuzzerTestOneInput(buf, size);
            count++;
        }
    }
    (void)closedir(handle);
    return count;
}

int main(int argc, char **argv)
{
    uint8_t buf[MAX_INPUT];
    unsigned seconds = 10u;
    uint32_t rng = 1u;
    unsigned long execs = 0;

    for (int i = 1; i + 1 < argc; i += 2) {
        if (strcmp(argv[i], "--seconds") == 0) {
            seconds = (unsigned)strtoul(argv[i + 1], NULL, 10);
        } else if (strcmp(argv[i], "--seed") == 0) {
            rng = (uint32_t)strtoul(argv[i + 1], NULL, 10);
        } else if (strcmp(argv[i], "--crash-dir") == 0) {
            crash_dir = argv[i + 1];
        }
    }
    rng = (rng == 0u) ? 1u : rng;
    if (__sanitizer_set_death_callback != NULL) {
        __sanitizer_set_death_callback(save_current);
    }
    (void)replay(crash_dir);
    current = buf;

    time_t start = time(NULL);
    while ((unsigned)(time(NULL) - start) < seconds) {
        size_t size = (size_t)(next(&rng) % 256u);
        for (size_t i = 0; i < size; i++) {
            buf[i] = (uint8_t)next(&rng);
        }
        current_size = size;
        (void)LLVMFuzzerTestOneInput(buf, size);
        execs++;
    }
    (void)printf("FUZZ execs=%lu crashes=0 regressions=0 seed=%u seconds=%u.0\n", execs, (unsigned)rng, seconds);
    return 0;
}
