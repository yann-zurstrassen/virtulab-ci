"""End-to-end tests: real arm-none-eabi toolchain + QEMU. Skipped if either is missing."""

import io
import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from virtulab.boards import BOARDS
from virtulab.cli import main
from virtulab.emulator import RENODE

REPO = Path(__file__).resolve().parent.parent
CRC_EXAMPLE = REPO / "examples" / "crc"
HAVE_TOOLS = bool(shutil.which("arm-none-eabi-gcc") and shutil.which("qemu-system-arm"))
HAVE_RENODE = bool(shutil.which(RENODE))


class E2EBase(unittest.TestCase):
    """Temp project + simulated GitHub Actions environment; no tests of its own."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.outputs_file = self.tmp / "github_output"
        env = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_WORKSPACE": str(self.tmp),
            "GITHUB_OUTPUT": str(self.outputs_file),
            "GITHUB_STEP_SUMMARY": str(self.tmp / "summary.md"),
        }
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)

    def project(self, name: str, files: dict[str, str]) -> Path:
        root = self.tmp / name
        for path, content in files.items():
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            (root / path).write_text(textwrap.dedent(content))
        return root

    def virtulab(self, root: Path, *args: str) -> tuple[int, str]:
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["run", "-C", str(root), *args])
        return code, out.getvalue()

    def outputs(self) -> dict[str, str]:
        """Parse (and reset) the `key<<delimiter` blocks written to $GITHUB_OUTPUT."""
        lines = iter(self.outputs_file.read_text().splitlines())
        values = {}
        for line in lines:
            key, delimiter = line.split("<<")
            values[key] = "\n".join(iter(lambda: next(lines), delimiter))
        self.outputs_file.unlink()
        return values

    def report(self, root: Path) -> str:
        return (root / ".virtulab" / "report.md").read_text()


@unittest.skipUnless(HAVE_TOOLS, "arm-none-eabi-gcc and qemu-system-arm are required")
class EndToEndTest(E2EBase):

    def test_crc_example_passes_on_every_board(self):
        root = self.tmp / "crc"
        shutil.copytree(CRC_EXAMPLE, root)
        for board, spec in BOARDS.items():
            with self.subTest(board=board):
                if spec.emulator == "renode" and not HAVE_RENODE:
                    self.skipTest("renode is not installed")
                code, log = self.virtulab(root, "-b", board, "-s", "src/*.c", "test/*.c",
                                          "-I", "include")
                self.assertEqual(code, 0, log)
                out = self.outputs()
                self.assertEqual(out["status"], "passed")
                self.assertEqual((out["tests_total"], out["tests_passed"]), ("4", "4"))
                self.assertGreater(int(out["flash_bytes"]), 0)

    def test_bare_metal_example_without_runtime(self):
        root = self.tmp / "bare"
        shutil.copytree(REPO / "examples" / "bare-metal", root)
        code, log = self.virtulab(root, "-s", "main.c", "--no-runtime",
                                  "--linker-script", "layout.ld")
        self.assertEqual(code, 0, log)
        self.assertIn("Hello from VirtuLab Virtual MCU!", log)
        self.assertNotIn("warning", log)

    def test_failing_test_is_annotated(self):
        root = self.tmp / "crc"
        shutil.copytree(CRC_EXAMPLE, root)
        crc = root / "src" / "crc.c"
        crc.write_text(crc.read_text().replace("0xEDB88320u", "0xEDB88321u"))
        code, log = self.virtulab(root, "-s", "src/*.c", "test/*.c", "-I", "include")
        self.assertEqual(code, 1)
        self.assertIn("::error file=crc/test/test_crc.c,line=15,"
                      "title=Test failed%3A test_crc32_check_value::Expected 0xCBF43926", log)
        out = self.outputs()
        self.assertEqual((out["status"], out["tests_failed"]), ("failed", "1"))
        self.assertIn("#### ❌ Failing tests", self.report(root))

    def test_fault_is_mapped_to_source_line(self):
        root = self.project("crash", {
            "src/main.c": """\
                #include <stdio.h>
                __attribute__((noinline)) static void parse_packet(int len) {
                    if (len > 4)
                        __builtin_trap();
                }
                int main(void) {
                    printf("starting\\n");
                    parse_packet(10);
                    return 0;
                }
            """,
        })
        for board in ("lm3s6965evb", "microbit"):  # Cortex-M3 and the Thumb-1 M0 path
            with self.subTest(board=board):
                code, log = self.virtulab(root, "-b", board, "-s", "src/*.c")
                self.assertEqual(code, 1, log)
                self.assertIn("starting", log)
                self.assertIn("💥 HardFault in parse_packet at src/main.c:4", log)
                self.assertIn("::error file=crash/src/main.c,line=4,", log)
                self.assertEqual(self.outputs()["status"], "crashed")

    def test_timeout(self):
        root = self.project("hang", {"main.c": "int main(void) { for (;;) {} }\n"})
        code, log = self.virtulab(root, "-s", "main.c", "-t", "1s")
        self.assertEqual(code, 1)
        self.assertIn("did not exit within 1s", log)
        self.assertEqual(self.outputs()["status"], "timeout")

    def test_exit_code_propagates(self):
        root = self.project("exit", {"main.c": "int main(void) { return 7; }\n"})
        code, log = self.virtulab(root, "-s", "main.c")
        self.assertEqual(code, 1)
        self.assertIn("(exit code 7)", log)

    def test_compile_error_is_annotated(self):
        root = self.project("broken", {"src/main.c": "int main(void) {\n  return missing;\n}\n"})
        code, log = self.virtulab(root, "-s", "src/*.c")
        self.assertEqual(code, 2)
        self.assertIn("::error file=broken/src/main.c,line=2,title=Compiler error::", log)
        self.assertEqual(self.outputs()["status"], "build_failed")
        self.assertIn("🔨 Compiler errors", self.report(root))

    def test_ram_overflow_fails_the_build(self):
        root = self.project("overflow", {
            "main.c": "static char buf[16 * 1024];\n"
                      "int main(void) { buf[0] = 1; return buf[100]; }\n",
        })
        code, log = self.virtulab(root, "-b", "lm3s811evb", "-s", "main.c")  # 8 KiB RAM
        self.assertEqual(code, 2)
        self.assertIn("region `RAM' overflowed", log)

    def test_cpp_static_constructors_and_unflushed_printf(self):
        root = self.project("cpp", {
            "main.cpp": """\
                #include <cstdio>
                struct Counter { int value; Counter() : value(41) {} };
                static Counter counter;
                int main() {
                    std::printf("value=%d", counter.value + 1);  // no trailing newline
                    return counter.value == 41 ? 0 : 1;
                }
            """,
        })
        code, log = self.virtulab(root, "-b", "mps2-an386", "-s", "*.cpp")
        self.assertEqual(code, 0, log)
        self.assertIn("value=42", log)

    def test_baseline_delta_and_budget(self):
        root = self.project("repo", {
            "fw/main.c": "int main(void) { return 0; }\n",
            "fw/test.c": "void helper(void) {}\n",
        })
        git = ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run([*git, "init", "-q"], check=True)
        subprocess.run([*git, "add", "."], check=True)
        subprocess.run([*git, "commit", "-qm", "base"], check=True)
        (root / "fw" / "main.c").write_text(
            "#include <stdint.h>\n"
            "const uint8_t lookup_table[2048] = {1};\n"
            "int main(void) { volatile int i = 0; return lookup_table[i] - 1; }\n"
        )

        code, log = self.virtulab(root / "fw", "-s", "*.c", "--baseline", "HEAD")
        self.assertEqual(code, 0, log)
        out = self.outputs()
        self.assertGreaterEqual(int(out["flash_delta"]), 2048)
        self.assertEqual(out["ram_delta"], "0")
        self.assertIn("| `lookup_table` | 0 | 2,048 | +2,048 |", self.report(root / "fw"))

        code, log = self.virtulab(root / "fw", "-s", "*.c", "--baseline", "HEAD",
                                  "--max-flash-increase", "1K")
        self.assertEqual(code, 1)
        self.assertIn("title=Memory budget exceeded::Flash grew by", log)
        self.assertEqual(self.outputs()["status"], "budget_exceeded")

    def test_vl_sim_reports_unsupported_on_qemu(self):
        root = self.project("nosim", {
            "main.c": '#include "virtulab.h"\n'
                      'int main(void) { return vl_sim("anything") == 0 ? 0 : 1; }\n',
        })
        code, log = self.virtulab(root, "-s", "main.c")
        self.assertEqual(code, 0, log)

    def test_peripherals_rejected_on_qemu_board(self):
        root = self.project("qemuperiph", {"main.c": "int main(void) { return 0; }\n"})
        code, log = self.virtulab(root, "-s", "main.c", "-p", "tmp108: VirtuLab.TMP108 @ i2c1 0x48")
        self.assertEqual(code, 2)
        self.assertIn("cannot add peripherals", log)

    def test_missing_baseline_is_not_fatal(self):
        root = self.project("nogit", {"main.c": "int main(void) { return 0; }\n"})
        code, log = self.virtulab(root, "-s", "main.c", "--baseline", "main")
        self.assertEqual(code, 0, log)
        self.assertIn("No footprint delta", self.report(root))


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(HAVE_TOOLS and HAVE_RENODE, "the toolchain and Renode are required")
class RenodeTest(E2EBase):
    """Renode boards: UART console, peripherals, and vl_sim() emulator control."""

    def test_thermostat_example_with_simulated_sensor(self):
        root = self.tmp / "thermostat"
        shutil.copytree(REPO / "examples" / "thermostat", root)
        code, log = self.virtulab(root, "-b", "stm32f4_discovery", "-s", "src/*.c", "test/*.c",
                                  "-I", "include", "-p", "board.repl")
        self.assertEqual(code, 0, log)
        out = self.outputs()
        self.assertEqual((out["status"], out["tests_passed"]), ("passed", "5"))
        self.assertIn("ok   sysbus.i2c1.tmp108 Temperature 21.5", log)
        self.assertIn("Emulator commands (vl_sim)", self.report(root))

    def test_rejected_emulator_command_fails_the_test(self):
        root = self.project("badsim", {
            "main.c": '#include "virtulab.h"\n'
                      'int main(void) { return vl_sim("sysbus.nothing Temperature 1") ? 0 : 5; }\n',
        })
        code, log = self.virtulab(root, "-b", "stm32f4_discovery", "-s", "main.c")
        self.assertEqual(code, 1, log)
        self.assertIn("FAIL sysbus.nothing Temperature 1", log)
        self.assertIn("(exit code 5)", log)

    def test_fault_and_timeout_on_renode(self):
        root = self.project("renodecrash", {
            "main.c": "int main(void) {\n    __builtin_trap();\n}\n",
        })
        code, log = self.virtulab(root, "-b", "stm32f4_discovery", "-s", "main.c")
        self.assertEqual(code, 1, log)
        self.assertIn("at main.c:2", log)
        self.assertEqual(self.outputs()["status"], "crashed")

        hang = self.project("renodehang", {"main.c": "int main(void) { for (;;) {} }\n"})
        code, log = self.virtulab(hang, "-b", "stm32f4_discovery", "-s", "main.c", "-t", "5s")
        self.assertEqual(code, 1, log)
        self.assertEqual(self.outputs()["status"], "timeout")
