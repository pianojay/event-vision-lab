param([Parameter(Mandatory=$true)][string]$Protocol)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$matrix = Get-Content -LiteralPath $Protocol -Raw | ConvertFrom-Json
foreach ($run in $matrix.runs) {
    if (Test-Path -LiteralPath (Join-Path $run.output 'manifest.json')) { continue }
    & (Join-Path $root 'run-lab.ps1') -AcquisitionConfig $run.config -EventCaptureDirectory $run.output -EvidenceDirectory ($run.output + '-launch')
    if ($LASTEXITCODE -ne 0) { throw "Capture failed: $($run.id)" }
}
python (Join-Path $PSScriptRoot 'experiment.py') analyze (Split-Path -Parent $Protocol)
exit $LASTEXITCODE
