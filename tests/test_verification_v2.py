"""Real Git and owned-process regressions for verification identity and capture."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import yaml
from test_scaffold import git_init, project_copy, quiet_call, run_git, set_full

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import _process
import _common as c
import _git as g
import _evidence
import _workspace
import ledger
import prompt
import verify


def awaiting(root, command):
    project_copy(root)
    set_full(root, command)
    git_init(root)
    run_git(root, "add", ".")
    run_git(root, "commit", "-qm", "baseline")
    prompt.coding(root, "M001-S01")
    (root / "07_app/product.txt").write_text("before\n", encoding="utf-8")
    if quiet_call(ledger.main, ["--root", str(root), "coded", "M001-S01"]):
        raise AssertionError("fixture could not record coding")


class VerificationIdentityTests(unittest.TestCase):
    def test_v2_verifier_uses_frozen_command_after_roadmap_edit(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            awaiting(root, "raise SystemExit(7)")
            plan = root / "roadmap.yaml"
            rm = yaml.safe_load(plan.read_text(encoding="utf-8"))
            rm["verification"]["full"] = ["python", "-c", "print('replacement command')"]
            plan.write_text(yaml.safe_dump(rm, sort_keys=False), encoding="utf-8")
            receipt, _ = verify.run(root, "M001-S01", 10)
            self.assertEqual(receipt["schema"], "frutlups.receipt/2")
            self.assertFalse(receipt["ok"])
            self.assertEqual(receipt["commands"][0]["exit"], 7)
            self.assertEqual(receipt["commands"][0]["argv"][1:], ["-c", "raise SystemExit(7)"])
            self.assertTrue(receipt["witness"]["stable"])
            self.assertEqual(receipt["witness"]["before"], receipt["witness"]["after"])
            self.assertNotIn("changed_files", receipt)

    def test_dirty_content_index_head_and_new_file_are_witnessed(self):
        cases = [
            ("pass", True),
            ("from pathlib import Path;Path('07_app/product.txt').write_text('after\\n')", False),
            (
                "import subprocess;subprocess.run(['git','add','07_app/product.txt'],check=True)",
                False,
            ),
            ("from pathlib import Path;Path('new.txt').write_text('new')", False),
            (
                "import subprocess;"
                "subprocess.run(['git','commit','--allow-empty','-m','moved'],check=True)",
                False,
            ),
        ]
        for command, expected in cases:
            with self.subTest(command=command), tempfile.TemporaryDirectory() as name:
                root = Path(name)
                awaiting(root, command)
                before = verify.c.status_bytes(root)
                receipt, _ = verify.run(root, "M001-S01", 10)
                self.assertEqual(receipt["ok"], expected)
                self.assertTrue(receipt["tree_dirty_before"])
                self.assertFalse(receipt["tree_clean_after"])
                if "write_text('after" in command:
                    # Porcelain alone cannot distinguish this mutation.
                    after = verify.c.status_bytes(root)
                    self.assertIn(b"07_app/product.txt", before)
                    self.assertIn(b"07_app/product.txt", after)

    def test_snapshot_includes_raw_content_index_flags_and_excludes_ignored_stores(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            git_init(root)
            (root / ".gitignore").write_text("cache/\n")
            product = root / "product.txt"
            product.write_bytes(b"raw\r\n")
            run_git(root, "add", ".")
            run_git(root, "commit", "-qm", "baseline")
            before = _workspace.snapshot(root)
            (root / "cache").mkdir()
            (root / "cache/deep").mkdir()
            (root / "cache/deep/private.txt").write_text("ignored")
            self.assertEqual(before, _workspace.snapshot(root))
            product.write_bytes(b"raw\n")
            changed = _workspace.snapshot(root)
            self.assertNotEqual(before["files"], changed["files"])
            run_git(root, "update-index", "--assume-unchanged", "product.txt")
            self.assertNotEqual(changed["index"], _workspace.snapshot(root)["index"])

    def test_snapshot_records_symlink_without_reading_target(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            git_init(root)
            (root / "baseline").write_text("x")
            run_git(root, "add", ".")
            run_git(root, "commit", "-qm", "baseline")
            try:
                os.symlink("missing one", root / "link")
            except OSError as exc:
                self.skipTest(f"symlinks unavailable: {exc}")
            first = _workspace.snapshot(root)["files"]["link"]
            self.assertEqual(first["kind"], "symlink")
            (root / "link").unlink()
            os.symlink("missing two", root / "link")
            self.assertNotEqual(first, _workspace.snapshot(root)["files"]["link"])


class VerificationProcessTests(unittest.TestCase):
    def test_output_flood_retains_bounded_complete_failure_tails(self):
        code = (
            "import os;os.write(1,b'x'*2000000+b'\\nstdout end\\n');"
            "os.write(2,b'y'*2000000+b'\\nstderr end\\n')"
        )
        result = _process.run([sys.executable, "-c", code], cwd=Path.cwd(), timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertFalse(result.timed_out)
        self.assertEqual(result.stdout_bytes, 2000012)
        self.assertEqual(result.stderr_bytes, 2000012)
        self.assertEqual(result.stdout, b"stdout end\n")
        self.assertEqual(result.stderr, b"stderr end\n")
        head = _process.run(
            [sys.executable, "-c", code], cwd=Path.cwd(), timeout=10, tail_limit=32, keep="head"
        )
        self.assertEqual(head.stdout, b"x" * 32)
        self.assertEqual(head.stdout_bytes, 2000012)

    def test_timeout_removes_owned_grandchild_and_preserves_unrelated_process(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            marker, other = root / "child-marker", root / "other-marker"
            child = "import pathlib,sys,time;time.sleep(1.2);pathlib.Path(sys.argv[1]).touch()"
            unrelated = subprocess.Popen([sys.executable, "-c", child, str(other)])
            code = (
                "import subprocess,sys,time;"
                "subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2]]);time.sleep(30)"
            )
            try:
                result = _process.run(
                    [sys.executable, "-c", code, child, str(marker)], cwd=root, timeout=0.5
                )
                self.assertTrue(result.timed_out)
                self.assertIsNone(result.returncode)
                self.assertEqual(unrelated.wait(timeout=5), 0)
                time.sleep(0.2)
                self.assertTrue(other.exists())
                self.assertFalse(marker.exists())
            finally:
                if unrelated.poll() is None:
                    unrelated.kill()
                    unrelated.wait()

    def test_stdin_is_literal_and_missing_program_is_a_launch_failure(self):
        result = _process.run(
            [sys.executable, "-c", "import sys;sys.stdout.buffer.write(sys.stdin.buffer.read())"],
            cwd=Path.cwd(),
            input=b"literal [*]\x00name\x00",
        )
        self.assertEqual(result.stdout, b"literal [*]\x00name\x00")
        try:
            missing = _process.run(["missing-template-verifier"], cwd=Path.cwd())
        except OSError:
            pass  # POSIX Popen reports launch failure before a child exists.
        else:
            self.assertIsNone(missing.returncode)


class VerificationPrivacyRuntimeTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("TEMPLATE_TEST_OTHER_PYTHON"), "second Python not selected")
    def test_second_installed_runtime_is_used_and_wrong_minor_refuses(self):
        other = Path(os.environ["TEMPLATE_TEST_OTHER_PYTHON"]).resolve()
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            git_init(root)
            (root / ".gitignore").write_text("project.local.toml\n")
            (root / "project.local.toml").write_text(
                "schema='template.local/1'\npython=" + json.dumps(str(other)) + "\n"
            )
            executable, identity = _workspace.resolve_runtime(root)
            self.assertEqual(Path(executable), other)
            self.assertEqual(identity["source"], "project.local")
            wanted = ".".join(identity["python"].split(".")[:2])
            agreed = _workspace.resolve_runtime(root, {"runtime": {"python": wanted}})[1]
            self.assertEqual(agreed["python"], identity["python"])
            self.assertNotEqual(agreed["sha"], identity["sha"])
            selected = _process.run(
                _workspace.runtime_argv(
                    ["python", "-c", "import sys;print(sys.version_info.minor)"], executable
                ),
                cwd=root,
            )
            self.assertEqual(selected.returncode, 0)
            self.assertEqual(int(selected.stdout), int(wanted.split(".")[1]))
            with self.assertRaisesRegex(ValueError, "required; selected runtime"):
                _workspace.resolve_runtime(root, {"runtime": {"python": "3.999"}})

    def test_sanitizer_preserves_markdown_slashes_urls_and_scrubs_spaced_paths(self):
        root = Path.cwd()
        ordinary = (
            "`/` read / write and pass / fail 1/2 [source](07_app/view.py) "
            "`07_app/view.py` https://example.test/a/b"
        )
        self.assertEqual(verify._scrub(ordinary.encode(), root, {}), ordinary)
        cases = [
            r'"C:\Users\Jane Doe\secret file.txt"',
            "'/home/Jane Doe/secret file.txt'",
            r"C:\Users\Jane Doe\secret.txt",
            "/home/Jane Doe/secret.txt",
            r"C:\Users\Jane Doe\secret file.txt",
            "/home/Jane Doe/secret file.txt",
            r"\\server\Jane Doe\secret file.txt",
            "file:///home/Jane Doe/secret file.txt",
        ]
        for value in cases:
            with self.subTest(value=value):
                cleaned = verify._scrub(value.encode(), root, {})
                self.assertNotIn("Jane", cleaned)
                self.assertNotIn("secret", cleaned)
                self.assertIn("<absolute-path>", cleaned)
        secret = "begin-" + "s" * 5000 + "-end"
        cleaned = verify._scrub(
            ("prefix\n" + secret + "\nlast line\n").encode(), root, {"SERVICE_TOKEN": secret}
        )
        self.assertIn("<redacted>", cleaned)
        self.assertNotIn("sss", cleaned)
        self.assertNotIn(
            "private line",
            verify._scrub(
                b"private line\nlast line\n", root, {"PRIVATE_KEY": "omitted prefix\nprivate line"}
            ),
        )

    def test_runtime_is_portable_and_wrong_version_fails_before_verification(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            executable, identity = _workspace.resolve_runtime(root)
            self.assertEqual(executable, sys.executable)
            self.assertNotIn(str(root), json.dumps(identity))
            self.assertNotIn(executable, json.dumps(identity))
            self.assertEqual(
                _workspace.runtime_argv(["python", "x.py"], executable), [executable, "x.py"]
            )
            self.assertEqual(
                _workspace.runtime_argv(["node", "x.js"], executable), ["node", "x.js"]
            )
            with self.assertRaisesRegex(ValueError, "required; selected runtime"):
                _workspace.resolve_runtime(root, {"runtime": {"python": "999.1"}})

    def test_runtime_mapping_must_be_ignored_and_schema_is_strict(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            git_init(root)
            local = root / "project.local.toml"
            local.write_text(
                "schema='template.local/1'\npython=" + json.dumps(sys.executable) + "\n"
            )
            with self.assertRaisesRegex(ValueError, "ignored and untracked"):
                _workspace.resolve_runtime(root)
            (root / ".gitignore").write_text("project.local.toml\n")
            self.assertEqual(_workspace.resolve_runtime(root)[1]["source"], "project.local")
            local.write_text(local.read_text() + "surprise=true\n")
            with self.assertRaisesRegex(ValueError, "requires schema"):
                _workspace.resolve_runtime(root)


class GitSelectionTests(unittest.TestCase):
    diagnostic = "TEMPLATE_GIT_EXECUTABLE must name an existing absolute executable file"
    no_status = "Git operation failed: no exit status; inspect retained state"

    def test_windows_disposable_interpreter_redirect_excludes_application_shadow(self):
        if os.name != "nt":
            self.skipTest("Windows interpreter redirect probe is not applicable on POSIX")
        import venv

        with tempfile.TemporaryDirectory() as name:
            root = Path(name) / "owned interpreter"
            venv.EnvBuilder(with_pip=False, symlinks=False).create(root)
            program = (
                "import ctypes,json,sys;"
                "b=ctypes.create_unicode_buffer(32768);"
                "ctypes.windll.kernel32.GetModuleFileNameW(None,b,len(b));"
                "print(json.dumps([sys.executable,sys._base_executable,b.value]))"
            )
            result = subprocess.run(
                [str(root / "Scripts/python.exe"), "-I", "-S", "-c", program],
                capture_output=True, check=True, timeout=30,
            )
            executable, base, application = map(Path, json.loads(result.stdout))
            self.assertTrue(executable.is_relative_to(root))
            self.assertFalse(application.is_relative_to(root))
            self.assertEqual(application.resolve(), base.resolve())


    def test_literal_argv_selection_and_unset_manual_behavior(self):
        selected = str(Path(shutil.which("git")).resolve())
        root = Path.cwd()
        args = ("diff", "HEAD", "--", 'space [literal] é "quote"')
        for value in (None, selected):
            with self.subTest(selected=value is not None), mock.patch.dict(os.environ):
                os.environ.pop("TEMPLATE_GIT_EXECUTABLE", None)
                if value is not None:
                    os.environ["TEMPLATE_GIT_EXECUTABLE"] = value
                expected = "git" if value is None else selected
                with mock.patch.object(c.subprocess, "run") as launch:
                    c.git(root, *args, check=False, text=True)
                launch.assert_called_once_with(
                    [expected, "-C", str(root), *args], check=False,
                    capture_output=True, text=True,
                )
                result = _process.Result(0, b"", b"", False, 0, 0)
                with mock.patch.object(_process, "run", return_value=result) as launch:
                    self.assertIs(g.run(root, *args, input=b"literal\0"), result)
                launch.assert_called_once_with(
                    [expected, "--no-replace-objects", "--no-optional-locks",
                     "--literal-pathspecs", "-C", str(root), *args],
                    cwd=root, timeout=120, tail_limit=8*1024*1024,
                    keep="head", input=b"literal\0",
                )
                for helper in (c.git, g.run):
                    self.assertEqual(helper(root, "--version").returncode, 0)

    def test_invalid_selection_refuses_before_either_launch(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            executable = root / "ordinary.exe"
            executable.write_bytes(b"invalid image")
            bad = ["", "git", "./git.exe", '"' + str(executable) + '"',
                   str(executable) + " --version", str(root / "missing.exe"), str(root),
                   "$GIT/bin/git", "~/git", "nul\0path"]
            for suffix in ((".cmd", ".bat", ".ps1", "") if os.name == "nt" else (".sh",)):
                path = root / ("unexecutable" + suffix)
                path.write_bytes(b"not executable")
                path.chmod(0o600)
                bad.append(str(path))
            if os.name != "nt":
                for target, link in (("missing", "dangling"), ("loop", "loop")):
                    (root / link).symlink_to(target)
                    bad.append(str(root / link))
            else:
                upper = root / "accepted.EXE"
                upper.write_bytes(executable.read_bytes())
                with mock.patch.dict(os.environ, TEMPLATE_GIT_EXECUTABLE=str(upper)):
                    self.assertEqual(c.git_executable(), str(upper.resolve()))
                with mock.patch.dict(os.environ, TEMPLATE_GIT_EXECUTABLE=str(executable)), \
                        mock.patch.object(Path, "resolve", return_value=root / "unexecutable.cmd"):
                    with self.assertRaises(ValueError) as error:
                        c.git_executable()
                    self.assertEqual(str(error.exception), self.diagnostic)
            for value in bad:
                # os.environ cannot contain NUL; intercept its read for that validation case.
                env = {**os.environ, "TEMPLATE_GIT_EXECUTABLE": value}
                with self.subTest(value=value), mock.patch.object(c.os, "environ", env):
                    with mock.patch.object(c.subprocess, "run") as direct, \
                            mock.patch.object(_process, "run") as supervised:
                        for helper in (c.git, g.run):
                            with self.assertRaises(ValueError) as error:
                                helper(root, "--version")
                            self.assertEqual(str(error.exception), self.diagnostic)
                        direct.assert_not_called()
                        supervised.assert_not_called()

    def test_posix_executable_symlink_resolves_and_launches_when_supported(self):
        if os.name == "nt":
            self.skipTest("POSIX executable symlink selection is not exercised on Windows")
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            target = Path(shutil.which("git")).resolve()
            link = root / "selected git"
            link.symlink_to(target)
            with mock.patch.dict(os.environ, TEMPLATE_GIT_EXECUTABLE=str(link)):
                self.assertEqual(c.git_executable(), str(target))
                for helper in (c.git, g.run):
                    self.assertEqual(helper(root, "--version").returncode, 0)

    def test_none_status_refuses_both_checks_and_actual_privacy_head_callers(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            git_init(root)
            (root / ".gitignore").write_text("project.local.toml\n")
            (root / "product").write_text("retained\n")
            run_git(root, "add", ".")
            run_git(root, "commit", "-qm", "baseline")
            local = root / "project.local.toml"
            local.write_text("schema='template.local/1'\npython=" + json.dumps(sys.executable))
            before = _workspace.snapshot(root)
            for check in (False, True):
                with self.subTest(check=check), mock.patch.object(
                    _process, "run",
                    return_value=_process.Result(None, b"", b"private", False, 0, 7)
                ) as launch:
                    with self.assertRaises(ValueError) as error:
                        g.run(root, "status", check=check)
                    self.assertEqual(str(error.exception), self.no_status)
                    launch.assert_called_once()
            with mock.patch.object(
                _process, "run", return_value=_process.Result(None, b"", b"", True, 0, 0)
            ):
                with self.assertRaisesRegex(ValueError, "Git operation timed out"):
                    g.run(root, "status", check=False)
            calls = [(_workspace.resolve_runtime, (root,), "check-ignore"),
                     (_evidence.head_shas, (root, ["product"]), "rev-parse")]
            for caller, args, command in calls:
                with self.subTest(caller=caller.__name__), mock.patch.object(
                    _process, "run", return_value=_process.Result(None, b"", b"", False, 0, 0)
                ) as launch:
                    with self.assertRaises(ValueError) as error:
                        caller(*args)
                    self.assertEqual(str(error.exception), self.no_status)
                    launch.assert_called_once()
                    self.assertIn(command, launch.call_args.args[0])
            self.assertEqual(_workspace.snapshot(root), before)

    def test_real_selected_failure_and_replacement_never_fall_back(self):
        trusted = str(Path(shutil.which("git")).resolve())
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            git_init(root)
            (root / ".gitignore").write_text("project.local.toml\n")
            (root / "product").write_text("retained\n")
            (root / "ledger.jsonl").write_bytes(b'{"retained":true}\r\n')
            run_git(root, "add", ".")
            run_git(root, "commit", "-qm", "baseline")
            local = root / "project.local.toml"
            local.write_text("schema='template.local/1'\npython=" + json.dumps(sys.executable))
            invalid = root / "invalid image.exe"
            invalid.write_bytes(b"not an executable image\n")
            invalid.chmod(0o700)
            before = _workspace.snapshot(root)
            self.assertEqual(c.git(root, "--version").returncode, 0)
            with mock.patch.dict(os.environ, TEMPLATE_GIT_EXECUTABLE=str(invalid)):
                for check in (False, True):
                    with self.subTest(helper="common", check=check):
                        with mock.patch.object(
                            c.subprocess, "run", wraps=c.subprocess.run
                        ) as calls:
                            with self.assertRaises(OSError):
                                c.git(root, "--version", check=check)
                        calls.assert_called_once()
                        self.assertEqual(calls.call_args.args[0][0], str(invalid.resolve()))
                    with self.subTest(helper="bounded", check=check):
                        with mock.patch.object(_process, "run", wraps=_process.run) as calls:
                            with self.assertRaises((ValueError, OSError)) as error:
                                g.run(root, "--version", check=check)
                        calls.assert_called_once()
                        self.assertEqual(calls.call_args.args[0][0], str(invalid.resolve()))
                        if os.name == "nt":
                            self.assertEqual(str(error.exception), self.no_status)
                for caller, args in ((_workspace.resolve_runtime, (root,)),
                                     (_evidence.head_shas, (root, ["product"]))):
                    with mock.patch.object(_process, "run", wraps=_process.run) as calls:
                        with self.assertRaises((ValueError, OSError)):
                            caller(*args)
                    calls.assert_called_once()
                    self.assertEqual(calls.call_args.args[0][0], str(invalid.resolve()))
            # Trusted observation after removing invalid selection preserves every raw byte.
            self.assertEqual(_workspace.snapshot(root), before)
            with mock.patch.dict(os.environ, TEMPLATE_GIT_EXECUTABLE=trusted):
                for helper in (c.git, g.run):
                    result = helper(root, "rev-parse", "--verify", "missing-ref", check=False)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIsNotNone(result.returncode)
            for helper in (c.git, g.run):
                with self.subTest(deleted_before_launch=helper.__module__):
                    vanished = root / "vanished.exe"
                    vanished.write_bytes(b"temporary")
                    def remove_after_selection():
                        vanished.unlink()
                        return str(vanished)
                    with mock.patch.object(c, "git_executable", side_effect=remove_after_selection):
                        with self.assertRaises((ValueError, OSError)):
                            helper(root, "--version", check=False)
            self.assertEqual(_workspace.snapshot(root), before)


if __name__ == "__main__":
    unittest.main()
