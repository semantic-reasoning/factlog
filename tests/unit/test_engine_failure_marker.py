# SPDX-License-Identifier: Apache-2.0
"""One report-marker contract shared by Python and the install-isolated gate."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from factlog.common import ENGINE_FAILED_STATUS_LINE, records_engine_failure

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE = REPO_ROOT / "hooks" / "gate_check.sh"
TOOL = REPO_ROOT / "tools" / "run_logic_check.py"
SAMPLE_KB = REPO_ROOT / "examples" / "sample-kb"

# Independent contract pin: corpus expectations must not follow a mutated
# production constant automatically.
MARKER = b"status: engine-did-not-run"


@pytest.mark.parametrize(
    ("report", "expected"),
    [
        (b"header\n" + MARKER + b"\nreason\n", True),
        (b"header\r\n" + MARKER + b"\r\nreason\r\n", True),
        (b"header\n" + MARKER + b"\r\r\n", True),
        (b"header\nno status\n", False),
        (b"header\nprefix " + MARKER + b" suffix\n", False),
        (b"header\n\r" + MARKER + b"\n", False),
        (b"header\nsta\rtus: engine-did-not-run\n", False),
        (b"header\nodd\r" + MARKER + b"\n", False),
        (b"header\nodd\xe2\x80\xa8" + MARKER + b"\n", False),
        (b"header\nsta\xfftus: engine-did-not-run\n", False),
        (b"header\x00data\n" + MARKER + b"\nreason\xff\n", True),
        (b"header\n" + MARKER + b" \n", False),
    ],
)
def test_shared_predicate_and_real_gate_agree_on_raw_corpus(
    tmp_path: Path, report: bytes, expected: bool
):
    assert ENGINE_FAILED_STATUS_LINE == MARKER.decode()
    assert records_engine_failure(report) is expected

    kb = tmp_path / "kb"
    facts = kb / "facts"
    facts.mkdir(parents=True)
    (kb / "sources").mkdir()
    accepted = facts / "accepted.dl"
    accepted.write_text('relation("a", "r", "b").\n', encoding="utf-8")
    report_path = facts / "logic_report.txt"
    report_path.write_bytes(report)
    os.utime(accepted, (1_700_000_000, 1_700_000_000))
    os.utime(report_path, (1_800_000_000, 1_800_000_000))

    env = dict(os.environ, FACTLOG_ROOT=str(kb), XDG_CONFIG_HOME=str(tmp_path / "cfg"))
    result = subprocess.run(
        ["bash", str(GATE)],
        input='{"file_path":"' + str(accepted) + '"}',
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT,
    )

    if expected:
        assert result.returncode == 2
        assert "last logic check could not run the engine" in result.stderr
        assert "could not be judged" not in result.stderr
    else:
        assert result.returncode == 0, result.stderr
        assert "DENIED" not in result.stderr


@pytest.mark.parametrize(
    "report",
    [
        "header\nstatus: engine-did-not-run\n",
        "header\r\nstatus: engine-did-not-run\r\n",
        "header\nstatus: engine-did-not-run\r\r\n",
        "header\nodd\rstatus: engine-did-not-run\n",
        "header\nodd\u2028status: engine-did-not-run\n",
        "header\nprefix status: engine-did-not-run\n",
    ],
)
def test_text_and_bytes_paths_have_the_same_rule(report: str):
    assert records_engine_failure(report) is records_engine_failure(report.encode())


def test_predicate_rejects_implicit_coercion():
    with pytest.raises(TypeError, match="report must be str or bytes"):
        records_engine_failure(bytearray(MARKER))  # type: ignore[arg-type]


@pytest.mark.parametrize("optimized", [False, True])
def test_writer_postcondition_calls_predicate_even_when_optimized(
    tmp_path: Path, optimized: bool
):
    kb = tmp_path / "kb"
    (kb / "facts").mkdir(parents=True)
    code = f"""
import importlib.util, sys
sys.argv = [{str(TOOL)!r}, "--wiki", {str(kb)!r}]
spec = importlib.util.spec_from_file_location("marker_writer", {str(TOOL)!r})
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.records_engine_failure = lambda report: False
try:
    module.engine_failure_report(RuntimeError("boom"))
except RuntimeError as exc:
    print(str(exc))
else:
    raise SystemExit("writer predicate was not called")
"""
    command = [sys.executable]
    if optimized:
        command.append("-O")
    command.extend(["-c", code])
    result = subprocess.run(command, capture_output=True, text=True, cwd=REPO_ROOT)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == (
        "engine failure report violates the shared status-line contract"
    )


@pytest.mark.parametrize("mode", ["nonzero", "invalid-token"])
def test_gate_report_runner_protocol_fails_closed(tmp_path: Path, mode: str):
    kb = tmp_path / "kb"
    facts = kb / "facts"
    facts.mkdir(parents=True)
    (kb / "sources").mkdir()
    accepted = facts / "accepted.dl"
    accepted.write_text("fact\n", encoding="utf-8")
    report = facts / "logic_report.txt"
    report.write_bytes(MARKER + b"\n")
    os.utime(accepted, (1_700_000_000, 1_700_000_000))
    os.utime(report, (1_800_000_000, 1_800_000_000))

    runner = tmp_path / "selective-runner.sh"
    action = "exit 19" if mode == "nonzero" else "printf '%s\\n' unexpected-token"
    runner.write_text(
        f'''#!/usr/bin/env bash
if [[ "$*" == *FACTLOG_GATE_REPORT* ]]; then
  {action}
  exit 0
fi
exec {sys.executable!r} "$@"
''',
        encoding="utf-8",
    )
    runner.chmod(0o755)
    env = dict(
        os.environ,
        FACTLOG_ROOT=str(kb),
        FACTLOG_PYTHON_RUNNER=str(runner),
        XDG_CONFIG_HOME=str(tmp_path / "cfg"),
    )
    result = subprocess.run(
        ["bash", str(GATE)],
        input='{"file_path":"' + str(accepted) + '"}',
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 2
    assert "facts/logic_report.txt could not be judged" in result.stderr
    assert "last logic check could not run the engine" not in result.stderr


def test_status_uses_raw_verdict_but_replaces_invalid_display_bytes(tmp_path: Path):
    kb = tmp_path / "kb"
    shutil.copytree(SAMPLE_KB, kb)
    report = kb / "facts" / "logic_report.txt"
    report.write_bytes(
        b"Logic Check Report\n==================\n"
        + MARKER
        + b"\nreason: loader \xff failed\n"
    )
    result = subprocess.run(
        [sys.executable, "-m", "factlog", "status", "--target", str(kb)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    assert "report records a run that never started the engine" in result.stdout
    assert "reason: loader \ufffd failed" in result.stdout
