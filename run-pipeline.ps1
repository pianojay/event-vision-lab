param(
    [string]$Config = '',
    [string]$OutputDirectory = '',
    [switch]$Replay,
    [switch]$VerifyReplay,
    [string]$GodotDirectory = '',
    [string]$ExistingRun = ''
)
$ErrorActionPreference = 'Stop'
if ($ExistingRun) {
    $outputPath = [System.IO.Path]::GetFullPath($ExistingRun)
} else {
    if (-not $Config) { $Config = Join-Path $PSScriptRoot 'tools\pipeline\configs\edge-ideal.json' }
    if (-not $OutputDirectory) {
        $runName = (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 6)
        $OutputDirectory = Join-Path $PSScriptRoot ('runs\pipeline\' + $runName)
    }
    $outputPath = [System.IO.Path]::GetFullPath($OutputDirectory)
    & python -B (Join-Path $PSScriptRoot 'tools\pipeline\pipeline.py') --config $Config --output $outputPath
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
$manifest = Join-Path $outputPath 'manifest.json'
if (-not (Test-Path -LiteralPath $manifest -PathType Leaf)) { throw "Run manifest not found: $manifest" }
Write-Host "Run artifact: $outputPath"
if ($Replay -or $VerifyReplay) {
    if (-not $GodotDirectory) { $GodotDirectory = $env:EVENT_LAB_GODOT_DIR }
    if (-not $GodotDirectory) { $GodotDirectory = 'C:\Godot_v4.7.2-stable_win64.exe' }
    $console = Join-Path $GodotDirectory 'Godot_v4.7.2-stable_win64_console.exe'
    if (-not (Test-Path -LiteralPath $console -PathType Leaf)) { throw "Godot console not found: $console" }
    $version = & $console --version
    if ($LASTEXITCODE -ne 0 -or "$version" -notmatch '^4\.7\.2\.') { throw "Expected Godot 4.7.2, received $version" }
    $godotArgs = @('--path', (Join-Path $PSScriptRoot 'prototype'), '--rendering-method', 'mobile', '--rendering-driver', 'vulkan',
                   '--script', 'res://replay.gd', '--log-file', (Join-Path $outputPath 'replay.log'), '--', ('--manifest=' + $manifest))
    if ($VerifyReplay) {
        $godotArgs += @('--verify', ('--capture=' + (Join-Path $outputPath 'replay.png')), ('--report=' + (Join-Path $outputPath 'replay-check.json')))
    }
    & $console @godotArgs
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
