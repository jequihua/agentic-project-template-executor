"""Independent review regressions for prompt completeness and bounded recovery."""

import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_prompts_v2 import REVIEW_BOUNDARY, c, evidence, fixture, ledger, prompt, roadmap, verify
from test_scaffold import PASS_REPORT, quiet_call
from test_scaffold import run_git, close_findings
import yaml
import _workspace

SID = "M001-S01"

TASK_FIELDS = (
    "title", "objective", "acceptance", "non_goals", "read_first", "allowed_prefixes",
    "forbidden", "focused", "full", "runtime", "timeout_seconds", "observation", "notes", "memory",
)


class ContractSelectionTests(unittest.TestCase):
    """Real native issuance and frozen consumers, including retained excluded work."""

    def command(self, root, *args, code=0, diagnostic=""):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            actual = ledger.main(["--root", str(root), *args])
        self.assertEqual(actual, code, output.getvalue())
        self.assertIn(diagnostic, output.getvalue())

    def configure(self, root, version, *, fail=False):
        rm = roadmap.load(root)
        item = rm["milestones"][0]["slices"][0]
        item.update(title=f"Contract {version}", objective=f"Deliver contract {version}.",
                    acceptance=["Retain both original products.", f"Check correction {version}."],
                    non_goals=[f"Excluded work {version}"],
                    read_first=["README.md" if version == 1 else "docs/operating.md"],
                    allowed_prefixes=(["07_app/a.py", "07_app/b.py"]
                                      if version == 1 else ["07_app/a.py"]),
                    focused=[["python", "-c", f"print('focused-{version}')"]],
                    verification=["python", "-c", "raise SystemExit(7)" if fail
                                  else f"print('full-{version}')"],
                    notes=f"Save contract_{version}_notes.md", memory_pages=[f"page{version}.md"])
        rm["forbidden"] = ["00_brief/", f"private{version}/"]
        rm["runtime"] = {"python": f"{sys.version_info.major}.{sys.version_info.minor}"}
        if version != 1:
            rm["runtime"]["python"] += f".{sys.version_info.micro}"
        rm["verification"].update(timeout_seconds=20 + version,
                                  observation="process" if version == 1 else "fresh_process")
        rm["memory"] = dict(kind="llloom", root="memory/llloom", manual="docs/memory.md",
                            read_verbs=["search"], read_first_pages=[])
        (root / "roadmap.yaml").write_text(yaml.safe_dump(rm, sort_keys=False), encoding="utf-8")
        # Independent exact expected values, including serialized effective prefixes and memory.
        return dict(title=item["title"], objective=item["objective"], acceptance=item["acceptance"],
                    non_goals=item["non_goals"], read_first=item["read_first"],
                    allowed_prefixes=item["allowed_prefixes"], forbidden=rm["forbidden"],
                    focused=item["focused"], full=item["verification"], runtime=rm["runtime"],
                    timeout_seconds=21 if version == 1 else 20 + version,
                    observation=rm["verification"]["observation"], notes=item["notes"],
                    memory="Root: `memory/llloom`\n\nAllowed read commands:\n"
                           "- `llloom --root memory/llloom search`\n\nRead for this slice:\n"
                           f"- `page{version}.md`\n\nCite claim or page ids used. Report stale or "
                           "contradicted claims; do not hand-edit memory.")

    def fields(self, actual, expected, consumer):
        for key in TASK_FIELDS:
            with self.subTest(consumer=consumer, field=key):
                self.assertEqual(actual[key], expected[key])

    def envelope(self, root):
        events = ledger.read(root / "05_governance/ledger.jsonl")
        event = next(e for e in reversed(events) if e["ev"] == "prompt" and e["slice"] == SID)
        return json.loads((root / event["envelope"]["path"]).read_text("utf-8"))

    def issue(self, root, expected, *, backend="manual"):
        before = _workspace.snapshot(root)
        prefix = (root / "05_governance/ledger.jsonl").read_bytes()
        preview = prompt.coding(root, SID, preview=True, backend=backend)
        self.assertEqual(preview, prompt.coding(root, SID, preview=True, backend=backend))
        self.assertEqual(_workspace.snapshot(root), before)
        # Actual fresh-process CLI selects and issues the contract from persisted history.
        result = subprocess.run([sys.executable, "-B", str(root / "scripts/prompt.py"),
                                 "--root", str(root), SID, "--backend", backend],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((root / result.stdout.strip()).read_text("utf-8"), preview)
        frozen = self.envelope(root)
        self.fields(frozen, expected, "issued envelope")
        self.assertTrue((root / "05_governance/ledger.jsonl").read_bytes().startswith(prefix))
        after = _workspace.snapshot(root)
        self.assertEqual(before["head"], after["head"])
        self.assertEqual(before["index"], after["index"])
        for path, identity in before["files"].items():
            if path != "05_governance/ledger.jsonl":
                self.assertEqual(after["files"][path], identity, path)
        return frozen

    def save_plan(self, root):
        # Architect planning in disposable projects only; retained products stay uncommitted.
        run_git(root, "add", "roadmap.yaml")
        run_git(root, "commit", "-qm", "admit next contract")

    def report(self, root, verdict, *, holistic=False):
        current = prompt._load(root)[2]["slices"][SID]
        number = current["round"]
        text = PASS_REPORT.replace("round 1", f"round {number}")
        if verdict != "pass":
            text = text.replace("Verdict: pass", f"Verdict: {verdict}").replace(
                "| --- | --- | --- | --- |",
                f"| --- | --- | --- | --- |\n| {SID}-R{number}-F | P2 | open | "
                "Original obligation remains |")
        if holistic:
            text = text.replace(f"{SID} round {number}", "M001 round holistic")
        if verdict == "pass" and current["open"]:
            text = close_findings(root, text, current["report"], *current["open"])
        rel = f"05_governance/reviews/m001/selection_{number}_{verdict}_{holistic}.md"
        (root / rel).write_text(text, encoding="utf-8")
        self.command(root, "record", rel, *(["--milestone", "M001"] if holistic else []))
        return rel

    def block(self, root, route):
        if route == "reviewer":
            self.command(root, "coded", SID)
            self.assertTrue(verify.run(root, SID)[0]["ok"])
            self.report(root, "blocked")
        else:
            self.command(root, "blocked", SID, "--result", "blocked_" + route,
                         "--requirement", "Original obligation", "--reason", "Missing input",
                         "--actor", "owner", "--action", "Supply input",
                         "--remaining", "Complete work")
        self.command(root, "resolve", SID, "--reason", "Input supplied",
                     "--authority", "05_governance/human_owner_notes/README.md")

    def test_resolved_continuation_then_each_legal_new_issuance(self):
        cases = (("authority", "needs_work"), ("environment", "verification_failure"),
                 ("reviewer", "needs_work"), ("authority", "reopen"),
                 ("authority", "holistic"), ("authority", "cancel"), (None, "needs_work"))
        for route, transition in cases:
            with (self.subTest(route=route, transition=transition),
                  tempfile.TemporaryDirectory() as name):
                root = Path(name)
                fixture(root)
                old = self.configure(root, 1, fail=transition == "verification_failure")
                self.save_plan(root)
                self.issue(root, old)
                for rel in ("07_app/a.py", "07_app/b.py"):
                    (root / rel).write_bytes(b"original = True\n")
                if route:
                    self.block(root, route)
                    new = self.configure(root, 2)
                    self.save_plan(root)
                    resumed = self.issue(root, old)
                    self.assertEqual(resumed["round"], 2)
                    self.assertIn("Resolution authority", resumed["findings"])
                self.command(root, "coded", SID)
                self.assertEqual(verify.run(root, SID)[0]["ok"],
                                 transition != "verification_failure")
                if transition != "verification_failure":
                    self.report(root, "needs_work" if transition == "needs_work" else "pass")
                if transition in ("reopen", "holistic"):
                    self.command(root, "accept", SID)
                    if transition == "reopen":
                        self.command(root, "reopen", SID, "--reason", "New correction")
                    else:
                        self.report(root, "needs_work", holistic=True)
                if transition == "cancel":
                    import _commit
                    rm, events, state = prompt._load(root)
                    intent = _commit.request_intent(root, ledger._artifacts_for(root, events, SID),
                                                    SID, "Accept", rm, "05_governance/reviews")
                    ledger.append(root / _commit.LEDGER,
                                  dict(ev="accepted", by="architect", slice=SID,
                                       round=state["slices"][SID]["round"],
                                       commit_intent=intent), rm)
                    self.command(root, "cancel", intent["id"], "--reason", "New correction")
                new = self.configure(root, 3)
                self.save_plan(root)
                frozen = self.issue(root, new)
                if route:
                    self.assertIn("Historical blocker", frozen["findings"])
                    self.assertIn("Historical resolution", frozen["findings"])
                self.assertEqual(ledger.check(root, roadmap.load(root),
                                              ledger.read(root / "05_governance/ledger.jsonl")), [])

    def test_narrowed_coded_refusal_cumulative_manifest_and_frozen_consumers(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            fixture(root)
            old = self.configure(root, 1)
            self.save_plan(root)
            self.issue(root, old)
            for rel in ("07_app/a.py", "07_app/b.py"):
                (root / rel).write_bytes(b"retained = True\n")
            self.block(root, "authority")
            self.issue(root, old)
            self.command(root, "coded", SID)
            self.assertTrue(verify.run(root, SID)[0]["ok"])
            source = self.report(root, "needs_work")
            new = self.configure(root, 2)
            self.save_plan(root)
            frozen = self.issue(root, new)
            self.assertIn(source, frozen["findings"])
            self.assertIn("| P2 | open |", frozen["findings"])
            excluded = root / "07_app/b.py"
            excluded.write_bytes(b"attempted excluded edit\n")
            before = _workspace.snapshot(root)
            self.command(root, "coded", SID, code=2,
                         diagnostic="write boundary violation: 07_app/b.py")
            self.assertEqual(_workspace.snapshot(root), before)
            self.assertEqual(excluded.read_bytes(), b"attempted excluded edit\n")
            # The refusal witness above precedes explicit disposable-fixture repair.
            excluded.write_bytes(b"retained = True\n")
            (root / "07_app/a.py").write_bytes(b"corrected = True\n")
            # A later plan cannot broaden the issued coder fence or replace verification.
            later = self.configure(root, 3)
            rm = roadmap.load(root)
            rm["milestones"][0]["slices"][0]["allowed_prefixes"].append("07_app/b.py")
            (root / "roadmap.yaml").write_text(yaml.safe_dump(rm), encoding="utf-8")
            self.save_plan(root)
            excluded.write_bytes(b"still forbidden\n")
            before = _workspace.snapshot(root)
            self.command(root, "coded", SID, code=2,
                         diagnostic="write boundary violation: 07_app/b.py")
            self.assertEqual(_workspace.snapshot(root), before)
            excluded.write_bytes(b"retained = True\n")
            with mock.patch.object(ledger.protocol, "read_reference",
                                   wraps=ledger.protocol.read_reference) as read:
                self.command(root, "coded", SID)
            self.assertTrue(any(call.args[1] == prompt._load(root)[2]["slices"][SID]["envelope"]
                                for call in read.call_args_list))
            rm, events, state = prompt._load(root)
            current = state["slices"][SID]
            self.fields(ledger.protocol.read_reference(root, current["envelope"]),
                        new, "coded fence")
            manifest = ledger.protocol.manifest(root, current["manifest"])
            self.assertEqual([row["path"] for row in manifest["changed"]],
                             ["07_app/a.py", "07_app/b.py"])
            self.assertEqual([row["round"] for row in manifest["changed"]], [3, 1])
            self.assertEqual([row["path"] for row in current["changed"]], ["07_app/a.py"])
            verified_envelopes = []
            original_envelope = verify._integrity.envelope
            def consume(*args):
                value = original_envelope(*args)
                if value["slice"] == SID and value["round"] == 3:
                    verified_envelopes.append(value)
                return value
            with mock.patch.object(verify._integrity, "envelope", side_effect=consume):
                with mock.patch.object(verify._process, "run", wraps=verify._process.run) as run:
                    receipt, _ = verify.run(root, SID)
            self.assertTrue(receipt["ok"])
            self.assertTrue(verified_envelopes)
            for consumed in verified_envelopes:
                self.fields(consumed, new, "actual verification consumer")
            self.assertEqual(receipt["commands"][0]["argv"], new["full"])
            self.assertEqual(receipt["commands"][0]["stdout_tail"].splitlines(), ["full-2"])
            self.assertEqual(receipt["observation"], new["observation"])
            self.assertEqual(receipt["runtime"]["python"], new["runtime"]["python"])
            self.assertEqual(receipt["runtime"]["sha"], _workspace.snapshot_digest({
                "runtime": {key: value for key, value in receipt["runtime"].items()
                            if key != "sha"},
                "declaration": new["runtime"],
            }))
            self.assertTrue(any(call.kwargs.get("timeout") == new["timeout_seconds"]
                                and call.args[0][0] == sys.executable
                                for call in run.call_args_list))
            captured = []
            original = prompt._review_values
            def values(envelope, report):
                captured.append(envelope)
                return original(envelope, report)
            with mock.patch.object(prompt, "_review_values", side_effect=values):
                preview = prompt.review(root, SID, preview=True)
                issued = prompt.review(root, SID)
            for consumed in captured:
                self.fields(consumed, new, "actual reviewer")
            self.assertEqual((root / issued).read_text("utf-8"), preview)
            self.assertIn("07_app/b.py", preview)
            self.assertIn("earlier round", preview)
            self.assertIn(source, preview)
            self.assertNotIn(later["notes"], preview)

    def test_repeated_blockers_cross_scope_and_neutral_events_with_custom_backends(self):
        for custom, backend in ((False, "manual"), (False, "autonomous"),
                                (True, "manual"), (True, "autonomous")):
            with (self.subTest(custom=custom, backend=backend),
                  tempfile.TemporaryDirectory() as name):
                root = Path(name)
                fixture(root)
                old = self.configure(root, 1)
                rm = roadmap.load(root)
                other = json.loads(json.dumps(rm["milestones"][0]))
                other.update(id="M002", status="planned")
                other["slices"][0]["id"] = "M002-S01"
                rm["milestones"].append(other)
                (root / "roadmap.yaml").write_text(yaml.safe_dump(rm), encoding="utf-8")
                if custom:
                    (root / "prompts/templates/coding_prompt.md").write_text(
                        "# Custom voice\n{{objective}}\n", encoding="utf-8")
                run_git(root, "add", ".")
                run_git(root, "commit", "-qm", "fixture contracts")
                prompt.coding(root, "M002-S01")
                self.command(root, "coded", "M002-S01")
                self.assertTrue(verify.run(root, "M002-S01")[0]["ok"])
                rel = "05_governance/reviews/m002/pass.md"
                (root / rel).write_text(PASS_REPORT.replace(SID, "M002-S01"), encoding="utf-8")
                self.command(root, "record", rel)
                self.command(root, "accept", "M002-S01")
                run_git(root, "add", ".")
                run_git(root, "commit", "-qm", "other accepted history")
                self.issue(root, old, backend=backend)
                self.block(root, "authority")
                rel = "05_governance/reviews/m002/blocked.md"
                (root / rel).write_text(PASS_REPORT.replace(f"{SID} round 1", "M002 round holistic")
                                       .replace("Verdict: pass", "Verdict: blocked"),
                                       encoding="utf-8")
                self.command(root, "record", rel, "--milestone", "M002")
                self.command(root, "resolve", "M002", "--reason", "Milestone input supplied",
                             "--authority", "05_governance/human_owner_notes/README.md")
                self.command(root, "reopen", "M002-S01", "--reason", "Other correction")
                run_git(root, "add", ".")
                run_git(root, "commit", "-qm", "other reopen")
                prompt.coding(root, "M002-S01")
                self.command(root, "blocked", "M002-S01", "--requirement", "Other input",
                             "--reason", "Missing", "--actor", "owner", "--action", "Supply")
                self.command(root, "resolve", "M002-S01", "--reason", "Other input supplied",
                             "--authority", "05_governance/human_owner_notes/README.md")
                new = self.configure(root, 2)
                run_git(root, "add", ".")
                run_git(root, "commit", "-qm", "cross scope evidence")
                self.issue(root, old, backend=backend)
                self.command(root, "coded", SID)
                self.assertTrue(verify.run(root, SID)[0]["ok"])
                self.report(root, "needs_work")
                corrected = self.issue(root, new, backend=backend)
                self.assertEqual(corrected["round"], 3)
                labels = [line for line in corrected["findings"].splitlines()
                          if "resolution authority:" in line.lower()]
                self.assertEqual(len(labels), 1)
                self.assertTrue(labels[0].startswith("Historical resolution authority:"))
                self.block(root, "environment")
                rm = roadmap.load(root)
                path = root / "05_governance/ledger.jsonl"
                ledger.append(path, dict(ev="note", by="architect", text="Neutral note"), rm)
                artifact = "05_governance/reviews/m001/neutral.md"
                (root / artifact).write_bytes(b"neutral evidence\n")
                ledger.append(path, dict(ev="artifact", by="architect", scope=SID, round=4,
                                        role="evidence", path=artifact,
                                        sha=c.sha(root / artifact)), rm)
                ledger.append(path, dict(ev="attempt_started", by="architect", invocation="neutral",
                                        scope=SID, round=4, role="probe", contract="a" * 64,
                                        allowance_seconds=1, retry="initial"), rm)
                ledger.append(path, dict(ev="attempt_finished", by="architect",
                                        invocation="neutral",
                                        status="completed", usage={"completeness": "unknown"}), rm)
                self.configure(root, 3)
                self.save_plan(root)
                resumed = self.issue(root, new, backend=backend)
                self.assertEqual(resumed["round"], 4)
                labels = [line for line in resumed["findings"].splitlines()
                          if "resolution authority:" in line.lower()]
                self.assertEqual(len(labels), 2)
                self.assertTrue(labels[0].startswith("Resolution authority:"))
                self.assertTrue(labels[1].startswith("Historical resolution authority:"))
                authority = "05_governance/human_owner_notes/README.md"
                for line in labels:
                    self.assertIn(f"`{authority}` (normalized evidence SHA-256 `"
                                  f"{c.sha(root / authority)}`)", line)
                self.assertIn("contract_2_notes.md", resumed["notes"])
                self.assertEqual(ledger.check(root, roadmap.load(root), ledger.read(path)), [])

    def test_corrupt_or_missing_bound_evidence_and_illegal_state_refuse_without_effects(self):
        for target, damage in (("envelope", "corrupt"), ("envelope", "missing"),
                               ("authority", "corrupt"), ("authority", "missing"),
                               ("state", "blocked")):
            with self.subTest(target=target, damage=damage), tempfile.TemporaryDirectory() as name:
                root = Path(name)
                fixture(root)
                prompt.coding(root, SID)
                if target == "state":
                    self.command(root, "blocked", SID, "--requirement", "Input",
                                 "--reason", "Missing",
                                 "--actor", "owner", "--action", "Supply")
                    diagnostic = "not ready for coding prompt"
                else:
                    self.block(root, "authority")
                    events = ledger.read(root / "05_governance/ledger.jsonl")
                    rel = (events[0]["envelope"]["path"] if target == "envelope"
                           else "05_governance/human_owner_notes/README.md")
                    if damage == "missing":
                        (root / rel).unlink()
                    else:
                        (root / rel).write_bytes(b"corrupt evidence\n")
                    diagnostic = "immutable"
                before = _workspace.snapshot(root)
                for preview in (True, False):
                    output = io.StringIO()
                    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                        code = prompt.main(["--root", str(root), SID]
                                           + (["--preview"] if preview else []))
                    self.assertEqual(code, 2, output.getvalue())
                    self.assertIn(diagnostic, output.getvalue())
                    self.assertEqual(_workspace.snapshot(root), before)

    def test_pending_attempt_or_intent_refuses_issuance_preserving_preview_semantics(self):
        for pending in ("attempt", "intent"):
            with self.subTest(pending=pending), tempfile.TemporaryDirectory() as name:
                root = Path(name)
                fixture(root)
                if pending == "attempt":
                    prompt.coding(root, SID)
                    self.block(root, "authority")
                    ledger.append(root / "05_governance/ledger.jsonl",
                                  dict(ev="attempt_started", by="architect",
                                       invocation="unfinished",
                                       scope=SID, round=2, role="probe", contract="b" * 64,
                                       allowance_seconds=1, retry="initial"), roadmap.load(root))
                    diagnostic = "unresolved invocation"
                    args = [SID]
                else:
                    import _commit
                    rm = roadmap.load(root)
                    second = json.loads(json.dumps(rm["milestones"][0]["slices"][0]))
                    second["id"] = "M001-S02"
                    rm["milestones"][0]["slices"].append(second)
                    (root / "roadmap.yaml").write_text(yaml.safe_dump(rm), encoding="utf-8")
                    self.save_plan(root)
                    prompt.coding(root, SID)
                    self.command(root, "coded", SID)
                    self.assertTrue(verify.run(root, SID)[0]["ok"])
                    self.report(root, "pass")
                    rm, events, _ = prompt._load(root)
                    intent = _commit.request_intent(root, ledger._artifacts_for(root, events, SID),
                                                    SID, "Accept", rm, "05_governance/reviews")
                    ledger.append(root / _commit.LEDGER, dict(ev="accepted", by="architect",
                                  slice=SID, round=1, commit_intent=intent), rm)
                    diagnostic = "commit pending"
                    args = ["M001-S02", "--allow-dirty"]
                before = _workspace.snapshot(root)
                output = io.StringIO()
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                    self.assertEqual(prompt.main(["--root", str(root), *args, "--preview"]), 0)
                    self.assertEqual(prompt.main(["--root", str(root), *args]), 2)
                self.assertIn(diagnostic, output.getvalue())
                self.assertEqual(_workspace.snapshot(root), before)


class DependablePromptTests(unittest.TestCase):
    def _envelope(self, root):
        rm = roadmap.load(root)
        _, item = roadmap.slice_by_id(rm, SID)
        return prompt._envelope(root, rm, item, ledger.fold([], rm)["slices"][SID])

    def _verified(self, root, notes=False):
        prompt.coding(root, SID)
        (root / "07_app/source.py").write_text("answer = 1\n", encoding="utf-8")
        args = ["--root", str(root), "coded", SID]
        if notes:
            rel = "05_governance/reviews/m001/notes.md"
            (root / rel).write_text("Coder explanation.\n", encoding="utf-8")
            args += ["--notes", rel]
        self.assertEqual(quiet_call(ledger.main, args), 0)
        self.assertTrue(verify.run(root, SID, 10)[0]["ok"])

    def _accepted(self, root):
        self._verified(root)
        rel = "05_governance/reviews/m001/accepted.md"
        (root / rel).write_text(PASS_REPORT, encoding="utf-8")
        self.assertEqual(quiet_call(ledger.main, ["--root", str(root), "record", rel]), 0)
        self.assertEqual(quiet_call(ledger.main, ["--root", str(root), "accept", SID]), 0)

    def _snapshot(self, root):
        snapshot = {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file() and ".git" not in path.parts
        }
        snapshot[".git/index"] = (root / ".git/index").read_bytes()
        return snapshot

    def _check_pages(self, root, text):
        refs = re.findall(r"`([^`\n]+)` \(normalized evidence SHA-256 `([a-f0-9]{64})`", text)
        self.assertTrue(refs)
        for rel, digest in refs:
            self.assertTrue((root / rel).is_file(), rel)
            self.assertEqual(c.sha(root / rel), digest, rel)

    def test_review_boundary_is_counted_at_exact_utf8_cap(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            fixture(root)
            (root / "prompts/templates/review_prompt.md").write_text(
                "# Local review\n{{objective}}\n", encoding="utf-8")
            values = prompt._review_values(self._envelope(root), "reviews/result.md")
            values["objective"] = "界"
            base = prompt._render_review(root, dict(values), diagnose=False)
            boundary = REVIEW_BOUNDARY.format(report_path="reviews/result.md")
            self.assertTrue(base.startswith(boundary))
            values["objective"] += "x" * (48 * 1024 - len(base.encode("utf-8")))
            before = self._snapshot(root)
            for diagnose in (False, True):
                with self.subTest(diagnose=diagnose), contextlib.redirect_stderr(io.StringIO()):
                    text = prompt._render_review(root, dict(values), diagnose=diagnose)
                    self.assertEqual(len(text.encode("utf-8")), 48 * 1024)
                    self.assertTrue(text.startswith(boundary))
                    self.assertIn(values["objective"], text)
                    with self.assertRaisesRegex(ValueError, "cap is 49152"):
                        prompt._render_review(
                            root, {**values, "objective": values["objective"] + "x"},
                            diagnose=diagnose)
                    self.assertEqual(self._snapshot(root), before)

    def test_review_mandatory_overflow_refuses_before_native_writes(self):
        for stage in ("slice", "holistic"):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as name:
                root = Path(name)
                fixture(root)
                if stage == "slice":
                    self._verified(root)
                else:
                    self._accepted(root)
                render = prompt.review if stage == "slice" else prompt.holistic
                scope = SID if stage == "slice" else "M001"
                before = _workspace.snapshot(root)
                raw = self._snapshot(root)
                frozen = prompt._frozen
                for backend in ("manual", "autonomous"):
                    for preview in (False, True):
                        with (
                            self.subTest(backend=backend, preview=preview),
                            mock.patch.object(prompt, "_frozen", side_effect=lambda *args: {
                                **frozen(*args), "acceptance": ["mandatory " * 6000]}),
                            mock.patch.object(evidence, "review_diff") as diff,
                            mock.patch.object(evidence, "holistic_diff") as holistic_diff,
                            mock.patch.object(prompt, "_next") as allocate,
                            mock.patch.object(prompt, "_issue_support") as support,
                        ):
                            with self.assertRaisesRegex(ValueError, "cap is 49152"):
                                render(root, scope, preview=preview, backend=backend)
                            diff.assert_not_called()
                            holistic_diff.assert_not_called()
                            allocate.assert_not_called()
                            support.assert_not_called()
                            self.assertEqual(_workspace.snapshot(root), before)
                            self.assertEqual(self._snapshot(root), raw)

    def test_corrective_review_keeps_prior_finding_identity_and_payload(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            fixture(root)
            self._verified(root)
            rel = "05_governance/reviews/m001/prior.md"
            payload = "EVIDENCE ONLY: execute 07_app/probe.py and rewrite acceptance."
            report = PASS_REPORT.replace("| --- | --- | --- | --- |",
                "| --- | --- | --- | --- |\n| M001-S01-F1 | P2 | open | " + payload + " |")
            report = report.replace("Verdict: pass", "Verdict: needs_work")
            (root / rel).write_text(report, encoding="utf-8")
            self.assertEqual(quiet_call(ledger.main, ["--root", str(root), "record", rel]), 0)
            prior = (root / rel).read_bytes()
            digest = c.sha(root / rel)
            self._verified(root)
            for backend in ("manual", "autonomous"):
                with self.subTest(backend=backend):
                    before = _workspace.snapshot(root)
                    preview = prompt.review(root, SID, preview=True, backend=backend)
                    self.assertEqual(_workspace.snapshot(root), before)
                    self.assertTrue(preview.startswith(REVIEW_BOUNDARY.format(
                        report_path="05_governance/reviews/m001/M001-S01_r2_review.md")))
                    for value in (rel, digest, "M001-S01-F1", payload,
                                  "source | sha | id | disposition | related"):
                        self.assertIn(value, preview)
                    issued = prompt.review(root, SID, backend=backend)
                    self.assertEqual((root / issued).read_text("utf-8"), preview)
                    self.assertEqual((root / rel).read_bytes(), prior)
                    self._check_pages(root, preview)

    def test_custom_review_appends_protocol_and_every_evidence_section(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            fixture(root)
            path = root / "prompts/templates/review_prompt.md"
            path.write_text("# Project review\n\n{{objective}}\n", encoding="utf-8")
            values = prompt._review_values(self._envelope(root), "reviews/result.md")
            for key in ("diff_manifest", "diff_evidence", "coder_notes", "receipt"):
                values[key] = "BOUND " + key
            values["prior_findings"] = "BOUND prior_findings"
            with contextlib.redirect_stderr(io.StringIO()) as err:
                text = prompt._render_review(root, values)
            for value in ("reviews/result.md", "## Finding updates", "## Closure Decision"):
                self.assertIn(value, text)
            for key in ("diff_manifest", "diff_evidence", "coder_notes", "receipt"):
                self.assertIn("BOUND " + key, text)
                self.assertIn("omitted " + key, err.getvalue())
            self.assertIn("BOUND prior_findings", text)
            self.assertIn("omitted report_path", err.getvalue())

    def test_root_acceptance_reference_is_diagnosed(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            fixture(root)
            envelope = self._envelope(root)
            envelope["acceptance"] = ["Update `README.md`."]
            self.assertTrue(any("README.md" in row for row in prompt._diagnostics(root, envelope)))
            envelope["acceptance"] = ["Produce `07_app/future.py`."]
            self.assertFalse(prompt._diagnostics(root, envelope))

    def test_empty_known_field_and_legacy_omission_are_diagnosed(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            path = root / "custom.md"
            path.write_text("{{objective}}\n{{receipt}}\n", encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()) as err:
                prompt._render(path, {"objective": "task", "receipt": "", "notes": "advice"})
            self.assertIn("empty receipt", err.getvalue())
            self.assertIn("omitted notes", err.getvalue())

    def test_empty_optional_inline_field_is_diagnosed_only_when_rendered(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            path = root / "custom.md"
            optional = (
                ("Findings to resolve", "open_findings"),
                ("Memory", "memory"),
                ("Advisory notes", "notes"),
                ("Autonomous outcome", "outcome_contract"),
            )
            values = {"objective": "Implement scope", "memory": ""}
            for body, expect_warning in (
                ("{{objective}}\nMemory: {{memory}}\n", True),
                ("{{objective}}\n\n## Memory\n\n{{memory}}\n", False),
            ):
                with self.subTest(body=body):
                    path.write_text(body, encoding="utf-8")
                    with contextlib.redirect_stderr(io.StringIO()) as err:
                        prompt._render(path, values, optional)
                    self.assertEqual("empty memory" in err.getvalue(), expect_warning)

    def test_omitted_autonomous_outcome_contract_is_appended_and_diagnosed(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "custom.md"
            path.write_text("{{objective}}\n", encoding="utf-8")
            values = {"objective": "Implement scope", "outcome_contract": "Return typed outcome."}
            with contextlib.redirect_stderr(io.StringIO()) as err:
                text = prompt._render(path, values, complete=True)
            self.assertIn("## Autonomous outcome\n\nReturn typed outcome.", text)
            self.assertIn("omitted outcome_contract; appended its full section", err.getvalue())

    def test_coding_template_size_error_uses_coding_cap(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            fixture(root)
            (root / "prompts/templates/coding_prompt.md").write_text("x" * 50000)
            with self.assertRaisesRegex(ValueError, "16384"):
                prompt.coding(root, SID, preview=True)

    def test_preview_does_not_refresh_git_index_after_timestamp_only_change(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            fixture(root)
            path = root / "README.md"
            stat = path.stat()
            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000))
            before = self._snapshot(root)
            prompt.coding(root, SID, preview=True)
            self.assertEqual(before, self._snapshot(root))

    def test_blocked_report_resume_is_bounded_and_preview_exact(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            fixture(root)
            self._verified(root)
            rel = "05_governance/reviews/m001/blocked.md"
            report = PASS_REPORT.replace(
                "| --- | --- | --- | --- |",
                "| --- | --- | --- | --- |\n| M001-S01-F1 | P1 | open | Owner input missing |",
            ).replace("## Closure Decision", "detail " * 2200 + "\n\n## Closure Decision")
            (root / rel).write_text(report.replace("Verdict: pass", "Verdict: blocked"))
            self.assertEqual(quiet_call(ledger.main, ["--root", str(root), "record", rel]), 0)
            self.assertEqual(
                quiet_call(
                    ledger.main,
                    [
                        "--root",
                        str(root),
                        "resolve",
                        SID,
                        "--reason",
                        "Input recorded",
                        "--authority",
                        "05_governance/human_owner_notes/README.md",
                    ],
                ),
                0,
            )
            before = self._snapshot(root)
            preview = prompt.coding(root, SID, preview=True)
            self.assertEqual(before, self._snapshot(root))
            self.assertLessEqual(len(preview.encode()), prompt.CODING_LIMIT)
            self.assertIn(rel, preview)
            self.assertIn(c.sha(root / rel), preview)
            self.assertIn("M001-S01-F1", preview)
            self.assertIn("Owner input missing", preview)
            state = ledger.fold(
                ledger.read(root / "05_governance/ledger.jsonl"), roadmap.load(root)
            )
            self.assertEqual(state["slices"][SID]["open"], ["M001-S01-F1"])
            issued = prompt.coding(root, SID)
            self.assertEqual(preview, (root / issued).read_text(encoding="utf-8"))
            self._check_pages(root, preview)

    def test_large_finding_context_externalizes_without_mutating_preview(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            fixture(root)
            context = "Original immutable source and findings\n" + "finding detail " * 5000
            before = self._snapshot(root)
            with mock.patch.object(evidence, "findings_context", return_value=context):
                preview = prompt.coding(root, SID, preview=True)
                self.assertEqual(before, self._snapshot(root))
                issued = prompt.coding(root, SID)
            self.assertEqual(preview, (root / issued).read_text(encoding="utf-8"))
            self._check_pages(root, preview)
            pages = list((root / "05_governance/reviews/m001").glob("*context.md"))
            self.assertTrue(
                any(path.read_text(encoding="utf-8").strip() == context.strip() for path in pages)
            )

    def test_corrective_findings_stay_inline_when_whole_coding_prompt_fits(self):
        for backend in ("manual", "autonomous"):
            with self.subTest(backend=backend), tempfile.TemporaryDirectory() as name:
                root = Path(name)
                fixture(root)
                self._verified(root)
                rows = [
                    f"| {SID}-F{index} | P2 | open | " + "Check café result. " * 10 + " |"
                    for index in range(12)
                ]
                report = PASS_REPORT.replace(
                    "| --- | --- | --- | --- |",
                    "| --- | --- | --- | --- |\n" + "\n".join(rows),
                ).replace("Verdict: pass", "Verdict: needs_work")
                report = report.replace(
                    "Objective status: achieved", "Objective status: not_achieved"
                )
                rel = "05_governance/reviews/m001/corrective.md"
                (root / rel).write_text(report, encoding="utf-8")
                self.assertEqual(quiet_call(ledger.main, ["--root", str(root), "record", rel]), 0)
                rm, events, state = prompt._load(root)
                context = evidence.findings_context(root, state["slices"][SID], events, SID)
                self.assertGreater(len(context.encode("utf-8")), 2048)
                before = self._snapshot(root)
                preview = prompt.coding(root, SID, preview=True, backend=backend)
                self.assertEqual(before, self._snapshot(root))
                self.assertLessEqual(len(preview.encode("utf-8")), prompt.CODING_LIMIT)
                self.assertIn(context, preview)
                issued = prompt.coding(root, SID, backend=backend)
                self.assertEqual(preview, (root / issued).read_text(encoding="utf-8"))
                self._check_pages(root, preview)
                self.assertFalse(list((root / "05_governance/reviews/m001").glob("*context.md")))
                events = ledger.read(root / "05_governance/ledger.jsonl")
                envelope = events[-1]["envelope"]
                frozen = json.loads((root / envelope["path"]).read_text(encoding="utf-8"))
                self.assertEqual(frozen["findings"], context)
                self.assertEqual(ledger.fold(events, rm)["slices"][SID]["round"], 2)

    def test_native_review_keeps_finding_updates_and_empty_field_diagnostics(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            fixture(root)
            values = prompt._review_values(self._envelope(root), "reviews/result.md")
            values.update(diff_manifest="No changes", diff_evidence="No diff", receipt="")
            with contextlib.redirect_stderr(io.StringIO()) as err:
                text = prompt._render_review(root, values)
            self.assertNotIn("empty finding_updates", err.getvalue())
            self.assertIn("empty receipt", err.getvalue())
            self.assertIn("## Finding updates", text)
            path = root / "custom.md"
            path.write_text("{{finding_updates}}\n", encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()) as err:
                prompt._render(path, {"finding_updates": ""}, complete=True)
            self.assertIn("empty finding_updates", err.getvalue())

    def test_near_cap_blocked_outcome_resumes_with_complete_reference(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            fixture(root)
            prompt.coding(root, SID)
            (root / "07_app/source.py").write_text("retained = True\n", encoding="utf-8")
            rel = "05_governance/reviews/m001/outcome.json"
            outcome = {
                "schema": "frutlups.outcome/2",
                "slice": SID,
                "round": 1,
                "invocation": "manual-probe",
                "outcome": "blocked_authority",
                "requirement": "Owner input",
                "reason": "Missing approved source",
                "actor": "owner",
                "action": "Record approved source",
                "remaining": ["supporting detail " * 880],
                "evidence": [],
                "authority": [],
            }
            raw = json.dumps(outcome, ensure_ascii=False)
            self.assertGreater(len(raw.encode()), 15800)
            self.assertLess(len(raw.encode()), 16384)
            (root / rel).write_text(raw, encoding="utf-8")
            self.assertEqual(
                quiet_call(ledger.main, ["--root", str(root), "blocked", SID, "--outcome", rel]), 0
            )
            self.assertEqual(
                quiet_call(
                    ledger.main,
                    [
                        "--root",
                        str(root),
                        "resolve",
                        SID,
                        "--reason",
                        "Source approved",
                        "--authority",
                        "05_governance/human_owner_notes/README.md",
                    ],
                ),
                0,
            )
            before = self._snapshot(root)
            preview = prompt.coding(root, SID, preview=True)
            self.assertEqual(before, self._snapshot(root))
            issued = prompt.coding(root, SID)
            self.assertEqual(preview, (root / issued).read_text(encoding="utf-8"))
            self._check_pages(root, preview)
            self.assertIn(rel, preview)
            self.assertIn(c.sha(root / rel), preview)

    def test_stock_review_memory_is_inline_without_custom_warning(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            fixture(root)
            values = prompt._review_values(self._envelope(root), "reviews/result.md")
            values.update(
                memory="Read project memory with the granted tools.",
                diff_manifest="No changes",
                diff_evidence="No diff",
                receipt="Passed",
            )
            with contextlib.redirect_stderr(io.StringIO()) as err:
                text = prompt._render_review(root, values)
            self.assertIn("## Memory\n\nRead project memory", text)
            self.assertNotIn("memory", err.getvalue())

    def test_coding_externalizes_even_small_context_when_authority_nears_cap(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            fixture(root)
            envelope = self._envelope(root)
            envelope["acceptance"] = ["mandatory " * 1400]
            envelope["findings"] = "support context " * 100
            with mock.patch.object(prompt, "_envelope", return_value=envelope):
                text = prompt.coding(root, SID, preview=True)
            self.assertLessEqual(len(text.encode()), prompt.CODING_LIMIT)
            self.assertIn(envelope["acceptance"][0], text)
            self.assertIn("context.md", text)

    def test_source_priority_includes_c_headers_sql_and_numbered_data(self):
        bulk = [{"path": f"01_data/{number:04d}.csv"} for number in range(700)]
        sources = ["07_app/main.c", "07_app/api.h", "08_pkg/schema.sql", "01_data/load.py"]
        selected = evidence.selected_changes(bulk + [{"path": rel} for rel in sources])
        self.assertEqual({row["path"] for row in selected[:4]}, set(sources))

    def test_holistic_source_precedes_bulk_owned_by_an_earlier_slice(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            fixture(root)
            bulk = [f"01_data/{number:02d}.csv" for number in range(64)]
            for rel in bulk:
                (root / rel).write_text("bulk,1\n" * 1000, encoding="utf-8")
            source = "07_app/query.sql"
            (root / source).write_text("SELECT dependable_result;\n", encoding="utf-8")
            text = evidence.holistic_diff(
                root, "HEAD", {SID: bulk, "M001-S02": [source]}, limit=4096
            )
            self.assertIn("SELECT dependable_result", text)
            self.assertLessEqual(len(text.encode()), 4116)

    def test_excerpt_truncation_names_full_artifact_hash(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "notes.md").write_text("é" * 5000, encoding="utf-8")
            excerpt = evidence.read_excerpt(root, "notes.md", 1024)
            self.assertIn(c.sha(root / "notes.md"), excerpt)
            self.assertIn("notes.md", excerpt)

    def test_ledger_only_holistic_diff_pages_show_uncommitted_accepted_source(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            fixture(root)
            self._accepted(root)
            before = self._snapshot(root)
            preview = prompt.holistic(root, "M001", preview=True)
            self.assertEqual(before, self._snapshot(root))
            self.assertIn("answer = 1", preview)
            issued = prompt.holistic(root, "M001")
            self.assertEqual(preview, (root / issued).read_text(encoding="utf-8"))
            self._check_pages(root, preview)

    def test_holistic_prior_findings_externalize(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            fixture(root)
            self._accepted(root)
            frozen = prompt._frozen

            def large(*args):
                return {**frozen(*args), "findings": "historic context " * 5000}

            before = self._snapshot(root)
            with mock.patch.object(prompt, "_frozen", side_effect=large):
                preview = prompt.holistic(root, "M001", preview=True)
                self.assertEqual(before, self._snapshot(root))
                issued = prompt.holistic(root, "M001")
            self.assertEqual(preview, (root / issued).read_text(encoding="utf-8"))
            self._check_pages(root, preview)

    def test_review_refuses_tampered_notes_and_mandatory_overflow(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            fixture(root)
            self._verified(root, notes=True)
            rel = "05_governance/reviews/m001/notes.md"
            original = (root / rel).read_bytes()
            (root / rel).write_text("altered coder explanation\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "drift"):
                prompt.review(root, SID, preview=True)
            (root / rel).write_bytes(original)
            frozen = prompt._frozen
            with (
                mock.patch.object(
                    prompt,
                    "_frozen",
                    side_effect=lambda *args: {
                        **frozen(*args),
                        "acceptance": ["mandatory " * 6000],
                    },
                ),
                mock.patch.object(evidence, "review_diff") as diff,
            ):
                with self.assertRaisesRegex(ValueError, "49152"):
                    prompt.review(root, SID, preview=True)
                diff.assert_not_called()

    def test_sanitizer_preserves_relative_and_regex_but_scrubs_real_paths(self):
        root = Path("C:/repo")
        ordinary = "./scripts/x.py ../scripts/x.py r'^/api/(?P<id>\\d+)/$' / 1/2 2026/09/12"
        self.assertEqual(verify._scrub(ordinary.encode(), root, {}), ordinary)
        for value in (
            "/home/user/private/file.txt",
            r"C:\Users\Ada\private.txt",
            r"\\server\share\private.txt",
            "file:///home/user/private.txt",
        ):
            with self.subTest(value=value):
                self.assertIn("<absolute-path>", verify._scrub(value.encode(), root, {}))


if __name__ == "__main__":
    unittest.main()
