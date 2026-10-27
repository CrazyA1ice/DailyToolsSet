# FolderHub unittest runner: ASCII-only for Windows PowerShell 5.1 codepages.
# All logs, temp captures, and Python scratch files stay under FolderHub.
$ErrorActionPreference = "Stop"
$Project = $PSScriptRoot
$Output = Join-Path $Project "test-results"
$Scratch = Join-Path $Project "tmp"
New-Item -ItemType Directory -Path $Output -Force | Out-Null
New-Item -ItemType Directory -Path $Scratch -Force | Out-Null

# Move only legacy FolderHub test logs from the repository root.
$RepositoryRoot = Split-Path -Parent $Project
Get-ChildItem -LiteralPath $RepositoryRoot -File -Filter "folderhub-tests-*.txt" -ErrorAction SilentlyContinue | ForEach-Object {
    $Destination = Join-Path $Output $_.Name
    if (Test-Path -LiteralPath $Destination) {
        $Destination = Join-Path $Output ($_.BaseName + "-legacy-" + (Get-Date -Format "yyyyMMddHHmmssfff") + ".txt")
    }
    Move-Item -LiteralPath $_.FullName -Destination $Destination -ErrorAction SilentlyContinue
}

$Log = Join-Path $Output ("folderhub-tests-" + (Get-Date -Format "yyyyMMdd-HHmmss-fff") + ".txt")
$RunId = [guid]::NewGuid().ToString("N")
$StdoutFile = Join-Path $Scratch ("unittest-stdout-" + $RunId + ".tmp")
$StderrFile = Join-Path $Scratch ("unittest-stderr-" + $RunId + ".tmp")
$PreviousTemp = $env:TEMP
$PreviousTmp = $env:TMP
$PreviousTmpDir = $env:TMPDIR
$PreviousPythonIOEncoding = $env:PYTHONIOENCODING
$ExitCode = 1

Push-Location $Project
try {
    $env:TEMP = $Scratch
    $env:TMP = $Scratch
    $env:TMPDIR = $Scratch
    $env:PYTHONIOENCODING = "utf-8"

    # Several Python installations can appear in PATH. Select one string.
    $PythonCommand = Get-Command python -CommandType Application -ErrorAction Stop | Select-Object -First 1
    $Python = [string]$PythonCommand.Source
    if ([string]::IsNullOrWhiteSpace($Python)) {
        throw "Python executable was not found."
    }

    # Do not pipe native stderr into PowerShell. unittest -v reports normal
    # progress to stderr; PS 5.1 may turn it into NativeCommandError.
    # Splatting also avoids fragile backtick line continuations.
    $RunOptions = @{
        FilePath = $Python
        ArgumentList = @("-m", "unittest", "discover", "-s", "tests", "-t", ".", "-v")
        WorkingDirectory = $Project
        NoNewWindow = $true
        Wait = $true
        PassThru = $true
        RedirectStandardOutput = $StdoutFile
        RedirectStandardError = $StderrFile
    }
    $Process = Start-Process @RunOptions
    $ExitCode = [int]$Process.ExitCode

    $StdoutText = ""
    $StderrText = ""
    if (Test-Path -LiteralPath $StdoutFile) {
        $StdoutText = [System.IO.File]::ReadAllText($StdoutFile, [System.Text.Encoding]::UTF8)
    }
    if (Test-Path -LiteralPath $StderrFile) {
        $StderrText = [System.IO.File]::ReadAllText($StderrFile, [System.Text.Encoding]::UTF8)
    }
    $Separator = ""
    if ($StdoutText.Length -gt 0 -and $StderrText.Length -gt 0 -and -not $StdoutText.EndsWith("`n")) {
        $Separator = [Environment]::NewLine
    }
    $LogText = $StdoutText + $Separator + $StderrText
    [System.IO.File]::WriteAllText($Log, $LogText, [System.Text.UTF8Encoding]::new($false))
}
finally {
    $env:TEMP = $PreviousTemp
    $env:TMP = $PreviousTmp
    $env:TMPDIR = $PreviousTmpDir
    $env:PYTHONIOENCODING = $PreviousPythonIOEncoding
    Remove-Item -LiteralPath $StdoutFile, $StderrFile -Force -ErrorAction SilentlyContinue
    Pop-Location
}

Write-Host ("Test log: " + $Log)
Select-String -CaseSensitive -Path $Log -Pattern "Ran \d+ tests", "^OK$", "^FAILED", "^ERROR:", "^FAIL:" | ForEach-Object { $_.Line }
exit $ExitCode
