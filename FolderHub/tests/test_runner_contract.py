"""Regression contract for the Windows PowerShell unittest launcher.

These static assertions run on Windows and Linux. Native PowerShell 5.1
behavior still needs one actual Windows acceptance run.
"""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "run_tests.ps1"


class PowerShellRunnerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code = SCRIPT.read_text(encoding="utf-8")
        cls.commands = "\n".join(
            line for line in cls.code.splitlines()
            if not line.lstrip().startswith("#")
        )

    def test_verbose_unittest_stderr_does_not_enter_powershell_error_pipeline(self):
        self.assertIn('$RunOptions = @{', self.commands)
        self.assertIn('FilePath = $Python', self.commands)
        self.assertIn('RedirectStandardOutput = $StdoutFile', self.commands)
        self.assertIn('RedirectStandardError = $StderrFile', self.commands)
        for parameter in ("NoNewWindow", "Wait", "PassThru"):
            self.assertIn(parameter + ' = $true', self.commands)
        self.assertIn('Start-Process @RunOptions', self.commands)
        self.assertNotIn('*>&1', self.commands)
        self.assertNotIn('2>&1', self.commands)

    def test_powershell51_source_is_ascii_and_needs_no_bom_or_codepage(self):
        # Windows PowerShell 5.1 decodes a BOM-less UTF-8 .ps1 through the
        # machine's ANSI codepage, which corrupts non-ASCII quoted messages.
        self.assertTrue(SCRIPT.read_bytes().isascii(),
                        "Keep this script ASCII-only for legacy PS5.1")
        self.assertNotIn("`" + "\\n", self.code, "Avoid backtick line continuations")
        self.assertIn('$RunOptions = @{', self.code)

    @unittest.skipUnless(sys.platform == "win32" and shutil.which("powershell.exe"),
                         "PowerShell 5.1 AST parser is available on Windows only")
    def test_windows_powershell_parser_rejects_no_syntax(self):
        # Parse without executing the suite recursively or writing outside
        # FolderHub; this catches the actual UnexpectedToken regression.
        env = dict(os.environ, FOLDERHUB_PS1_TO_PARSE=str(SCRIPT))
        command = (
            '$tokens=$null; $parseErrors=$null; '
            '[System.Management.Automation.Language.Parser]::ParseFile('
            '$env:FOLDERHUB_PS1_TO_PARSE,[ref]$tokens,[ref]$parseErrors) | Out-Null; '
            'if ($parseErrors.Count -gt 0) { '
            '$parseErrors | ForEach-Object { Write-Output $_.ToString() }; exit 1 }; '
            'exit 0'
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            env=env, cwd=SCRIPT.parent, capture_output=True, text=True,
            timeout=15, check=False
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_multiple_python_installations_select_one_scalar_path(self):
        # Get-Command -CommandType Application may enumerate *all* PATH
        # candidates; .Source on its Object[] crashes Start-Process -FilePath.
        self.assertIn('Get-Command python -CommandType Application -ErrorAction Stop |',
                      self.commands)
        self.assertIn('Select-Object -First 1', self.commands)
        self.assertIn('$Python = [string]$PythonCommand.Source', self.commands)
        self.assertIn('[string]::IsNullOrWhiteSpace($Python)', self.commands)
        self.assertNotIn('(Get-Command python -CommandType Application -ErrorAction Stop).Source',
                         self.commands)

    def test_preserves_real_python_exit_code_and_failure_logs(self):
        self.assertIn('$ExitCode = [int]$Process.ExitCode', self.code)
        self.assertIn('exit $ExitCode', self.code)
        self.assertIn('$StdoutText + $Separator + $StderrText', self.code)
        self.assertIn('Select-String -CaseSensitive -Path $Log', self.code)

    def test_output_and_scratch_are_local_and_temporary_state_is_restored(self):
        self.assertIn('Join-Path $Project "test-results"', self.code)
        self.assertIn('Join-Path $Project "tmp"', self.code)
        self.assertIn('Join-Path $Scratch ("unittest-stdout-"', self.code)
        self.assertIn('Join-Path $Scratch ("unittest-stderr-"', self.code)
        self.assertIn('$env:PYTHONIOENCODING = "utf-8"', self.code)
        for key in ("TEMP", "TMP", "TMPDIR", "PYTHONIOENCODING"):
            self.assertIn('$env:' + key + ' = $Previous', self.code)
        self.assertIn('Remove-Item -LiteralPath $StdoutFile, $StderrFile', self.code)
        self.assertIn('Pop-Location', self.code)


if __name__ == "__main__":
    unittest.main()
