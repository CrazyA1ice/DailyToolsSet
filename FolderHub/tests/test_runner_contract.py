"""Regression contract for the Windows PowerShell unittest launcher.

These static assertions run on Windows and Linux. Native PowerShell 5.1
behavior still needs one actual Windows acceptance run.
"""
from pathlib import Path
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
        self.assertIn('Start-Process -FilePath $Python', self.commands)
        self.assertIn('-RedirectStandardOutput $StdoutFile', self.commands)
        self.assertIn('-RedirectStandardError $StderrFile', self.commands)
        self.assertIn('-NoNewWindow -Wait -PassThru', self.commands)
        self.assertNotIn('*>&1', self.commands)
        self.assertNotIn('2>&1', self.commands)

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
        self.assertIn('$ExitCode = $Process.ExitCode', self.code)
        self.assertIn('if ($ExitCode -ne 0) { exit $ExitCode }', self.code)
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
