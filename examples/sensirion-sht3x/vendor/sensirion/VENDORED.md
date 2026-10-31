# Sensirion SHT3x driver (vendored, unchanged)

- **Source:** https://github.com/Sensirion/embedded-i2c-sht3x
- **Commit:** `4026a907aa9045ffc2a2813302e8ee5e69c96846` (2026-09-29)
- **Licence:** BSD 3-Clause, Sensirion AG (see `LICENSE`)
- **Files:** `sht3x_i2c.[ch]`, `sensirion_i2c.[ch]`, `sensirion_common.[ch]`, `sensirion_config.h`,
  `sensirion_i2c_hal.h`. The vendor's own `sensirion_i2c_hal.c` is not copied; our version is in `../../hal/`.

These files are exactly what Sensirion publishes. Nothing was edited to make them work with VirtuLab; that is
the point of the example. `SHA256SUMS` lists their checksums and a test in the VirtuLab repository checks them
(`shasum -a 256 -c SHA256SUMS`).

To update: copy the files again from a newer commit, run `shasum -a 256 * > SHA256SUMS`, update the commit above.
