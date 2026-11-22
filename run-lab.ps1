param(
    [switch]$Editor,
    [switch]$Validate,
    [ValidateSet('vulkan','d3d12')][string]$Driver = 'vulkan',
    [int]$ProfileSeconds = 0,
    [string]$CapturePath = '',
    [ValidateRange(0,3)][int]$View = 0
)
$ErrorActionPreference = 'Stop'
$projectPath = Join-Path $PSScriptRoot 'prototype'
$godotDirectory = Join-Path $PSScriptRoot 'tools\godot\4.7.2'
$consoleExe = Join-Path $godotDirectory 'Godot_v4.7.2-stable_win64_console.exe'
$guiExe = Join-Path $godotDirectory 'Godot_v4.7.2-stable_win64.exe'
if (-not (Test-Path -LiteralPath $guiExe)) {
    throw 'Godot 4.7.2 is missing. See docs/godot-prototype.md for the official portable download.'
}
$evidencePath = Join-Path $PSScriptRoot 'docs\evidence\2026-11-22'
New-Item -ItemType Directory -Force -Path $evidencePath | Out-Null
$godotArguments = @('--path', $projectPath, '--rendering-method', 'mobile', '--rendering-driver', $Driver)
if ($Editor) {
    $godotArguments += '--editor'
} elseif ($Validate) {
    $godotArguments += @('--script', 'res://tests/sensor_tests.gd', '--log-file', (Join-Path $evidencePath 'active-lighting-tests.log'), '--', ('--report=' + (Join-Path $evidencePath 'active-lighting-tests.json')))
} elseif ($ProfileSeconds -gt 0) {
    $godotArguments += @('--log-file', (Join-Path $evidencePath 'active-lighting-runtime.log'), '--', ('--duration=' + $ProfileSeconds), ('--report=' + (Join-Path $evidencePath 'active-lighting-runtime.json')))
    $godotArguments += '--view=' + $View
    if ($CapturePath) { $godotArguments += '--capture=' + [System.IO.Path]::GetFullPath($CapturePath) }
} else {
    $godotArguments += @('--log-file', (Join-Path $evidencePath 'godot-interactive.log'), '--', ('--view=' + $View))
}
if ($Validate -or $ProfileSeconds -gt 0) { & $consoleExe @godotArguments }
else { & $guiExe @godotArguments }
if ($LASTEXITCODE) { exit $LASTEXITCODE }
