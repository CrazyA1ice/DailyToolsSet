# Run from anywhere: outputs always remain under DailyToolsSet/FolderHub.
$ErrorActionPreference = "Stop"
$Project = $PSScriptRoot
$Output = Join-Path $Project "test-results"
New-Item -ItemType Directory -Path $Output -Force | Out-Null
# V4.8 and earlier instructions created logs at repository root.
# Move only known FolderHub unittest logs into this project's test-results.
$RepositoryRoot = Split-Path -Parent $Project
Get-ChildItem -LiteralPath $RepositoryRoot -File -Filter "folderhub-tests-*.txt" -ErrorAction SilentlyContinue | ForEach-Object {
    $Destination = Join-Path $Output $_.Name
    if (Test-Path -LiteralPath $Destination) {
        $Destination = Join-Path $Output ($_.BaseName + "-legacy-" + (Get-Date -Format "yyyyMMddHHmmssfff") + ".txt")
    }
    Move-Item -LiteralPath $_.FullName -Destination $Destination -ErrorAction SilentlyContinue
}
$Log = Join-Path $Output ("folderhub-tests-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".txt")
Push-Location $Project
try {
    python -m unittest discover -s tests -t . -v *>&1 | Out-File -FilePath $Log -Encoding UTF8
    $ExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
Write-Host ("测试结果: " + $Log)
Select-String -CaseSensitive -Path $Log -Pattern "Ran \d+ tests", "^OK$", "^FAILED", "^ERROR:", "^FAIL:" | ForEach-Object { $_.Line }
if ($ExitCode -ne 0) { exit $ExitCode }
