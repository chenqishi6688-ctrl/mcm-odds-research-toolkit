from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class TestOfflineSmoke(unittest.TestCase):
    def run_cli(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, *args],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=f"command failed: {args}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        return result

    def test_core_self_tests(self) -> None:
        commands = [
            ("independent_score_matrix.py", "--self-test"),
            ("sporting_baseline_builder.py", "--self-test"),
            ("capital_intent_engine.py",),
            ("identity_registry.py", "self-test"),
            ("shadow_model_lab.py", "self-test"),
            ("adjustment_calibration_lab.py", "self-test"),
            ("capital_evidence_ledger.py", "self-test"),
            ("shadow_cohort_evaluator.py", "self-test"),
            ("improvement_completion_tracker.py", "self-test"),
            ("market_quality.py",),
            ("validate_report.py", "--self-test"),
        ]
        for command in commands:
            with self.subTest(command=command):
                self.run_cli(str(SCRIPTS / command[0]), *command[1:])

    def test_evidence_integrity_self_test(self) -> None:
        temp_root = ROOT / ".test-tmp"
        temp_root.mkdir(exist_ok=True)
        env = os.environ.copy()
        env["TMP"] = str(temp_root)
        env["TEMP"] = str(temp_root)
        try:
            self.run_cli(str(SCRIPTS / "evidence_integrity.py"), env=env)
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

    def test_synthetic_pipeline_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            output = Path(folder) / "demo-run"
            self.run_cli(
                str(SCRIPTS / "full_mcm_pipeline.py"),
                str(ROOT / "examples" / "synthetic-full-mcm-batch.json"),
                "--output",
                str(output),
            )
            validation = json.loads((output / "validation.json").read_text(encoding="utf-8"))
            self.assertTrue(validation["success"])
            self.assertEqual(validation["validated_fixtures"], 1)
            self.run_cli(str(SCRIPTS / "freeze_manifest.py"), str(output))


if __name__ == "__main__":
    unittest.main()


