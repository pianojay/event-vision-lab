"""Run one owned Godot process without foreground input or a visible window."""

import argparse
import ctypes
import hashlib
import json
import os
import platform
import socket
import subprocess
import threading
import time
from ctypes import wintypes
from pathlib import Path


def resolve_engine(requested):
    engine = requested.resolve()
    if not engine.is_file():
        raise FileNotFoundError(f"Engine does not exist: {engine}")
    if engine.name.lower().startswith("godot") and engine.name.lower().endswith("_console.exe"):
        engine = engine.with_name(engine.name[:-len("_console.exe")] + ".exe")
        if not engine.is_file():
            raise FileNotFoundError(f"Godot console wrapper requires its same-directory engine: {engine}")
    return engine


def file_sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def process_image(process):
    api = ctypes.WinDLL("kernel32", use_last_error=True).QueryFullProcessImageNameW
    api.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    api.restype = wintypes.BOOL
    capacity = wintypes.DWORD(32768)
    path = ctypes.create_unicode_buffer(capacity.value)
    if not api(wintypes.HANDLE(int(process._handle)), 0, path, ctypes.byref(capacity)):
        raise ctypes.WinError(ctypes.get_last_error())
    return Path(path.value)


def power_status():
    class Status(ctypes.Structure):
        _fields_ = [("ac", wintypes.BYTE), ("flags", wintypes.BYTE), ("percent", wintypes.BYTE),
                    ("reserved", wintypes.BYTE), ("remaining", wintypes.DWORD), ("full", wintypes.DWORD)]
    status = Status()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
        raise ctypes.WinError()
    return {"ac_line_status": status.ac, "battery_percent": status.percent}


def process_memory(process):
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ("peak_working", "working", "peak_paged", "paged",
                                                "peak_nonpaged", "nonpaged", "pagefile", "peak_pagefile", "private")]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    api = ctypes.windll.psapi.GetProcessMemoryInfo
    api.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
    if not api(wintypes.HANDLE(int(process._handle)), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError()
    return {"working_set_bytes": counters.working, "private_bytes": counters.private,
            "peak_working_set_bytes": counters.peak_working}


def source_identity(project, declared_revision=None):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(project), *args], text=True,
                                       creationflags=subprocess.CREATE_NO_WINDOW).strip()
    hashes = {"prototype/" + path.relative_to(project).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted(project.rglob("*")) if path.is_file() and ".godot" not in path.relative_to(project).parts
              and path.suffix in (".gd", ".glsl", ".gdshader", ".json", ".tscn", ".godot")}
    for path in sorted(Path(__file__).parent.glob("*.py")):
        hashes["tools/validation/" + path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    if declared_revision:
        if len(declared_revision) != 40 or any(char not in "0123456789abcdef" for char in declared_revision.lower()):
            raise ValueError("Snapshot source revision must be a full Git SHA")
        return {"commit": declared_revision, "provenance": "declared snapshot revision plus actual file hashes", "sha256": hashes}
    root = Path(git("rev-parse", "--show-toplevel"))
    if (root / "prototype").resolve() != project.resolve():
        raise ValueError("An archived/nested project requires --source-revision; outer repository identity is not its source")
    return {"commit": git("rev-parse", "HEAD"), "status": git("status", "--short"), "sha256": hashes}


def memory_trend(samples):
    if not samples:
        return {}
    times = [sample["wall_s"] for sample in samples]
    values = [sample["private_bytes"] for sample in samples]
    mean_t, mean_v = sum(times) / len(times), sum(values) / len(values)
    variance = sum((value - mean_t) ** 2 for value in times)
    slope = sum((t - mean_t) * (v - mean_v) for t, v in zip(times, values)) / variance if variance else 0
    return {"samples": len(samples), "first_private_bytes": values[0], "last_private_bytes": values[-1],
            "peak_private_bytes": max(values), "least_squares_private_bytes_per_second": slope,
            "scope": "whole owned process including warmup and validation instrumentation"}


def windows_inventory():
    command = "$inventory = @{cpu = @(Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors); graphics = @(Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion,DriverDate); physical_memory_bytes = (Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory; power_scheme = (powercfg /getactivescheme)}; $inventory | ConvertTo-Json -Depth 4 -Compress"
    try:
        result = subprocess.run(["powershell.exe", "-NoProfile", "-Command", command], capture_output=True,
                                text=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW, check=True)
        return json.loads(result.stdout)
    except (subprocess.SubprocessError, json.JSONDecodeError) as error:
        return {"inventory_error": str(error)}


class OutputReceiver:
    def __init__(self, directory, duration):
        from output_bounds import OutputAccumulator
        self.accumulator = OutputAccumulator(directory, duration)
        self.error = None
        self.completed = False
        self.server = socket.socket()
        self.server.bind(("127.0.0.1", 0))
        self.server.listen(1)
        self.server.settimeout(1)
        self.port = self.server.getsockname()[1]
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self.receive, daemon=True)
        self.thread.start()

    def receive(self):
        try:
            connection = None
            while not self.stopped.is_set():
                try:
                    connection, _ = self.server.accept()
                    break
                except socket.timeout:
                    pass
            if connection is None:
                return
            with connection:
                connection.settimeout(30)
                with connection.makefile("rb") as stream:
                    while not self.stopped.is_set():
                        line = stream.readline(4097)
                        if not line:
                            break
                        if len(line) > 4096:
                            raise ValueError("Frame header exceeds bound")
                        meta = json.loads(line)
                        if meta.get("end"):
                            self.completed = True
                            break
                        length = int(meta["width"]) * int(meta["height"]) * 3
                        if not 0 < length <= 8192 * 8192 * 3:
                            raise ValueError("Invalid frame payload size")
                        payload = stream.read(length)
                        self.accumulator.consume(meta, payload)
        except Exception as error:
            self.error = repr(error)

    def finish(self):
        self.thread.join(timeout=5)
        self.stopped.set()
        self.server.close()
        self.thread.join(timeout=2)
        report = self.accumulator.finish(self.completed and not self.error and not self.thread.is_alive())
        if self.error:
            report["receiver_error"] = self.error
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=750)
    parser.add_argument("--resolution", default="1280x800")
    parser.add_argument("--capture-output", action="store_true")
    parser.add_argument("--source-revision", help="Full source SHA for an archived project outside its owning checkout")
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("This launcher requires Windows and a real Windows graphics context")
    scenario = json.loads(args.scenario.read_text(encoding="utf-8"))
    try:
        engine = resolve_engine(args.engine)
    except OSError as error:
        parser.error(str(error))
    if not (args.project / "project.godot").is_file():
        parser.error("Godot project does not exist")
    if args.output.exists():
        parser.error("Use a new output directory to preserve prior evidence")
    args.output.mkdir(parents=True)
    (args.output / "scenario.json").write_text(json.dumps(scenario, indent=2) + "\n", encoding="utf-8")
    receiver = OutputReceiver(args.output, scenario["measure_seconds"]) if args.capture_output else None
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    command = [str(engine), "--path", str(args.project.resolve()), "--display-driver", "windows",
               "--rendering-method", "mobile", "--rendering-driver", "vulkan", "--position", "-32000,-32000",
               "--resolution", args.resolution, "--single-window", "--script", "res://tests/runtime_scenario.gd",
               "--log-file", str((args.output / "godot.log").resolve()), "--",
               "--validation-scenario=" + str(args.scenario.resolve()),
               "--validation-output=" + str(args.output.resolve())]
    if receiver:
        command.append("--capture-port=" + str(receiver.port))
    identity = source_identity(args.project.resolve(), args.source_revision)
    command.append("--source-revision=" + identity["commit"])
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    samples, windows = [], set()
    timed_out = False
    report = {"command": command, "source": identity, "platform": platform.platform(),
              "engine": {"requested_path": str(args.engine.resolve()), "resolved_path": str(engine),
                         "resolved_sha256": file_sha256(engine)},
              "processor": platform.processor(), "logical_cpus": os.cpu_count(), "headless": False,
              "windows_hardware": windows_inventory(),
              "startup_show_window": "SW_HIDE", "requested_backend": "windows/vulkan/mobile",
              "capture_instrumentation": bool(receiver), "computer_use": False}
    with (args.output / "launcher.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, startupinfo=startup,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        report["process_id"] = process.pid
        started = time.monotonic()
        next_sample = 0.0
        @callback_type
        def hide_owned(window, parameter):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(window, ctypes.byref(pid))
            if pid.value == process.pid:
                windows.add(int(window))
                if user32.IsWindowVisible(window):
                    user32.ShowWindow(window, 0)
            return True
        try:
            actual_image = process_image(process)
            report["process_image"] = {"path": str(actual_image), "sha256": file_sha256(actual_image),
                                       "matches_resolved_engine": actual_image.samefile(engine)}
            if not report["process_image"]["matches_resolved_engine"]:
                raise RuntimeError("Owned process image does not match the resolved engine")
            with (args.output / "process.jsonl").open("w", encoding="utf-8") as telemetry:
                while process.poll() is None:
                    elapsed = time.monotonic() - started
                    user32.EnumWindows(hide_owned, 0)
                    if elapsed >= next_sample:
                        sample = {"wall_s": elapsed, **process_memory(process), **power_status()}
                        samples.append(sample)
                        telemetry.write(json.dumps(sample) + "\n")
                        telemetry.flush()
                        next_sample = elapsed + 1
                    if elapsed >= args.timeout:
                        timed_out = True
                        process.kill()
                        break
                    time.sleep(0.02)
        except Exception as error:
            report["launcher_error"] = repr(error)
            raise
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            report.update(exit_code=process.returncode, timeout=timed_out, wall_seconds=time.monotonic() - started,
                          owned_windows=len(windows), memory=memory_trend(samples),
                          ac_power_all_samples=bool(samples) and all(row["ac_line_status"] == 1 for row in samples))
            if receiver:
                try:
                    report["output_analysis"] = receiver.finish()["verdict"]
                except Exception as error:
                    report["output_analysis_error"] = repr(error)
            (args.output / "launcher.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    raise SystemExit(1 if timed_out or report.get("output_analysis_error") else process.returncode)


if __name__ == "__main__":
    main()
