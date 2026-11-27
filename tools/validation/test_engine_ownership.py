import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from run_hidden import process_image, resolve_engine


class EngineOwnershipTests(unittest.TestCase):
    def test_console_wrapper_resolves_to_same_directory_engine(self):
        with tempfile.TemporaryDirectory(prefix="engine with spaces ") as directory:
            wrapper = Path(directory) / "Godot_v4.7.2-stable_win64_console.exe"
            engine = Path(directory) / "Godot_v4.7.2-stable_win64.exe"
            wrapper.touch()
            engine.touch()
            self.assertEqual(resolve_engine(wrapper), engine.resolve())

    def test_console_wrapper_without_engine_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            wrapper = Path(directory) / "Godot_v4.7.2-stable_win64_console.exe"
            wrapper.touch()
            with self.assertRaises(FileNotFoundError):
                resolve_engine(wrapper)

    def test_direct_engine_and_unrelated_console_name_are_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ("Godot_v4.7.2-stable_win64.exe", "custom_console.exe"):
                engine = Path(directory) / name
                engine.touch()
                self.assertEqual(resolve_engine(engine), engine.resolve())

    def test_missing_engine_and_directory_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            for path in (Path(directory), Path(directory) / "Godot_console.exe"):
                with self.assertRaises(FileNotFoundError):
                    resolve_engine(path)

    def test_windows_console_suffix_is_case_insensitive(self):
        with tempfile.TemporaryDirectory() as directory:
            wrapper = Path(directory) / "GODOT_v4.7.2_win64_CONSOLE.EXE"
            engine = Path(directory) / "GODOT_v4.7.2_win64.exe"
            wrapper.touch()
            engine.touch()
            self.assertEqual(resolve_engine(wrapper), engine.resolve())

    @unittest.skipUnless(os.name == "nt", "Windows process handle API")
    def test_owned_process_image_and_termination_use_the_launched_process(self):
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            self.assertTrue(process_image(process).samefile(sys.executable))
            process.kill()
            self.assertNotEqual(process.wait(timeout=5), 0)
            self.assertIsNotNone(process.poll())
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
