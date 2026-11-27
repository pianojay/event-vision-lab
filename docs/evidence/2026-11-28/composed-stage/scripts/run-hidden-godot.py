import argparse
import ctypes
import json
import os
import subprocess
import time
from pathlib import Path
from ctypes import wintypes

parser = argparse.ArgumentParser()
parser.add_argument('--project', type=Path, required=True)
parser.add_argument('--script')
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--timeout', type=float, default=60)
parser.add_argument('--resolution', default='1280x800')
parser.add_argument('user_args', nargs='*')
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
engine = Path(r'C:\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64.exe')
startup = subprocess.STARTUPINFO()
startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
startup.wShowWindow = 0
command = [str(engine), '--path', str(args.project.resolve()), '--display-driver', 'windows',
           '--rendering-method', 'mobile', '--rendering-driver', 'vulkan',
           '--position', '-32000,-32000', '--resolution', args.resolution, '--single-window']
if args.script:
    command += ['--script', args.script]
command += ['--log-file', str((args.output/'godot.log').resolve()),
            '--', '--report=' + str((args.output/'report.json').resolve()), *args.user_args]
user32 = ctypes.WinDLL('user32', use_last_error=True)
callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
visible = []
windows = set()
with (args.output/'launcher.log').open('w', encoding='utf-8') as stream:
    process = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT,
                               startupinfo=startup, creationflags=subprocess.CREATE_NO_WINDOW)
    start = time.monotonic()
    while process.poll() is None:
        @callback_type
        def inspect_window(window, parameter):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(window, ctypes.byref(pid))
            if pid.value == process.pid:
                windows.add(int(window))
                if user32.IsWindowVisible(window):
                    visible.append(int(window))
                    user32.ShowWindow(window, 0)
            return True
        user32.EnumWindows(inspect_window, 0)
        if time.monotonic() - start > args.timeout:
            process.kill()
            process.wait()
            raise TimeoutError('Owned Godot validation process exceeded timeout')
        time.sleep(0.02)
    result = dict(command=command, process_id=process.pid, exit_code=process.returncode,
                  owned_windows=len(windows), visible_window_observations=len(visible),
                  startup_show_window='SW_HIDE', position=[-32000, -32000],
                  computer_use=False, real_context='windows/vulkan/mobile',
                  duration_s=time.monotonic()-start)
(args.output/'launcher.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
print(json.dumps(result))
raise SystemExit(process.returncode)
