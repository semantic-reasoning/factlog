# SPDX-License-Identifier: Apache-2.0
"""The smoke harness owns one private, concurrency-safe scratch workspace."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE = REPO_ROOT / "tests" / "smoke.sh"

pytestmark = pytest.mark.skipif(os.name != "posix", reason="smoke.sh requires POSIX paths")


def _fake_python_source() -> str:
    return f"""#!{sys.executable}
import json
import os
import sys
import time
from pathlib import Path

def record(stage, **fields):
    path = Path(os.environ["SMOKE_TEST_LOG"])
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({{"stage": stage, **fields}}) + "\\n")

name = Path(sys.argv[0]).name
args = sys.argv[1:]
if name == "pip":
    record("pip", args=args)
    if os.environ.get("SMOKE_FAIL_STAGE") == "pip":
        raise SystemExit(7)
    raise SystemExit(0)

if args[:2] == ["-m", "venv"]:
    target = Path(args[2])
    target.joinpath("bin").mkdir(parents=True)
    source = Path(sys.argv[0]).resolve()
    os.symlink(source, target / "bin" / "python")
    os.symlink(source, target / "bin" / "pip")
    record("venv", target=str(target), config=os.environ.get("XDG_CONFIG_HOME", ""))
    raise SystemExit(0)

root = Path(os.environ.get("FACTLOG_ROOT", "")) if os.environ.get("FACTLOG_ROOT") else None
if args[:3] == ["-m", "factlog", "doctor"]:
    record("doctor")
    raise SystemExit(0)
if args[:3] == ["-m", "factlog", "init"]:
    target = Path(args[args.index("--target") + 1])
    record("init", target=str(target), config=os.environ.get("XDG_CONFIG_HOME", ""))
    marker = os.environ.get("SMOKE_SIGNAL_MARKER")
    if marker:
        marker_path = Path(marker)
        temporary = marker_path.with_name(marker_path.name + ".tmp-" + str(os.getpid()))
        temporary.write_text(str(target.parent), encoding="utf-8")
        os.replace(temporary, marker_path)
        while True:
            time.sleep(0.05)
    barrier = os.environ.get("SMOKE_BARRIER_DIR")
    if barrier:
        barrier_path = Path(barrier)
        barrier_path.mkdir(parents=True, exist_ok=True)
        barrier_path.joinpath(str(os.getpid())).write_text(str(target.parent), encoding="utf-8")
        deadline = time.monotonic() + 10
        expected = int(os.environ.get("SMOKE_BARRIER_COUNT", "2"))
        while len(list(barrier_path.iterdir())) < expected:
            if time.monotonic() >= deadline:
                raise SystemExit(8)
            time.sleep(0.02)
    for child in ("facts", "sources", "pages", "policy", "decisions"):
        target.joinpath(child).mkdir(parents=True, exist_ok=True)
    raise SystemExit(0)

tool = Path(args[0]).name if args else ""
if tool == "compile_facts.py":
    record("compile", root=str(root))
    root.joinpath("facts", "accepted.dl").write_text(
        'relation("Claude Code", "developed_by", "Anthropic").\\n', encoding="utf-8"
    )
    raise SystemExit(0)
if tool == "run_logic_check.py":
    record("logic", root=str(root))
    root.joinpath("facts", "logic_report.txt").write_text(
        "Query evaluation:\\n"
        "- relation results: 1 rows; Claude Code, developed_by, Anthropic\\n",
        encoding="utf-8",
    )
    raise SystemExit(0)
if tool == "validate.py":
    record("validate", root=str(root))
    raise SystemExit(0)
record("unexpected", args=args)
raise SystemExit(9)
"""


def _fake_toolchain(tmp_path: Path) -> Path:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    python = fake_bin / "python3"
    python.write_text(_fake_python_source(), encoding="utf-8")
    python.chmod(0o755)
    return fake_bin


def _environment(fake_bin: Path, log: Path, **extra: str) -> dict[str, str]:
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join((str(fake_bin), env["PATH"]))
    env["SMOKE_TEST_LOG"] = str(log)
    env.update(extra)
    return env


def _events(log: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def _work_root(events: list[dict[str, object]]) -> Path:
    event = next(item for item in events if item["stage"] == "venv")
    return Path(str(event["target"])).parent


def _group_exists(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    return True


def _signal_group(pgid: int, sent: signal.Signals) -> None:
    try:
        os.killpg(pgid, sent)
    except ProcessLookupError:
        pass


def _terminate_groups(processes: list[subprocess.Popen[str]]) -> None:
    # A session leader can exit while a descendant keeps its stdout/stderr pipe
    # open. `poll()` then says the Popen is done even though communicate() hangs
    # and the known process group still exists, so signal the PGID independently
    # of the leader's state.
    pending = []
    for process in processes:
        try:
            # A zero deadline can raise even for an exited child whose finite
            # pipe output has not been drained yet. Give completed output a
            # bounded chance to drain before treating the session as live.
            process.communicate(timeout=0.1)
        except subprocess.TimeoutExpired:
            pending.append(process)

    for process in pending:
        _signal_group(process.pid, signal.SIGTERM)
    still_pending = []
    for process in pending:
        try:
            process.communicate(timeout=0.5)
        except subprocess.TimeoutExpired:
            still_pending.append(process)
    for process in still_pending:
        _signal_group(process.pid, signal.SIGKILL)
    for process in still_pending:
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            _signal_group(process.pid, signal.SIGKILL)
            process.communicate(timeout=5)


def test_two_runs_overlap_without_sharing_any_workspace(tmp_path):
    fake_bin = _fake_toolchain(tmp_path)
    barrier = tmp_path / "barrier"
    processes = []
    logs = []
    for index in range(2):
        log = tmp_path / f"run-{index}.jsonl"
        logs.append(log)
        processes.append(
            subprocess.Popen(
                ["bash", str(SMOKE)],
                cwd=REPO_ROOT,
                env=_environment(
                    fake_bin,
                    log,
                    SMOKE_BARRIER_DIR=str(barrier),
                    SMOKE_BARRIER_COUNT="2",
                ),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
        )

    try:
        completed = [process.communicate(timeout=20) for process in processes]
    finally:
        _terminate_groups(processes)
    event_sets = [_events(log) for log in logs]
    roots = [_work_root(events) for events in event_sets]

    assert len({str(root) for root in roots}) == 2
    assert len(list(barrier.iterdir())) == 2, "both runs must reach the overlap barrier"
    for (stdout, stderr), process, events, root in zip(
        completed, processes, event_sets, roots, strict=True
    ):
        assert process.returncode == 0, stdout + stderr
        assert stderr == ""
        assert "Smoke results: 15 passed, 0 failed" in stdout
        stages = [event["stage"] for event in events]
        assert stages.count("venv") == 1
        assert stages.count("pip") == 2
        assert stages.count("logic") == 2
        assert {"doctor", "init", "compile", "validate"} <= set(stages)
        venv = next(event for event in events if event["stage"] == "venv")
        init = next(event for event in events if event["stage"] == "init")
        assert Path(str(venv["target"])).parent == root
        assert Path(str(venv["config"])).parent == root
        assert Path(str(init["target"])).parent == root
        assert Path(str(init["config"])).parent == root
        for event in events:
            if event["stage"] in {"compile", "logic", "validate"}:
                assert Path(str(event["root"])) == root / "kb"
        assert not root.exists()

    normalized = [output.replace(str(root), "<WORK_ROOT>") for (output, _), root in zip(completed, roots)]
    assert normalized[0] == normalized[1]


def test_failure_after_venv_creation_cleans_only_its_workspace(tmp_path):
    fake_bin = _fake_toolchain(tmp_path)
    log = tmp_path / "failure.jsonl"
    sentinel = tmp_path / "sentinel"
    sentinel.mkdir()

    result = subprocess.run(
        ["bash", str(SMOKE)],
        cwd=REPO_ROOT,
        env=_environment(fake_bin, log, SMOKE_FAIL_STAGE="pip"),
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )

    events = _events(log)
    root = _work_root(events)
    assert result.returncode == 7
    assert not root.exists()
    assert sentinel.is_dir()


def test_term_cleans_a_workspace_while_a_child_is_running(tmp_path):
    fake_bin = _fake_toolchain(tmp_path)
    log = tmp_path / "signal.jsonl"
    marker = tmp_path / "signal-marker"
    process = subprocess.Popen(
        ["bash", str(SMOKE)],
        cwd=REPO_ROOT,
        env=_environment(fake_bin, log, SMOKE_SIGNAL_MARKER=str(marker)),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 10
        root = None
        while process.poll() is None and time.monotonic() < deadline:
            if marker.exists():
                published = marker.read_text(encoding="utf-8").strip()
                if published.startswith("/"):
                    root = Path(published)
                    break
            time.sleep(0.02)
        assert root is not None, "smoke never published its blocking init workspace"

        process.terminate()
        stdout, stderr = process.communicate(timeout=10)
    finally:
        _terminate_groups([process])

    assert process.returncode == 143, stdout + stderr
    assert not root.exists()


def test_mktemp_failure_starts_no_pipeline_stage(tmp_path):
    fake_bin = _fake_toolchain(tmp_path)
    mktemp = fake_bin / "mktemp"
    mktemp.write_text("#!/bin/sh\nexit 9\n", encoding="utf-8")
    mktemp.chmod(0o755)
    log = tmp_path / "mktemp-failure.jsonl"

    result = subprocess.run(
        ["bash", str(SMOKE)],
        cwd=REPO_ROOT,
        env=_environment(fake_bin, log),
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert result.returncode == 9
    assert not log.exists(), "python/venv started after mktemp failed"


def test_test_cleanup_kills_descendants_after_the_session_leader_exits():
    process = subprocess.Popen(
        ["bash", "-c", "sleep 30 & exit 0"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        with pytest.raises(subprocess.TimeoutExpired):
            process.communicate(timeout=0.1)
        assert process.poll() == 0, "the leader must exit before cleanup is exercised"

        _terminate_groups([process])

        assert not _group_exists(process.pid)
    finally:
        _signal_group(process.pid, signal.SIGKILL)


def test_test_cleanup_drains_an_exited_process_without_signaling_it(monkeypatch):
    process = subprocess.Popen(
        ["bash", "-c", "printf finished"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    assert process.wait(timeout=5) == 0
    signals = []
    monkeypatch.setattr(
        sys.modules[__name__],
        "_signal_group",
        lambda pgid, sent: signals.append((pgid, sent)),
    )

    _terminate_groups([process])

    assert signals == []


def test_shell_syntax_and_static_delete_boundary():
    subprocess.run(["bash", "-n", str(SMOKE)], check=True, timeout=10)
    text = SMOKE.read_text(encoding="utf-8")
    assert "/tmp/factlog-smoke-venv" not in text
    assert "/tmp/factlog-smoke-kb" not in text
    assert 'rm -rf "$SMOKE_VENV"' not in text
    assert 'rm -rf "$SMOKE_KB"' not in text
    assert 'rm -rf -- "$WORK_ROOT"' in text
    assert "trap exit_with_cleanup EXIT" in text
    assert "trap 'signal_with_cleanup 143' TERM" in text
    assert text.index("trap exit_with_cleanup EXIT") < text.index('WORK_ROOT="$(mktemp -d)"')
