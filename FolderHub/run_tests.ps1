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
$Scratch = Join-Path $Project "tmp"
New-Item -ItemType Directory -Path $Scratch -Force | Out-Null
$PreviousTemp = $env:TEMP
$PreviousTmp = $env:TMP
$PreviousTmpDir = $env:TMPDIR
$PreviousPythonIOEncoding = $env:PYTHONIOENCODING
# Standard unittest progress ("test_... ... ok") goes to stderr, even on
# success. With ErrorActionPreference=Stop, Windows PowerShell 5.1 can turn
# native stderr redirected by *>&1 into a terminating NativeCommandError.
# Redirect both native streams to files without going through the PS pipeline.
$RunId = [guid]::NewGuid().ToString("N")
$StdoutFile = Join-Path $Scratch ("unittest-stdout-" + $RunId + ".tmp")
$StderrFile = Join-Path $Scratch ("unittest-stderr-" + $RunId + ".tmp")
$ExitCode = 1
Push-Location $Project
try {
    # Python tempfile and temporary capture streams stay inside FolderHub/tmp.
    $env:TEMP = $Scratch
    $env:TMP = $Scratch
    $env:TMPDIR = $Scratch
    # Ensure unicode test messages survive Windows console code pages.
    $env:PYTHONIOENCODING = "utf-8"
    $Python = (Get-Command python -CommandType Application -ErrorAction Stop).Source
    $Process = Start-Process -FilePath $Python `
        -ArgumentList @("-m", "unittest", "discover", "-s", "tests", "-t", ".", "-v") `
        -WorkingDirectory $Project -NoNewWindow -Wait -PassThru `
        -RedirectStandardOutput $StdoutFile -RedirectStandardError $StderrFile
    $ExitCode = $Process.ExitCode

    # Python unittest writes normal test status and the final OK/FAILED line
    # to stderr; preserve both streams without treating either as PS errors.
    $StdoutText = if (Test-Path -LiteralPath $StdoutFile) {
        [System.IO.File]::ReadAllText($StdoutFile, [System.Text.Encoding]::UTF8)
    } else { "" }
    $StderrText = if (Test-Path -LiteralPath $StderrFile) {
        [System.IO.File]::ReadAllText($StderrFile, [System.Text.Encoding]::UTF8)
    } else { "" }
    [System.IO.File]::WriteAllText(
        $Log, $StdoutText + $StderrText,
        (New-Object System.Text.UTF8Encoding($false)))
} finally {
    $env:TEMP = $PreviousTemp
    $env:TMP = $PreviousTmp
    $env:TMPDIR = $PreviousTmpDir
    $env:PYTHONIOENCODING = $PreviousPythonIOEncoding
    Remove-Item -LiteralPath $StdoutFile, $StderrFile -Force -ErrorAction SilentlyContinue
    Pop-Location
}
Write-Host ("测试结果: " + $Log)
Select-String -CaseSensitive -Path $Log -Pattern "Ran \d+ tests", "^OK$", "^FAILED", "^ERROR:", "^FAIL:" | ForEach-Object { $_.Line }
if ($ExitCode -ne 0) { exit $ExitCode }
