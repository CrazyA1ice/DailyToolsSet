# Run from anywhere: outputs always remain under DailyToolsSet/FolderHub.
$ErrorActionPreference = "Stop"
$Project = $PSScriptRoot
$Output = Join-Path $Project "test-results"
New-Item -ItemType Directory -Path $Output -Force | Out-Null
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
