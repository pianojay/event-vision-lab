param(
    [switch]$Editor,
    [switch]$Validate,
    [switch]$ValidateControls,
    [string]$AcquisitionConfig = '',
    [string]$EventCaptureDirectory = '',
    [ValidateSet('vulkan','d3d12')][string]$Driver = 'vulkan',
    [int]$ProfileSeconds = 0,
    [string]$CapturePath = '',
    [ValidateRange(0,3)][int]$View = 0,
    [string]$GodotDirectory = '',
    [string]$EvidenceDirectory = ''
)
$ErrorActionPreference = 'Stop'
if ($ValidateControls -and ($Editor -or $Validate -or $ProfileSeconds -ne 0)) {
    throw '-ValidateControls cannot be combined with -Editor, -Validate, or -ProfileSeconds.'
}
if (($AcquisitionConfig -or $EventCaptureDirectory) -and ($Editor -or $Validate -or $ValidateControls -or $ProfileSeconds -ne 0)) {
    throw 'Live acquisition cannot be combined with editor, baseline validation, or profiling.'
}
if (($AcquisitionConfig -and -not $EventCaptureDirectory) -or ($EventCaptureDirectory -and -not $AcquisitionConfig)) {
    throw 'Supply both -AcquisitionConfig and -EventCaptureDirectory.'
}
$projectPath = Join-Path $PSScriptRoot 'prototype'
# Explicit settings must resolve as given; do not silently fall back after a typo.
if (-not $GodotDirectory) { $GodotDirectory = $env:EVENT_LAB_GODOT_DIR }
if (-not $GodotDirectory) {
    $candidates = @('C:\Godot_v4.7.2-stable_win64.exe', (Join-Path $PSScriptRoot 'tools\godot\4.7.2'))
    foreach ($candidate in $candidates) {
        if ((Test-Path -LiteralPath (Join-Path $candidate 'Godot_v4.7.2-stable_win64.exe') -PathType Leaf) -and
            (Test-Path -LiteralPath (Join-Path $candidate 'Godot_v4.7.2-stable_win64_console.exe') -PathType Leaf)) {
            $GodotDirectory = $candidate
            break
        }
    }
}
if (-not $GodotDirectory) {
    throw 'Godot 4.7.2 was not found. Set -GodotDirectory or EVENT_LAB_GODOT_DIR; see docs/godot-prototype.md.'
}
$GodotDirectory = [System.IO.Path]::GetFullPath($GodotDirectory)
$consoleExe = Join-Path $GodotDirectory 'Godot_v4.7.2-stable_win64_console.exe'
$guiExe = Join-Path $GodotDirectory 'Godot_v4.7.2-stable_win64.exe'
foreach ($executable in @($guiExe, $consoleExe)) {
    if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) { throw "Godot executable missing: $executable" }
}
$version = & $consoleExe --version
if ($LASTEXITCODE -ne 0 -or "$version" -notmatch '^4\.7\.2\.') {
    throw "Expected Godot 4.7.2; received '$version' from $consoleExe"
}
Write-Host "Godot $version from $GodotDirectory"
if ($EvidenceDirectory) { $evidencePath = [System.IO.Path]::GetFullPath($EvidenceDirectory) }
else { $evidencePath = Join-Path $PSScriptRoot 'docs\evidence\2026-11-22' }
New-Item -ItemType Directory -Force -Path $evidencePath | Out-Null
$godotArguments = @('--path', $projectPath)
if (-not $ValidateControls) {
    $godotArguments += @('--rendering-method', 'mobile', '--rendering-driver', $Driver)
}
if ($ValidateControls) {
    $godotArguments += @('--headless', '--script', 'res://tests/controls_tests.gd', '--log-file', (Join-Path $evidencePath 'controls-tests.log'))
} elseif ($AcquisitionConfig) {
    $revision = git -C $PSScriptRoot rev-parse HEAD
    $godotArguments += @('--log-file', (Join-Path $evidencePath 'acquisition.log'), '--', ('--acquisition-config=' + [System.IO.Path]::GetFullPath($AcquisitionConfig)), ('--event-capture=' + [System.IO.Path]::GetFullPath($EventCaptureDirectory)), ('--source-revision=' + $revision))
} elseif ($Editor) {
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
if ($ValidateControls -or $Validate -or $ProfileSeconds -gt 0 -or $AcquisitionConfig) { & $consoleExe @godotArguments }
else { & $guiExe @godotArguments }
if ($LASTEXITCODE) { exit $LASTEXITCODE }
