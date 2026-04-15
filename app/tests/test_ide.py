"""
app/tests/test_ide.py
=====================
Full test suite for the Gravitix IDE API (ide_routes.py) and bot runner (ide_runner.py).

Coverage:
  - Unit tests for ide_runner helpers (_gx_available, _parse_gx_errors, _script_path)
  - Unit tests for compile_code (binary absent / timeout / success / errors)
  - Unit tests for publish_bot (binary absent / no-token / success / stop-previous)
  - Unit tests for stop_bot, get_status, get_logs
  - Integration tests for all five API endpoints (auth, success, failure, edge cases)
  - Security / validation tests (invalid project_id, oversized payload, unauthenticated)
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

# ── ensure project root on sys.path ────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from conftest import SyncASGIClient, make_user, login_user, random_str


# ===========================================================================
# Helpers
# ===========================================================================

def _auth_headers(client: SyncASGIClient, suffix: str | None = None) -> dict:
    """Register + login a fresh user, return fresh CSRF headers dict."""
    # Always use a random suffix so usernames never collide across test runs
    tag = (suffix or "") + random_str(8)
    user = make_user(client, suffix=tag)
    login_user(client, user["username"], user["password"])
    # Fetch a fresh CSRF token *after* login (the login itself consumes one)
    csrf = client.get("/api/authentication/csrf-token").json().get("csrf_token", "")
    return {"X-CSRF-Token": csrf}


VALID_CODE = """\
on /start do
    send "Hello!"
end
"""

INVALID_CODE = "@@@ this is not valid gravitix code at all $$$"

VALID_PID = "test_project_01"


# ===========================================================================
# Unit tests — ide_runner helpers
# ===========================================================================

class TestGxAvailable:
    """Tests for _gx_available()."""

    def test_returns_false_when_binary_missing(self, tmp_path):
        import app.bots.ide_runner as runner
        orig = runner._GX_BIN
        try:
            runner._GX_BIN = tmp_path / "nonexistent_bin"
            assert runner._gx_available() is False
        finally:
            runner._GX_BIN = orig

    def test_returns_false_when_not_executable(self, tmp_path):
        import app.bots.ide_runner as runner
        bin_path = tmp_path / "gravitix"
        bin_path.write_bytes(b"\x7fELF")
        bin_path.chmod(0o644)  # no execute bit
        orig = runner._GX_BIN
        try:
            runner._GX_BIN = bin_path
            assert runner._gx_available() is False
        finally:
            runner._GX_BIN = orig

    def test_returns_true_when_executable(self, tmp_path):
        import app.bots.ide_runner as runner
        bin_path = tmp_path / "gravitix"
        bin_path.write_bytes(b"\x7fELF")
        bin_path.chmod(0o755)
        orig = runner._GX_BIN
        try:
            runner._GX_BIN = bin_path
            assert runner._gx_available() is True
        finally:
            runner._GX_BIN = orig


class TestParseGxErrors:
    """Tests for _parse_gx_errors()."""

    def test_empty_stderr_returns_empty(self):
        from app.bots.ide_runner import _parse_gx_errors
        assert _parse_gx_errors("") == []

    def test_blank_lines_ignored(self):
        from app.bots.ide_runner import _parse_gx_errors
        result = _parse_gx_errors("\n  \n\t\n")
        assert result == []

    def test_single_error_line(self):
        from app.bots.ide_runner import _parse_gx_errors
        result = _parse_gx_errors("error[E01] at line 5: undefined variable x")
        assert len(result) == 1
        assert result[0]["msg"] == "error[E01] at line 5: undefined variable x"
        assert result[0]["line"] is None
        assert result[0]["col"] is None

    def test_multiple_error_lines(self):
        from app.bots.ide_runner import _parse_gx_errors
        stderr = "error[E01] at line 3: foo\nerror[E02] at line 7: bar\n"
        result = _parse_gx_errors(stderr)
        assert len(result) == 2
        assert result[0]["msg"] == "error[E01] at line 3: foo"
        assert result[1]["msg"] == "error[E02] at line 7: bar"

    def test_strips_whitespace(self):
        from app.bots.ide_runner import _parse_gx_errors
        result = _parse_gx_errors("  warning: unused variable  ")
        assert result[0]["msg"] == "warning: unused variable"


class TestScriptPath:
    """Tests for _script_path()."""

    def test_returns_path_in_bots_dir(self, tmp_path):
        import app.bots.ide_runner as runner
        orig = runner._BOTS_DIR
        try:
            runner._BOTS_DIR = tmp_path / "bots"
            p = runner._script_path("mybot")
            assert p == tmp_path / "bots" / "mybot.grav"
            assert (tmp_path / "bots").exists()  # mkdir was called
        finally:
            runner._BOTS_DIR = orig


# ===========================================================================
# Unit tests — compile_code
# ===========================================================================

class TestCompileCode:
    """Tests for async compile_code()."""

    def _run(self, coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def test_binary_not_found_returns_error(self):
        import app.bots.ide_runner as runner
        orig = runner._GX_BIN
        try:
            runner._GX_BIN = Path("/nonexistent/gravitix")
            result = self._run(runner.compile_code("code", "pid1"))
            assert result["ok"] is False
            assert result["errors"]
            assert "Gravitix binary not found" in result["errors"][0]["msg"]
            assert result["warnings"] == []
        finally:
            runner._GX_BIN = orig

    def test_success_returns_ok(self, tmp_path):
        import app.bots.ide_runner as runner

        bin_path = tmp_path / "gravitix"
        bin_path.write_bytes(b"#!/bin/sh\nexit 0\n")
        bin_path.chmod(0o755)

        orig_bin = runner._GX_BIN
        orig_dir = runner._BOTS_DIR
        try:
            runner._GX_BIN = bin_path
            runner._BOTS_DIR = tmp_path / "bots"
            result = self._run(runner.compile_code("on /start do\nend\n", "pid_ok"))
            assert result["ok"] is True
            assert result["errors"] == []
            assert result["warnings"] == []
        finally:
            runner._GX_BIN = orig_bin
            runner._BOTS_DIR = orig_dir

    def test_compiler_errors_returned(self, tmp_path):
        import app.bots.ide_runner as runner

        # Script that exits 1 and prints error to stderr
        bin_path = tmp_path / "gravitix"
        bin_path.write_text("#!/bin/sh\necho 'error[E01] at line 2: bad token' >&2\nexit 1\n")
        bin_path.chmod(0o755)

        orig_bin = runner._GX_BIN
        orig_dir = runner._BOTS_DIR
        try:
            runner._GX_BIN = bin_path
            runner._BOTS_DIR = tmp_path / "bots"
            result = self._run(runner.compile_code("bad code", "pid_err"))
            assert result["ok"] is False
            assert len(result["errors"]) >= 1
            assert "E01" in result["errors"][0]["msg"]
        finally:
            runner._GX_BIN = orig_bin
            runner._BOTS_DIR = orig_dir

    def test_timeout_returns_error(self, tmp_path):
        import app.bots.ide_runner as runner

        bin_path = tmp_path / "gravitix"
        bin_path.write_text("#!/bin/sh\nsleep 60\n")
        bin_path.chmod(0o755)

        orig_bin = runner._GX_BIN
        orig_dir = runner._BOTS_DIR
        orig_timeout = None

        try:
            runner._GX_BIN = bin_path
            runner._BOTS_DIR = tmp_path / "bots"

            # Patch asyncio.wait_for to simulate timeout
            async def _fake_wait_for(coro, timeout):
                raise asyncio.TimeoutError()

            with patch("asyncio.wait_for", side_effect=_fake_wait_for):
                result = self._run(runner.compile_code("code", "pid_timeout"))

            assert result["ok"] is False
            assert "timed out" in result["errors"][0]["msg"].lower()
        finally:
            runner._GX_BIN = orig_bin
            runner._BOTS_DIR = orig_dir

    def test_exception_returns_error(self, tmp_path):
        import app.bots.ide_runner as runner

        bin_path = tmp_path / "gravitix"
        bin_path.write_bytes(b"")
        bin_path.chmod(0o755)

        orig_bin = runner._GX_BIN
        orig_dir = runner._BOTS_DIR
        try:
            runner._GX_BIN = bin_path
            runner._BOTS_DIR = tmp_path / "bots"

            async def _raise(*a, **k):
                raise OSError("exec failed")

            with patch("asyncio.create_subprocess_exec", side_effect=_raise):
                result = self._run(runner.compile_code("code", "pid_exc"))

            assert result["ok"] is False
            assert "exec failed" in result["errors"][0]["msg"]
        finally:
            runner._GX_BIN = orig_bin
            runner._BOTS_DIR = orig_dir

    def test_unknown_compiler_error_fallback(self, tmp_path):
        """When stderr is empty but returncode != 0, fallback to stdout."""
        import app.bots.ide_runner as runner

        bin_path = tmp_path / "gravitix"
        bin_path.write_text("#!/bin/sh\necho 'internal fault'\nexit 1\n")
        bin_path.chmod(0o755)

        orig_bin = runner._GX_BIN
        orig_dir = runner._BOTS_DIR
        try:
            runner._GX_BIN = bin_path
            runner._BOTS_DIR = tmp_path / "bots"
            result = self._run(runner.compile_code("code", "pid_fallback"))
            assert result["ok"] is False
            assert result["errors"]
        finally:
            runner._GX_BIN = orig_bin
            runner._BOTS_DIR = orig_dir


# ===========================================================================
# Unit tests — publish_bot / stop_bot / get_status / get_logs
# ===========================================================================

class TestPublishBot:
    """Tests for async publish_bot()."""

    def _run(self, coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def _make_fake_proc(self, pid=12345, returncode=None):
        """Return a mock Popen process object."""
        proc = MagicMock(spec=subprocess.Popen)
        proc.pid = pid
        proc.returncode = returncode
        proc.poll.return_value = returncode
        proc.stdout = iter([])
        return proc

    def test_no_binary_returns_error(self):
        import app.bots.ide_runner as runner
        orig = runner._GX_BIN
        try:
            runner._GX_BIN = Path("/does/not/exist/gravitix")
            result = self._run(runner.publish_bot("pub1", "code", "tok123"))
            assert result["ok"] is False
            assert "not found" in result["error"].lower()
        finally:
            runner._GX_BIN = orig

    def test_empty_token_returns_error(self, tmp_path):
        import app.bots.ide_runner as runner
        bin_path = tmp_path / "gravitix"
        bin_path.write_bytes(b"x")
        bin_path.chmod(0o755)
        orig = runner._GX_BIN
        try:
            runner._GX_BIN = bin_path
            result = self._run(runner.publish_bot("pub2", "code", ""))
            assert result["ok"] is False
            assert "token" in result["error"].lower()
        finally:
            runner._GX_BIN = orig

    def test_success_registers_process(self, tmp_path):
        import app.bots.ide_runner as runner

        bin_path = tmp_path / "gravitix"
        bin_path.write_bytes(b"x")
        bin_path.chmod(0o755)

        fake_proc = self._make_fake_proc(pid=9999)

        orig_bin = runner._GX_BIN
        orig_dir = runner._BOTS_DIR
        orig_procs = dict(runner._procs)
        loop = asyncio.new_event_loop()
        try:
            runner._GX_BIN = bin_path
            runner._BOTS_DIR = tmp_path / "bots"
            runner._procs.clear()

            mock_asyncio = MagicMock()
            mock_loop_obj = MagicMock()
            mock_asyncio.get_event_loop.return_value = mock_loop_obj

            with patch("subprocess.Popen", return_value=fake_proc):
                with patch("app.bots.ide_runner.asyncio", mock_asyncio):
                    result = loop.run_until_complete(runner.publish_bot("pub3", "code", "tok"))

            assert result["ok"] is True
            assert result["pid"] == 9999
            assert result["error"] is None
            assert "pub3" in runner._procs
        finally:
            runner._GX_BIN = orig_bin
            runner._BOTS_DIR = orig_dir
            runner._procs.clear()
            runner._procs.update(orig_procs)
            loop.close()

    def test_stops_previous_before_publish(self, tmp_path):
        import app.bots.ide_runner as runner
        from app.bots.ide_runner import _BotProcess

        bin_path = tmp_path / "gravitix"
        bin_path.write_bytes(b"x")
        bin_path.chmod(0o755)

        # Pre-register a running process
        old_proc = self._make_fake_proc(pid=1111, returncode=None)
        old_proc.poll.return_value = None  # still running
        old_bp = _BotProcess(1111, old_proc, "pub_replace")

        new_proc = self._make_fake_proc(pid=2222)

        orig_bin = runner._GX_BIN
        orig_dir = runner._BOTS_DIR
        orig_procs = dict(runner._procs)
        try:
            runner._GX_BIN = bin_path
            runner._BOTS_DIR = tmp_path / "bots"
            runner._procs.clear()
            runner._procs["pub_replace"] = old_bp

            mock_asyncio = MagicMock()
            mock_asyncio.get_event_loop.return_value = MagicMock()
            loop = asyncio.new_event_loop()
            try:
                with patch("subprocess.Popen", return_value=new_proc):
                    with patch("app.bots.ide_runner.asyncio", mock_asyncio):
                        result = loop.run_until_complete(
                            runner.publish_bot("pub_replace", "code", "tok")
                        )
            finally:
                loop.close()

            # Old process should have been terminated
            old_proc.terminate.assert_called_once()
            assert result["ok"] is True
            assert runner._procs["pub_replace"].pid == 2222
        finally:
            runner._GX_BIN = orig_bin
            runner._BOTS_DIR = orig_dir
            runner._procs.clear()
            runner._procs.update(orig_procs)

    def test_popen_exception_returns_error(self, tmp_path):
        import app.bots.ide_runner as runner

        bin_path = tmp_path / "gravitix"
        bin_path.write_bytes(b"x")
        bin_path.chmod(0o755)

        orig_bin = runner._GX_BIN
        orig_dir = runner._BOTS_DIR
        orig_procs = dict(runner._procs)
        try:
            runner._GX_BIN = bin_path
            runner._BOTS_DIR = tmp_path / "bots"
            runner._procs.clear()

            mock_asyncio = MagicMock()
            mock_asyncio.get_event_loop.return_value = MagicMock()
            loop = asyncio.new_event_loop()
            try:
                with patch("subprocess.Popen", side_effect=OSError("no such file")):
                    with patch("app.bots.ide_runner.asyncio", mock_asyncio):
                        result = loop.run_until_complete(
                            runner.publish_bot("pub_exc", "code", "tok")
                        )
            finally:
                loop.close()

            assert result["ok"] is False
            assert "no such file" in result["error"]
        finally:
            runner._GX_BIN = orig_bin
            runner._BOTS_DIR = orig_dir
            runner._procs.clear()
            runner._procs.update(orig_procs)


class TestStopBot:
    """Tests for async stop_bot()."""

    def _run(self, coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def _make_fake_proc(self, running=True):
        proc = MagicMock(spec=subprocess.Popen)
        proc.pid = 5555
        proc.poll.return_value = None if running else 0
        return proc

    def test_stop_nonexistent_returns_not_running(self):
        import app.bots.ide_runner as runner
        runner._procs.pop("no_such", None)
        result = self._run(runner.stop_bot("no_such"))
        assert result["ok"] is True
        assert result["was_running"] is False

    def test_stop_running_process(self):
        import app.bots.ide_runner as runner
        from app.bots.ide_runner import _BotProcess

        proc = self._make_fake_proc(running=True)
        bp = _BotProcess(proc.pid, proc, "stop_me")
        runner._procs["stop_me"] = bp

        result = self._run(runner.stop_bot("stop_me"))

        assert result["ok"] is True
        assert result["was_running"] is True
        proc.terminate.assert_called_once()
        assert "stop_me" not in runner._procs

    def test_stop_kills_after_timeout(self):
        import app.bots.ide_runner as runner
        from app.bots.ide_runner import _BotProcess

        proc = self._make_fake_proc(running=True)
        proc.wait.side_effect = subprocess.TimeoutExpired("gravitix", 5)
        bp = _BotProcess(proc.pid, proc, "kill_me")
        runner._procs["kill_me"] = bp

        result = self._run(runner.stop_bot("kill_me"))

        assert result["ok"] is True
        proc.kill.assert_called_once()

    def test_stop_already_dead_process(self):
        import app.bots.ide_runner as runner
        from app.bots.ide_runner import _BotProcess

        proc = self._make_fake_proc(running=False)
        bp = _BotProcess(proc.pid, proc, "dead_bot")
        runner._procs["dead_bot"] = bp

        result = self._run(runner.stop_bot("dead_bot"))

        assert result["ok"] is True
        # terminate should NOT have been called since poll() != None
        proc.terminate.assert_not_called()


class TestGetStatus:
    """Tests for get_status()."""

    def _make_bp(self, pid=777, running=True, returncode=0):
        import app.bots.ide_runner as runner
        from app.bots.ide_runner import _BotProcess
        proc = MagicMock(spec=subprocess.Popen)
        proc.pid = pid
        proc.poll.return_value = None if running else returncode
        proc.returncode = returncode
        return _BotProcess(pid, proc, "proj")

    def test_stopped_project(self):
        import app.bots.ide_runner as runner
        runner._procs.pop("gs_absent", None)
        result = runner.get_status("gs_absent")
        assert result["status"] == "stopped"
        assert result["pid"] is None
        assert result["uptime"] is None

    def test_running_project(self):
        import app.bots.ide_runner as runner
        bp = self._make_bp(pid=888, running=True)
        runner._procs["gs_run"] = bp
        try:
            result = runner.get_status("gs_run")
            assert result["status"] == "running"
            assert result["pid"] == 888
            assert isinstance(result["uptime"], int)
            assert result["uptime"] >= 0
        finally:
            runner._procs.pop("gs_run", None)

    def test_crashed_project(self):
        import app.bots.ide_runner as runner
        bp = self._make_bp(pid=999, running=False, returncode=1)
        runner._procs["gs_crash"] = bp
        result = runner.get_status("gs_crash")
        assert result["status"] == "crashed"
        assert result["pid"] == 999
        assert result["exit_code"] == 1
        assert "gs_crash" not in runner._procs  # cleaned up


class TestGetLogs:
    """Tests for get_logs()."""

    def _make_bp(self, logs: list):
        from app.bots.ide_runner import _BotProcess
        proc = MagicMock(spec=subprocess.Popen)
        proc.pid = 1234
        proc.poll.return_value = None
        bp = _BotProcess(1234, proc, "log_proj")
        bp.logs = list(logs)
        return bp

    def test_no_process_returns_empty(self):
        import app.bots.ide_runner as runner
        runner._procs.pop("log_absent", None)
        assert runner.get_logs("log_absent") == []

    def test_returns_last_n_lines(self):
        import app.bots.ide_runner as runner
        logs = [f"line {i}" for i in range(200)]
        bp = self._make_bp(logs)
        runner._procs["log_proj"] = bp
        try:
            result = runner.get_logs("log_proj", last_n=10)
            assert result == logs[-10:]
            assert len(result) == 10
        finally:
            runner._procs.pop("log_proj", None)

    def test_returns_all_when_fewer_than_n(self):
        import app.bots.ide_runner as runner
        logs = ["a", "b", "c"]
        bp = self._make_bp(logs)
        runner._procs["log_proj2"] = bp
        try:
            result = runner.get_logs("log_proj2", last_n=100)
            assert result == ["a", "b", "c"]
        finally:
            runner._procs.pop("log_proj2", None)

    def test_default_last_n(self):
        import app.bots.ide_runner as runner
        logs = [f"line {i}" for i in range(200)]
        bp = self._make_bp(logs)
        runner._procs["log_def"] = bp
        try:
            result = runner.get_logs("log_def")  # default=100
            assert len(result) == 100
            assert result == logs[-100:]
        finally:
            runner._procs.pop("log_def", None)


class TestCollectLogs:
    """Tests for _collect_logs() background thread."""

    def test_collects_stdout_lines(self):
        import app.bots.ide_runner as runner
        from app.bots.ide_runner import _BotProcess, _collect_logs
        import io

        lines = [f"log line {i}\n" for i in range(5)]
        proc = MagicMock(spec=subprocess.Popen)
        proc.pid = 4242
        proc.stdout = iter(lines)
        bp = _BotProcess(4242, proc, "cl_proj")
        runner._procs["cl_proj"] = bp

        try:
            _collect_logs("cl_proj")
            assert bp.logs == [f"log line {i}" for i in range(5)]
        finally:
            runner._procs.pop("cl_proj", None)

    def test_trims_log_buffer_at_500(self):
        import app.bots.ide_runner as runner
        from app.bots.ide_runner import _BotProcess, _collect_logs

        lines = [f"line {i}\n" for i in range(600)]
        proc = MagicMock(spec=subprocess.Popen)
        proc.pid = 5050
        proc.stdout = iter(lines)
        bp = _BotProcess(5050, proc, "cl_trim")
        runner._procs["cl_trim"] = bp

        try:
            _collect_logs("cl_trim")
            assert len(bp.logs) <= 500
        finally:
            runner._procs.pop("cl_trim", None)

    def test_missing_project_does_not_crash(self):
        from app.bots.ide_runner import _collect_logs
        # Should silently return without error
        _collect_logs("nonexistent_proj_xyz")


# ===========================================================================
# Integration tests — API endpoints
# ===========================================================================

class TestIDEAuth:
    """All endpoints require authentication."""

    def test_compile_requires_auth(self, client: SyncASGIClient, anon_client: SyncASGIClient):
        r = anon_client.post("/api/ide/compile", json={
            "project_id": "proj1",
            "code": "on /start do\nend\n",
        })
        assert r.status_code in (401, 403)

    def test_publish_requires_auth(self, client: SyncASGIClient, anon_client: SyncASGIClient):
        r = anon_client.post("/api/ide/publish", json={
            "project_id": "proj1",
            "code": "code",
            "token": "tok",
        })
        assert r.status_code in (401, 403)

    def test_status_requires_auth(self, client: SyncASGIClient, anon_client: SyncASGIClient):
        r = anon_client.get("/api/ide/status/proj1")
        assert r.status_code in (401, 403)

    def test_logs_requires_auth(self, client: SyncASGIClient, anon_client: SyncASGIClient):
        r = anon_client.get("/api/ide/logs/proj1")
        assert r.status_code in (401, 403)

    def test_stop_requires_auth(self, client: SyncASGIClient, anon_client: SyncASGIClient):
        r = anon_client.post("/api/ide/stop/proj1")
        assert r.status_code in (401, 403)


class TestIDECompile:
    """POST /api/ide/compile"""

    def test_compile_without_binary_returns_error(self, client: SyncASGIClient):
        headers = _auth_headers(client, "comp1")
        import app.bots.ide_runner as runner
        orig = runner._GX_BIN
        try:
            runner._GX_BIN = Path("/nonexistent/gravitix")
            r = client.post("/api/ide/compile", json={
                "project_id": VALID_PID,
                "code": VALID_CODE,
            }, headers=headers)
            assert r.status_code == 200
            data = r.json()
            assert data["ok"] is False
            assert data["errors"]
        finally:
            runner._GX_BIN = orig

    def test_compile_success(self, client: SyncASGIClient, tmp_path):
        headers = _auth_headers(client, "comp2")
        import app.bots.ide_runner as runner

        bin_path = tmp_path / "gravitix"
        bin_path.write_bytes(b"#!/bin/sh\nexit 0\n")
        bin_path.chmod(0o755)

        orig_bin = runner._GX_BIN
        orig_dir = runner._BOTS_DIR
        try:
            runner._GX_BIN = bin_path
            runner._BOTS_DIR = tmp_path / "bots"

            r = client.post("/api/ide/compile", json={
                "project_id": VALID_PID,
                "code": VALID_CODE,
            }, headers=headers)

            assert r.status_code == 200
            data = r.json()
            assert data["ok"] is True
            assert data["errors"] == []
        finally:
            runner._GX_BIN = orig_bin
            runner._BOTS_DIR = orig_dir

    def test_compile_with_errors(self, client: SyncASGIClient, tmp_path):
        headers = _auth_headers(client, "comp3")
        import app.bots.ide_runner as runner

        bin_path = tmp_path / "gravitix"
        bin_path.write_text("#!/bin/sh\necho 'error[E01] at line 1: bad token' >&2\nexit 1\n")
        bin_path.chmod(0o755)

        orig_bin = runner._GX_BIN
        orig_dir = runner._BOTS_DIR
        try:
            runner._GX_BIN = bin_path
            runner._BOTS_DIR = tmp_path / "bots"

            r = client.post("/api/ide/compile", json={
                "project_id": VALID_PID,
                "code": INVALID_CODE,
            }, headers=headers)

            assert r.status_code == 200
            data = r.json()
            assert data["ok"] is False
            assert len(data["errors"]) >= 1
        finally:
            runner._GX_BIN = orig_bin
            runner._BOTS_DIR = orig_dir

    def test_compile_invalid_project_id_rejected(self, client: SyncASGIClient):
        headers = _auth_headers(client, "comp4")
        # WAF may reject path-traversal sequences before the handler (→ 403),
        # or the handler itself rejects them (→ 400). Both mean "rejected".
        r = client.post("/api/ide/compile", json={
            "project_id": "bad@id",
            "code": VALID_CODE,
        }, headers=headers)
        assert r.status_code in (400, 403)

    def test_compile_empty_project_id_rejected(self, client: SyncASGIClient):
        headers = _auth_headers(client, "comp5")
        r = client.post("/api/ide/compile", json={
            "project_id": "",
            "code": VALID_CODE,
        }, headers=headers)
        assert r.status_code == 422  # Pydantic min_length validation

    def test_compile_oversized_code_rejected(self, client: SyncASGIClient):
        headers = _auth_headers(client, "comp6")
        r = client.post("/api/ide/compile", json={
            "project_id": VALID_PID,
            "code": "x" * 600_000,  # exceeds 500k limit
        }, headers=headers)
        assert r.status_code == 422

    def test_compile_project_id_too_long_rejected(self, client: SyncASGIClient):
        headers = _auth_headers(client, "comp7")
        r = client.post("/api/ide/compile", json={
            "project_id": "a" * 65,
            "code": VALID_CODE,
        }, headers=headers)
        assert r.status_code == 422

    def test_compile_special_chars_in_id_rejected(self, client: SyncASGIClient):
        headers = _auth_headers(client, "comp8")
        # Characters outside [a-zA-Z0-9_-] must be rejected.
        # WAF may intercept some (→ 403) before _validate_id (→ 400).
        for bad_id in ["proj;cmd", "proj@foo", "proj|pipe", "proj space"]:
            r = client.post("/api/ide/compile", json={
                "project_id": bad_id,
                "code": VALID_CODE,
            }, headers=headers)
            assert r.status_code in (400, 403), \
                f"Expected 400/403 for id={bad_id!r}, got {r.status_code}"

    def test_compile_valid_id_formats(self, client: SyncASGIClient):
        """IDs with letters, digits, underscores, hyphens are all valid."""
        headers = _auth_headers(client, "comp9")
        import app.bots.ide_runner as runner
        orig = runner._GX_BIN
        try:
            runner._GX_BIN = Path("/nonexistent/gravitix")
            for good_id in ["proj1", "my-bot", "bot_v2", "ABC123", "a"]:
                r = client.post("/api/ide/compile", json={
                    "project_id": good_id,
                    "code": VALID_CODE,
                }, headers=headers)
                # Should reach the handler (not 400/422)
                assert r.status_code in (200, 422), f"id={good_id!r} got {r.status_code}"
        finally:
            runner._GX_BIN = orig


class TestIDEPublish:
    """POST /api/ide/publish"""

    def test_publish_without_binary_returns_422(self, client: SyncASGIClient):
        headers = _auth_headers(client, "pub1")
        import app.bots.ide_runner as runner
        orig = runner._GX_BIN
        try:
            runner._GX_BIN = Path("/nonexistent/gravitix")
            r = client.post("/api/ide/publish", json={
                "project_id": VALID_PID,
                "code": VALID_CODE,
                "token": "my_bot_token_123",
            }, headers=headers)
            assert r.status_code == 422
        finally:
            runner._GX_BIN = orig

    def test_publish_success(self, client: SyncASGIClient, tmp_path):
        headers = _auth_headers(client, "pub2")
        import app.bots.ide_runner as runner

        bin_path = tmp_path / "gravitix"
        bin_path.write_bytes(b"x")
        bin_path.chmod(0o755)

        fake_proc = MagicMock(spec=subprocess.Popen)
        fake_proc.pid = 7777
        fake_proc.poll.return_value = None
        fake_proc.stdout = iter([])

        orig_bin = runner._GX_BIN
        orig_dir = runner._BOTS_DIR
        orig_procs = dict(runner._procs)
        try:
            runner._GX_BIN = bin_path
            runner._BOTS_DIR = tmp_path / "bots"
            runner._procs.clear()

            mock_asyncio = MagicMock()
            mock_asyncio.get_event_loop.return_value = MagicMock()
            with patch("subprocess.Popen", return_value=fake_proc):
                with patch("app.bots.ide_runner.asyncio", mock_asyncio):
                    r = client.post("/api/ide/publish", json={
                        "project_id": "pub_proj",
                        "code": VALID_CODE,
                        "token": "real_token_abc",
                    }, headers=headers)

            assert r.status_code == 200
            data = r.json()
            assert data["ok"] is True
            assert data["pid"] == 7777
        finally:
            runner._GX_BIN = orig_bin
            runner._BOTS_DIR = orig_dir
            runner._procs.clear()
            runner._procs.update(orig_procs)

    def test_publish_invalid_project_id(self, client: SyncASGIClient):
        headers = _auth_headers(client, "pub3")
        r = client.post("/api/ide/publish", json={
            "project_id": "bad@path",
            "code": VALID_CODE,
            "token": "tok",
        }, headers=headers)
        assert r.status_code in (400, 403)

    def test_publish_missing_token_field_rejected(self, client: SyncASGIClient):
        headers = _auth_headers(client, "pub4")
        r = client.post("/api/ide/publish", json={
            "project_id": VALID_PID,
            "code": VALID_CODE,
            # token missing
        }, headers=headers)
        assert r.status_code == 422

    def test_publish_empty_token_rejected_by_pydantic(self, client: SyncASGIClient):
        """Pydantic min_length=1 rejects empty token before it even reaches runner."""
        headers = _auth_headers(client, "pub5")
        r = client.post("/api/ide/publish", json={
            "project_id": VALID_PID,
            "code": VALID_CODE,
            "token": "",
        }, headers=headers)
        assert r.status_code == 422

    def test_publish_oversized_code_rejected(self, client: SyncASGIClient):
        headers = _auth_headers(client, "pub6")
        r = client.post("/api/ide/publish", json={
            "project_id": VALID_PID,
            "code": "x" * 600_000,
            "token": "tok",
        }, headers=headers)
        assert r.status_code == 422

    def test_publish_token_too_long_rejected(self, client: SyncASGIClient):
        headers = _auth_headers(client, "pub7")
        r = client.post("/api/ide/publish", json={
            "project_id": VALID_PID,
            "code": VALID_CODE,
            "token": "t" * 121,  # exceeds max_length=120
        }, headers=headers)
        assert r.status_code == 422


class TestIDEStatus:
    """GET /api/ide/status/{project_id}"""

    def test_status_stopped_project(self, client: SyncASGIClient):
        headers = _auth_headers(client, "stat1")
        import app.bots.ide_runner as runner
        runner._procs.pop("status_test", None)

        r = client.get("/api/ide/status/status_test", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "stopped"
        assert data["pid"] is None

    def test_status_running_project(self, client: SyncASGIClient):
        headers = _auth_headers(client, "stat2")
        import app.bots.ide_runner as runner
        from app.bots.ide_runner import _BotProcess

        proc = MagicMock(spec=subprocess.Popen)
        proc.pid = 4242
        proc.poll.return_value = None
        bp = _BotProcess(4242, proc, "status_run")
        runner._procs["status_run"] = bp

        try:
            r = client.get("/api/ide/status/status_run", headers=headers)
            assert r.status_code == 200
            data = r.json()
            assert data["status"] == "running"
            assert data["pid"] == 4242
            assert "uptime" in data
        finally:
            runner._procs.pop("status_run", None)

    def test_status_invalid_id(self, client: SyncASGIClient):
        headers = _auth_headers(client, "stat3")
        # Use a single path segment with invalid chars (@ is not in [a-zA-Z0-9_-])
        r = client.get("/api/ide/status/bad@id", headers=headers)
        assert r.status_code in (400, 403)

    def test_status_id_with_spaces_rejected(self, client: SyncASGIClient):
        headers = _auth_headers(client, "stat4")
        r = client.get("/api/ide/status/bad id", headers=headers)
        assert r.status_code in (400, 422)


class TestIDELogs:
    """GET /api/ide/logs/{project_id}"""

    def test_logs_no_process(self, client: SyncASGIClient):
        headers = _auth_headers(client, "log1")
        import app.bots.ide_runner as runner
        runner._procs.pop("log_test", None)

        r = client.get("/api/ide/logs/log_test", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert data["logs"] == []

    def test_logs_with_process(self, client: SyncASGIClient):
        headers = _auth_headers(client, "log2")
        import app.bots.ide_runner as runner
        from app.bots.ide_runner import _BotProcess

        proc = MagicMock(spec=subprocess.Popen)
        proc.pid = 3131
        bp = _BotProcess(3131, proc, "log_run")
        bp.logs = ["line 1", "line 2", "line 3"]
        runner._procs["log_run"] = bp

        try:
            r = client.get("/api/ide/logs/log_run", headers=headers)
            assert r.status_code == 200
            data = r.json()
            assert data["logs"] == ["line 1", "line 2", "line 3"]
        finally:
            runner._procs.pop("log_run", None)

    def test_logs_n_param_capped_at_500(self, client: SyncASGIClient):
        headers = _auth_headers(client, "log3")
        import app.bots.ide_runner as runner
        from app.bots.ide_runner import _BotProcess

        proc = MagicMock(spec=subprocess.Popen)
        proc.pid = 6161
        bp = _BotProcess(6161, proc, "log_cap")
        bp.logs = [f"l{i}" for i in range(600)]
        runner._procs["log_cap"] = bp

        try:
            # n=9999 should be capped to 500
            r = client.get("/api/ide/logs/log_cap?n=9999", headers=headers)
            assert r.status_code == 200
            data = r.json()
            assert len(data["logs"]) <= 500
        finally:
            runner._procs.pop("log_cap", None)

    def test_logs_default_n(self, client: SyncASGIClient):
        headers = _auth_headers(client, "log4")
        import app.bots.ide_runner as runner
        from app.bots.ide_runner import _BotProcess

        proc = MagicMock(spec=subprocess.Popen)
        proc.pid = 7272
        bp = _BotProcess(7272, proc, "log_def")
        bp.logs = [f"line {i}" for i in range(200)]
        runner._procs["log_def"] = bp

        try:
            r = client.get("/api/ide/logs/log_def", headers=headers)
            assert r.status_code == 200
            data = r.json()
            assert len(data["logs"]) == 100  # default n=100
        finally:
            runner._procs.pop("log_def", None)

    def test_logs_invalid_id(self, client: SyncASGIClient):
        headers = _auth_headers(client, "log5")
        # Single segment with invalid char so URL isn't normalized away
        r = client.get("/api/ide/logs/bad@id", headers=headers)
        assert r.status_code in (400, 403)


class TestIDEStop:
    """POST /api/ide/stop/{project_id}"""

    def test_stop_nonexistent_returns_ok(self, client: SyncASGIClient):
        headers = _auth_headers(client, "stop1")
        import app.bots.ide_runner as runner
        runner._procs.pop("stop_absent", None)

        r = client.post("/api/ide/stop/stop_absent", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["was_running"] is False

    def test_stop_running_process(self, client: SyncASGIClient):
        headers = _auth_headers(client, "stop2")
        import app.bots.ide_runner as runner
        from app.bots.ide_runner import _BotProcess

        proc = MagicMock(spec=subprocess.Popen)
        proc.pid = 8888
        proc.poll.return_value = None  # running
        bp = _BotProcess(8888, proc, "stop_run")
        runner._procs["stop_run"] = bp

        r = client.post("/api/ide/stop/stop_run", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["was_running"] is True
        proc.terminate.assert_called_once()

    def test_stop_invalid_id(self, client: SyncASGIClient):
        headers = _auth_headers(client, "stop3")
        r = client.post("/api/ide/stop/bad;id", headers=headers)
        assert r.status_code == 400


# ===========================================================================
# Edge cases and security
# ===========================================================================

class TestIDEEdgeCases:

    def test_compile_empty_code_passes_pydantic(self, client: SyncASGIClient):
        """Empty string is valid from Pydantic (no min_length on code)."""
        headers = _auth_headers(client, "edge1")
        import app.bots.ide_runner as runner
        orig = runner._GX_BIN
        try:
            runner._GX_BIN = Path("/nonexistent/gravitix")
            r = client.post("/api/ide/compile", json={
                "project_id": VALID_PID,
                "code": "",
            }, headers=headers)
            assert r.status_code == 200
            assert r.json()["ok"] is False
        finally:
            runner._GX_BIN = orig

    def test_concurrent_publish_replaces_old(self, client: SyncASGIClient, tmp_path):
        """Second publish to same project_id stops first and starts new."""
        headers = _auth_headers(client, "edge2")
        import app.bots.ide_runner as runner
        from app.bots.ide_runner import _BotProcess

        bin_path = tmp_path / "gravitix"
        bin_path.write_bytes(b"x")
        bin_path.chmod(0o755)

        old_proc = MagicMock(spec=subprocess.Popen)
        old_proc.pid = 1001
        old_proc.poll.return_value = None
        old_proc.stdout = iter([])
        old_bp = _BotProcess(1001, old_proc, "conc_proj")

        new_proc = MagicMock(spec=subprocess.Popen)
        new_proc.pid = 1002
        new_proc.poll.return_value = None
        new_proc.stdout = iter([])

        orig_bin = runner._GX_BIN
        orig_dir = runner._BOTS_DIR
        orig_procs = dict(runner._procs)
        try:
            runner._GX_BIN = bin_path
            runner._BOTS_DIR = tmp_path / "bots"
            runner._procs.clear()
            runner._procs["conc_proj"] = old_bp

            mock_asyncio = MagicMock()
            mock_asyncio.get_event_loop.return_value = MagicMock()
            with patch("subprocess.Popen", return_value=new_proc):
                with patch("app.bots.ide_runner.asyncio", mock_asyncio):
                    r = client.post("/api/ide/publish", json={
                        "project_id": "conc_proj",
                        "code": VALID_CODE,
                        "token": "tok",
                    }, headers=headers)

            assert r.status_code == 200
            assert r.json()["pid"] == 1002
            old_proc.terminate.assert_called_once()
        finally:
            runner._GX_BIN = orig_bin
            runner._BOTS_DIR = orig_dir
            runner._procs.clear()
            runner._procs.update(orig_procs)

    def test_status_after_crash_cleans_up(self, client: SyncASGIClient):
        headers = _auth_headers(client, "edge3")
        import app.bots.ide_runner as runner
        from app.bots.ide_runner import _BotProcess

        proc = MagicMock(spec=subprocess.Popen)
        proc.pid = 9999
        proc.poll.return_value = 137  # killed
        proc.returncode = 137
        bp = _BotProcess(9999, proc, "crash_proj")
        runner._procs["crash_proj"] = bp

        r = client.get("/api/ide/status/crash_proj", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "crashed"
        assert data["exit_code"] == 137
        assert "crash_proj" not in runner._procs

    def test_logs_n_param_zero(self, client: SyncASGIClient):
        """n=0 → last_n=min(0,500)=0 → logs[-0:] = logs[0:] (all items in Python)."""
        headers = _auth_headers(client, "edge4")
        import app.bots.ide_runner as runner
        from app.bots.ide_runner import _BotProcess

        proc = MagicMock(spec=subprocess.Popen)
        proc.pid = 1212
        bp = _BotProcess(1212, proc, "edge_log")
        bp.logs = ["a", "b", "c"]
        runner._procs["edge_log"] = bp

        try:
            r = client.get("/api/ide/logs/edge_log?n=0", headers=headers)
            assert r.status_code == 200
            data = r.json()
            # Python: list[-0:] == list[0:] == all items
            assert data["logs"] == ["a", "b", "c"]
        finally:
            runner._procs.pop("edge_log", None)

    def test_publish_code_written_to_disk(self, tmp_path):
        """publish_bot writes the code to the .grav file."""
        import app.bots.ide_runner as runner
        from unittest.mock import patch
        import asyncio

        bin_path = tmp_path / "gravitix"
        bin_path.write_bytes(b"x")
        bin_path.chmod(0o755)

        fake_proc = MagicMock(spec=subprocess.Popen)
        fake_proc.pid = 5555
        fake_proc.poll.return_value = None
        fake_proc.stdout = iter([])

        orig_bin = runner._GX_BIN
        orig_dir = runner._BOTS_DIR
        orig_procs = dict(runner._procs)
        try:
            runner._GX_BIN = bin_path
            runner._BOTS_DIR = tmp_path / "bots"
            runner._procs.clear()

            code = "on /hello do\n    send 'world'\nend\n"

            mock_asyncio = MagicMock()
            mock_asyncio.get_event_loop.return_value = MagicMock()
            loop = asyncio.new_event_loop()
            try:
                with patch("subprocess.Popen", return_value=fake_proc):
                    with patch("app.bots.ide_runner.asyncio", mock_asyncio):
                        result = loop.run_until_complete(
                            runner.publish_bot("disk_test", code, "tok")
                        )
            finally:
                loop.close()

            script_file = tmp_path / "bots" / "disk_test.grav"
            assert script_file.exists()
            assert script_file.read_text() == code
        finally:
            runner._GX_BIN = orig_bin
            runner._BOTS_DIR = orig_dir
            runner._procs.clear()
            runner._procs.update(orig_procs)

    def test_compile_code_written_to_disk(self, tmp_path):
        """compile_code writes code to disk before invoking binary."""
        import app.bots.ide_runner as runner

        bin_path = tmp_path / "gravitix"
        bin_path.write_bytes(b"#!/bin/sh\nexit 0\n")
        bin_path.chmod(0o755)

        orig_bin = runner._GX_BIN
        orig_dir = runner._BOTS_DIR
        try:
            runner._GX_BIN = bin_path
            runner._BOTS_DIR = tmp_path / "bots"

            code = "on /test do\n    send 'ok'\nend\n"
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(runner.compile_code(code, "write_test"))
            loop.close()

            script_file = tmp_path / "bots" / "write_test.grav"
            assert script_file.exists()
            assert script_file.read_text() == code
        finally:
            runner._GX_BIN = orig_bin
            runner._BOTS_DIR = orig_dir


# ===========================================================================
# BotProcess dataclass tests
# ===========================================================================

class TestBotProcess:
    """Tests for _BotProcess internals."""

    def test_started_at_is_recent(self):
        from app.bots.ide_runner import _BotProcess
        before = time.time()
        proc = MagicMock(spec=subprocess.Popen)
        proc.pid = 1
        bp = _BotProcess(1, proc, "proj")
        after = time.time()
        assert before <= bp.started_at <= after

    def test_logs_initially_empty(self):
        from app.bots.ide_runner import _BotProcess
        proc = MagicMock(spec=subprocess.Popen)
        proc.pid = 2
        bp = _BotProcess(2, proc, "proj2")
        assert bp.logs == []

    def test_stores_project_id(self):
        from app.bots.ide_runner import _BotProcess
        proc = MagicMock(spec=subprocess.Popen)
        proc.pid = 3
        bp = _BotProcess(3, proc, "my_project")
        assert bp.project_id == "my_project"
        assert bp.pid == 3


# ===========================================================================
# Request model validation tests
# ===========================================================================

class TestRequestModels:
    """Pydantic model validation for CompileRequest and PublishRequest."""

    def test_compile_request_valid(self):
        from app.bots.ide_routes import CompileRequest
        req = CompileRequest(project_id="my_proj", code="some code")
        assert req.project_id == "my_proj"
        assert req.code == "some code"

    def test_compile_request_empty_id(self):
        from app.bots.ide_routes import CompileRequest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            CompileRequest(project_id="", code="code")

    def test_compile_request_id_too_long(self):
        from app.bots.ide_routes import CompileRequest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            CompileRequest(project_id="a" * 65, code="code")

    def test_compile_request_code_too_long(self):
        from app.bots.ide_routes import CompileRequest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            CompileRequest(project_id="proj", code="x" * 500_001)

    def test_publish_request_valid(self):
        from app.bots.ide_routes import PublishRequest
        req = PublishRequest(project_id="p", code="c", token="t")
        assert req.token == "t"

    def test_publish_request_empty_token(self):
        from app.bots.ide_routes import PublishRequest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            PublishRequest(project_id="proj", code="code", token="")

    def test_publish_request_token_too_long(self):
        from app.bots.ide_routes import PublishRequest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            PublishRequest(project_id="proj", code="code", token="t" * 121)

    def test_validate_id_accepts_valid(self):
        from app.bots.ide_routes import _validate_id
        assert _validate_id("my_project-01") == "my_project-01"
        assert _validate_id("ABC") == "ABC"
        assert _validate_id("a1-b2_c3") == "a1-b2_c3"

    def test_validate_id_rejects_invalid(self):
        from app.bots.ide_routes import _validate_id
        from fastapi import HTTPException
        for bad in ["../etc", "proj;rm", "p q", "p@q", "p/q"]:
            with pytest.raises(HTTPException) as exc_info:
                _validate_id(bad)
            assert exc_info.value.status_code == 400
