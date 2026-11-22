param([string]$OutputDirectory = (Join-Path $PSScriptRoot '..\..\docs\evidence\2026-11-22'))
$ErrorActionPreference = 'Stop'
$outputDir = [System.IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
$buildDir = Join-Path $outputDir 'build'
New-Item -ItemType Directory -Force -Path $buildDir | Out-Null
$vswhere = 'C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe'
$vsInstall = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vsInstall) { throw 'MSVC x64 tools not found.' }
$devCmd = Join-Path $vsInstall 'Common7\Tools\VsDevCmd.bat'
$sourcePath = Join-Path $PSScriptRoot 'sensor-benchmark.cpp'
$exePath = Join-Path $buildDir 'sensor-benchmark.exe'
$objPath = Join-Path $buildDir 'sensor-benchmark.obj'
$buildScript = Join-Path $buildDir 'compile.cmd'
@('@echo off', ('call "{0}" -arch=x64 -host_arch=x64 >nul' -f $devCmd),
    'if errorlevel 1 exit /b %errorlevel%',
    ('cl /nologo /O2 /EHsc /std:c++17 "{0}" /Fe:"{1}" /Fo:"{2}"' -f $sourcePath,$exePath,$objPath),
    'exit /b %errorlevel%') | Set-Content -LiteralPath $buildScript -Encoding ascii
& $env:ComSpec /d /c $buildScript
if ($LASTEXITCODE -ne 0) { throw 'Benchmark compilation failed.' }
$json = & $exePath
if ($LASTEXITCODE -ne 0) { throw 'Benchmark failed.' }
$json | ConvertFrom-Json | Out-Null
$json | Set-Content -LiteralPath (Join-Path $outputDir 'sensor-benchmark.json') -Encoding utf8
$json
