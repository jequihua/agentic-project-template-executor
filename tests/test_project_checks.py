"""Executable examples for project-owned user-path and coverage admission."""

from __future__ import annotations

import hashlib
import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

VIEWER = """import argparse,hashlib,json,pathlib,sys
parser=argparse.ArgumentParser()
parser.add_argument('action',choices=['prepare','serve'])
parser.add_argument('--output',required=True,type=pathlib.Path)
parser.add_argument('--once',action='store_true')
args=parser.parse_args()
identity={'code':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
          'input':hashlib.sha256(pathlib.Path('input.txt').read_bytes()).hexdigest()}
if args.action=='prepare':
    args.output.write_text(json.dumps({
        'identity':identity,'value':pathlib.Path('input.txt').read_text().upper()}))
else:
    saved=json.loads(args.output.read_text())
    if saved['identity']!=identity:
        sys.exit('stale output: run prepare with current code and inputs')
    print(saved['value'])
"""

REQUIRED = """import sys,unittest
suite=unittest.defaultTestLoader.discover('tests')
def ids(node):
    for item in node:
        if isinstance(item,unittest.TestSuite):
            yield from ids(item)
        else:
            yield item.id()
required={'test_product.ProductTests.test_user_path'}
if not required.issubset(set(ids(suite))):
    sys.exit('required test missing from discovery')
result=unittest.TextTestRunner().run(suite)
if any(test.id() in required for test,reason in result.skipped):
    sys.exit('required test skipped')
sys.exit(0 if result.wasSuccessful() else 1)
"""


def cli(root, *args):
    return subprocess.run(
        [sys.executable, "-B", *args],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


class ProjectChecksTests(unittest.TestCase):
    def test_prepare_exit_serve_rejects_cache_only_design_and_code_drift(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "viewer.py"
            source.write_text(
                "import sys\ncache={}\nif sys.argv[1]=='prepare': cache['value']='READY'\n"
                "else: print(cache['value'])\n"
            )
            self.assertEqual(cli(root, "viewer.py", "prepare").returncode, 0)
            broken = cli(root, "viewer.py", "serve")
            self.assertNotEqual(broken.returncode, 0)
            self.assertIn("KeyError", broken.stderr)
            source.write_text(VIEWER)
            (root / "input.txt").write_text("ready")
            self.assertEqual(
                cli(root, "viewer.py", "prepare", "--output", "current.json").returncode, 0
            )
            served = cli(root, "viewer.py", "serve", "--output", "current.json", "--once")
            self.assertEqual((served.returncode, served.stdout.strip()), (0, "READY"))
            historical = (root / "current.json").read_bytes()
            historical_sha = hashlib.sha256(historical).hexdigest()
            (root / "historical.json").write_bytes(historical)
            source.write_text(VIEWER + "\n# current implementation changed\n")
            stale = cli(root, "viewer.py", "serve", "--output", "current.json", "--once")
            self.assertNotEqual(stale.returncode, 0)
            self.assertIn("stale output", stale.stderr)
            self.assertEqual((root / "current.json").read_bytes(), historical)
            self.assertEqual(
                cli(root, "viewer.py", "prepare", "--output", "current.json").returncode, 0
            )
            self.assertEqual(
                cli(root, "viewer.py", "serve", "--output", "current.json", "--once").returncode, 0
            )
            self.assertEqual(
                hashlib.sha256((root / "historical.json").read_bytes()).hexdigest(), historical_sha
            )
            self.assertNotEqual(
                json.loads((root / "current.json").read_text()), json.loads(historical)
            )
            missing_flag = cli(root, "viewer.py", "prepare")
            self.assertEqual(missing_flag.returncode, 2)
            self.assertIn("--output", missing_flag.stderr)

    def test_required_discovery_and_skip_are_acceptance_failures(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "tests").mkdir()
            (root / "required.py").write_text(REQUIRED)
            missing = cli(root, "required.py")
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("required test missing", missing.stderr)
            test = root / "tests/test_product.py"
            body = (
                "import unittest\nclass ProductTests(unittest.TestCase):\n"
                "    def test_user_path(self):\n        self.assertEqual(2+2,4)\n"
            )
            test.write_text(body)
            self.assertEqual(cli(root, "required.py").returncode, 0)
            test.write_text(
                body.replace(
                    "    def test_user_path",
                    "    @unittest.skip('unavailable product dependency')\n    def test_user_path",
                )
            )
            skipped = cli(root, "required.py")
            self.assertNotEqual(skipped.returncode, 0)
            self.assertIn("required test skipped", skipped.stderr)

    def test_unavailable_product_dependency_cannot_hide_behind_template_tooling(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "entry.py").write_text("import unavailable_product_dependency_fixture\n")
            result = cli(root, "entry.py")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unavailable_product_dependency_fixture", result.stderr)


ROOT = Path(__file__).resolve().parents[1]


def walkthrough_recipe():
    guide = (ROOT / "docs/walkthrough.md").read_text(encoding="utf-8")
    return guide.split("<!-- rehearsal -->\n```python\n", 1)[1].split("\n```", 1)[0]


def walkthrough_artifacts():
    """Evaluate only the guide's source-building statements, without its lifecycle."""
    artifacts = {}
    namespace = {"put": artifacts.__setitem__}
    for node in ast.parse(walkthrough_recipe()).body:
        target = None
        if isinstance(node, ast.Assign):
            target = node.targets[0]
        elif isinstance(node, ast.AugAssign):
            target = node.target
        source = isinstance(target, ast.Name) and target.id in {"launcher", "code", "tests"}
        write = (
            isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name) and node.value.func.id == "put"
            and isinstance(node.value.args[0], ast.Constant)
            and node.value.args[0].value in {
                "scripts/verify_project.py", "07_app/count.py", "07_app/tests/test_count.py"
            }
        )
        if source or write:
            exec(compile(ast.Module(body=[node], type_ignores=[]), "guide", "exec"), namespace)
    return artifacts


# Observation only: the child executes the exact exported recipe. No setup is injected.
WALKTHROUGH_OBSERVER = r'''
import hashlib, json, os, pathlib, subprocess, sys
original = subprocess.run
recorded = {}
def identity():
    def git(*args):
        return original(['git', *args], capture_output=True, check=True, timeout=120).stdout
    names = git('ls-files', '--cached', '--others', '--exclude-standard', '-z')
    return dict(head=git('rev-parse', 'HEAD').decode().strip(),
        index=hashlib.sha256(git('ls-files', '--stage', '-v', '-z')).hexdigest(),
        files={os.fsdecode(p): hashlib.sha256(pathlib.Path(os.fsdecode(p)).read_bytes())
               .hexdigest() for p in set(names.split(b'\0')) if p})
def observed(argv, *args, **kwargs):
    close = 'scripts/ledger.py' in argv and 'close' in argv
    before = identity() if close else None
    if 'scripts/prompt.py' in argv and '--review' not in argv:
        status = original(['git', 'status', '--porcelain'], capture_output=True,
            check=True, timeout=120).stdout.decode()
        stored = original(['git', 'show', 'HEAD:scripts/verify_project.py'],
            capture_output=True, check=True, timeout=120).stdout
        print('ISSUE ' + json.dumps(dict(argv=argv[2:], status=status,
            committed_launcher=stored.decode(),
            launcher_matches=stored == pathlib.Path('scripts/verify_project.py').read_bytes())))
    if 'scripts/ledger.py' in argv and 'record' in argv:
        path = argv[-1]
        recorded[path] = hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
    result = original(argv, *args, **kwargs)
    if close:
        print('CLOSE ' + json.dumps(dict(argv=argv[2:], exit=result.returncode,
            before=before, after=identity())))
    return result
subprocess.run = observed
print('IMPORTS ' + json.dumps(dict(path=sys.path, pythonpath=os.environ.get('PYTHONPATH'),
    tests_present=pathlib.Path('tests').exists())))
exec(compile(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'), 'rehearse.py', 'exec'))
assert all(hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() == h
           for p, h in recorded.items())
print('REPORTS ' + json.dumps(recorded))
print('MODULES ' + json.dumps(sorted(sys.modules)))
'''


class WalkthroughTests(unittest.TestCase):
    def setUp(self):
        self.evidence = {}

    def test_walkthrough_links_reach_promised_guidance(self):
        guide = (ROOT / "docs/walkthrough.md").read_text(encoding="utf-8")
        expected = {
            "operating.md#manual-slice-walkthrough": ("--preview", "coded", "--review"),
            "project_checks.md#raw-evidence-and-current-output": ("-text", "raw"),
            "autonomy.md#exact-grant-grammar": ("Q001", "run"),
            "operating.md#steering-and-closure": ("--holistic", "close"),
            "upgrading.md#exceptional-commands": ("resolve", "recover --execute"),
            "upgrading.md#compatibility": ("qualification", "/2"),
        }
        links = re.findall(r"\[[^\]]+\]\(([^)]+)\)", guide)
        self.assertEqual(set(links), set(expected))
        for link in links:
            with self.subTest(link=link):
                path, fragment = link.split("#")
                destination = (ROOT / "docs" / path).read_text(encoding="utf-8")
                headings = re.findall(r"^#+ (.+)$", destination, re.M)
                anchors = [re.sub(r"[^\w -]", "", h.lower()).replace(" ", "-")
                           for h in headings]
                self.assertIn(fragment, anchors)
                for promised in expected[link]:
                    self.assertIn(promised, destination)
        for rel, link in [("README.md", "docs/walkthrough.md"),
                          ("docs/operating.md", "walkthrough.md"),
                          ("docs/project_checks.md", "walkthrough.md")]:
            self.assertIn(f"[CSV walkthrough]({link})", (ROOT / rel).read_text(encoding="utf-8"))

    def command(self, root, *args, expected=0, optimize=None):
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        if optimize is not None:
            env["PYTHONOPTIMIZE"] = str(optimize)
        result = subprocess.run(
            args, cwd=root, env=env, capture_output=True, timeout=120, check=False
        )
        self.evidence.setdefault("commands", []).append({
            "argv": list(args), "exit": result.returncode,
            "stdout": result.stdout.decode(errors="replace"),
            "stderr": result.stderr.decode(errors="replace"),
        })
        self.assertEqual(result.returncode, expected, result.stderr.decode(errors="replace"))
        return result.stdout

    def protected_fixture(self, root):
        import yaml
        from test_prompts_v2 import fixture

        fixture(root)
        artifacts = walkthrough_artifacts()
        (root / "scripts/verify_project.py").write_bytes(
            artifacts["scripts/verify_project.py"].encode()
        )
        plan = yaml.safe_load((root / "roadmap.yaml").read_bytes())
        plan["verification"]["full"] = ["python", "-B", "scripts/verify_project.py"]
        plan["verification"]["observation"] = "fresh_process"
        (root / "roadmap.yaml").write_text(
            yaml.safe_dump(plan, sort_keys=False), encoding="utf-8", newline="\n"
        )
        self.command(root, "git", "add", ".")
        self.command(root, "git", "commit", "-qm", "Protected guide launcher")
        self.command(root, sys.executable, "-B", "scripts/prompt.py", "M001-S01")
        (root / "07_app/tests").mkdir(exist_ok=True)
        return artifacts

    def test_final_launcher_native_receipt_matrix(self):
        artifacts = walkthrough_artifacts()
        correct = artifacts["07_app/count.py"]
        substantive = artifacts["07_app/tests/test_count.py"]
        noop = (
            "import unittest\nclass CountTests(unittest.TestCase):\n"
            "    def test_user_path(self):\n        pass\n"
            "    def test_missing(self):\n        pass\n"
        )
        wrong = correct.replace("{'rows': rows}", "{'rows': 999}")
        cases = [
            ("correct_substantive", correct, substantive, True, "Ran 2 tests"),
            ("correct_noop", correct, noop, True, "Ran 2 tests"),
            ("wrong_substantive", wrong, substantive, False, "project tests failed"),
            ("wrong_noop", wrong, noop, False, "{'rows': 999} != {'rows': 2}"),
            ("quoted", correct.replace("for row in csv.reader(stream)", "for row in stream"),
             noop, False, "{'rows': 2} != {'rows': 1}"),
            ("mutation", correct + "from pathlib import Path\n"
             "Path(sys.argv[1]).write_bytes(b'changed')\n", noop, False, "path.read_bytes()"),
            ("success_exit", correct + "sys.exit(3)\n", noop, False, "3 != 0"),
            ("success_stderr", correct + "print('noise', file=sys.stderr)\n",
             noop, False, "'noise\\n' != ''"),
            ("extra_json", correct.replace("{'rows': rows}", "{'rows': rows, 'extra': 0}"),
             noop, False, "{'rows': 2, 'extra': 0} != {'rows': 2}"),
            ("missing_exit", correct.replace("sys.exit(2)", "sys.exit(0)"),
             noop, False, "0 != 2"),
            ("missing_stdout", correct.replace("sys.exit(2)", "print('noise')\n    sys.exit(2)"),
             noop, False, "'noise\\n' != ''"),
            ("missing_stderr", correct.replace("'input not found'", "'missing'"),
             noop, False, "'missing\\n' != 'input not found\\n'"),
            ("missing_creation", correct.replace("    sys.exit(2)",
             "    open(sys.argv[1], 'w').close()\n    sys.exit(2)"),
             noop, False, "True is not false"),
            ("zero", correct, "", False, "zero tests discovered"),
            ("missing_id", correct, noop.replace("test_missing", "test_other"),
             False, "required test missing"),
            ("skipped", correct, noop.replace("    def test_missing",
             "    @unittest.skip('oracle')\n    def test_missing"), False, "required test skipped"),
            ("failed", correct, noop.replace("        pass", "        self.fail('oracle')"),
             False, "project tests failed"),
        ]
        self.evidence["protected_receipts"] = []
        for optimize in (0, 1):
            for label, code, tests, ok, diagnostic in cases:
                with self.subTest(case=label, optimize=optimize), \
                        tempfile.TemporaryDirectory() as name:
                    root = Path(name)
                    self.protected_fixture(root)
                    (root / "07_app/count.py").write_bytes(code.encode())
                    (root / "07_app/tests/test_count.py").write_bytes(tests.encode())
                    self.command(root, sys.executable, "-B", "scripts/ledger.py",
                                 "coded", "M001-S01")
                    receipt_path = root / "05_governance/reviews/m001/M001-S01_r1_verification.json"
                    self.assertFalse(receipt_path.exists())
                    self.command(root, sys.executable, "-B", "scripts/verify.py", "M001-S01",
                                 expected=0 if ok else 1, optimize=optimize)
                    receipt = json.loads(receipt_path.read_bytes())
                    self.evidence["protected_receipts"].append(
                        dict(case=label, optimize=optimize, receipt=receipt)
                    )
                    self.assertEqual(receipt["ok"], ok)
                    self.assertEqual(receipt["observation"], "fresh_process")
                    self.assertTrue(receipt["witness"]["stable"])
                    self.assertEqual(receipt["witness"]["before"], receipt["witness"]["after"])
                    self.assertEqual(len(receipt["commands"]), 1)
                    command = receipt["commands"][0]
                    self.assertEqual(command["exit"], 0 if ok else 1)
                    self.assertFalse(command["timed_out"])
                    self.assertIn(diagnostic, command["stderr_tail"])
                    if label not in {"zero", "missing_id"}:
                        self.assertIn("Ran 2 tests", command["stderr_tail"])

    def test_protected_launcher_write_refused_and_preserved(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            self.protected_fixture(root)
            path = root / "scripts/verify_project.py"
            offending = path.read_bytes() + b"\n# out-of-prefix attempted change\n"
            path.write_bytes(offending)
            ledger_path = root / "05_governance/ledger.jsonl"
            before = ledger_path.read_bytes()
            self.command(root, sys.executable, "-B", "scripts/ledger.py",
                         "coded", "M001-S01", expected=2)
            self.assertIn("scripts/verify_project.py", self.evidence["commands"][-1]["stderr"])
            self.assertEqual(path.read_bytes(), offending)
            self.assertEqual(ledger_path.read_bytes(), before)
            self.assertFalse(
                (root / "05_governance/reviews/m001/M001-S01_r1_verification.json").exists()
            )
            self.evidence["refused_write"] = dict(
                path="scripts/verify_project.py", raw_sha256=hashlib.sha256(offending).hexdigest(),
                preserved=True, ledger_unchanged=True,
            )

    def test_required_launcher_refusals(self):
        assignment = next(
            node for node in ast.parse(walkthrough_recipe()).body
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "launcher"
        )
        launcher = ast.literal_eval(assignment.value)
        body = "import unittest\nclass CountTests(unittest.TestCase):\n"
        cases = [
            ("zero", "", "zero tests discovered"),
            ("missing", body + "    def test_other(self):\n        pass\n",
             "required test missing"),
            ("failed", body + "    def test_user_path(self):\n        self.fail('oracle')\n",
             "project tests failed"),
            ("skipped", body + "    @unittest.skip('oracle')\n"
             "    def test_user_path(self):\n        pass\n", "required test skipped"),
        ]
        for label, source, diagnostic in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as name:
                root = Path(name)
                (root / "07_app/tests").mkdir(parents=True)
                (root / "verify_project.py").write_bytes(launcher.encode())
                (root / "07_app/tests/test_count.py").write_bytes(source.encode())
                self.command(root, sys.executable, "-B", "verify_project.py", expected=1)
                result = self.evidence["commands"][-1]
                self.assertIn(diagnostic, result["stderr"])
                if label in {"failed", "skipped"}:
                    self.assertIn("Ran 1 test", result["stderr"])

    def test_committed_export_manual_route(self):
        with tempfile.TemporaryDirectory() as name:
            scratch = Path(name)
            source, project = scratch / "source", scratch / "csv"
            source.mkdir()
            project.mkdir()
            names = self.command(
                ROOT, "git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"
            )
            inventory = {}
            for entry in sorted(set(names.split(b"\0")) - {b""}):
                rel = os.fsdecode(entry)
                raw = (ROOT / rel).read_bytes()
                target = source / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
                inventory[rel] = dict(bytes=len(raw), raw_sha256=hashlib.sha256(raw).hexdigest())
            for args in [
                ("init",), ("config", "user.name", "Export fixture"),
                ("config", "user.email", "export@example.invalid"),
                ("add", "--all"), ("commit", "-m", "Reviewed bytes"),
            ]:
                self.command(source, "git", *args)
            commit = self.command(source, "git", "rev-parse", "HEAD").decode().strip()
            archive = scratch / "csv.zip"
            self.command(source, "git", "archive", "--format=zip", "--output", str(archive),
                         "HEAD")
            with zipfile.ZipFile(archive) as exported:
                members = {n: exported.read(n) for n in exported.namelist() if not n.endswith("/")}
                self.assertIn("docs/walkthrough.md", members)
                self.assertFalse(any(n.startswith("tests/") for n in members))
                # Tests and the repository licence are not part of a project archive.
                kept = {n for n in inventory if not n.startswith("tests/") and n != "LICENSE"}
                self.assertEqual(set(members), kept)
                for rel, raw in members.items():
                    self.assertEqual(raw, (ROOT / rel).read_bytes(), rel)
                exported.extractall(project)
            self.evidence["archive"] = dict(
                commit=commit, raw_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                bytes=archive.stat().st_size, source=inventory,
                members={n: inventory[n] for n in members},
            )
            self.command(project, sys.executable, "-B", "scripts/hermetic_verification.py",
                         expected=2)
            self.assertIn("not configured", self.evidence["commands"][-1]["stderr"])
            recipe = scratch / "rehearse.py"
            recipe.write_bytes(walkthrough_recipe().encode())
            # A single finite replay, without a maintenance path or import in the product child.
            env = dict(os.environ)
            env.pop("PYTHONPATH", None)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            replay = subprocess.run(
                [sys.executable, "-B", "-c", WALKTHROUGH_OBSERVER, str(recipe)],
                cwd=project, env=env, capture_output=True, text=True, timeout=900, check=False,
            )
            self.evidence["replay"] = dict(exit=replay.returncode, stdout=replay.stdout,
                                           stderr=replay.stderr)
            self.assertEqual(replay.returncode, 0, replay.stderr + replay.stdout[-6000:])
            closes = [json.loads(line[6:]) for line in replay.stdout.splitlines()
                      if line.startswith("CLOSE ")]
            self.assertEqual([row["exit"] for row in closes], [0, 0, 2])
            for row in closes:
                self.assertEqual(row["before"], row["after"])
            self.evidence["close_witnesses"] = closes
            changes = {p for p in closes[0]["after"]["files"]
                       if closes[0]["after"]["files"][p] != closes[1]["before"]["files"][p]}
            self.assertEqual(changes, {"roadmap.yaml", "docs/roadmap.md"})
            imports = next(json.loads(line[8:]) for line in replay.stdout.splitlines()
                           if line.startswith("IMPORTS "))
            self.assertIsNone(imports["pythonpath"])
            self.assertFalse(imports["tests_present"])
            self.assertNotIn(str(ROOT), imports["path"])
            self.evidence["imports"] = imports
            issues = [json.loads(line[6:]) for line in replay.stdout.splitlines()
                      if line.startswith("ISSUE ")]
            self.assertEqual(len(issues), 6)
            for index in (0, 1, 4, 5):
                self.assertEqual(issues[index]["status"], "")
                self.assertTrue(issues[index]["launcher_matches"])
            self.assertNotIn("test_missing", issues[0]["committed_launcher"])
            self.assertIn("test_missing", issues[4]["committed_launcher"])
            self.assertEqual(issues[4]["committed_launcher"],
                             walkthrough_artifacts()["scripts/verify_project.py"])
            self.evidence["issuance"] = issues
            modules = next(json.loads(line[8:]) for line in replay.stdout.splitlines()
                           if line.startswith("MODULES "))
            self.assertFalse(any(n.startswith(("frutlups", "test_")) for n in modules))
            self.check_history(project, replay.stdout)

    def check_history(self, root, transcript):
        import yaml

        rm = yaml.safe_load((root / "roadmap.yaml").read_bytes())
        self.assertEqual(rm["allowed_prefixes"], ["07_app/"])
        self.assertEqual([m["status"] for m in rm["milestones"]], ["done", "planned"])
        self.assertEqual([len(m["slices"]) for m in rm["milestones"]], [2, 1])
        self.assertFalse(rm["milestones"][0]["holistic_review"])
        events = [json.loads(line) for line in (root / "05_governance/ledger.jsonl")
                  .read_text().splitlines()]
        self.assertFalse(any(e["ev"] in {"milestone_done", "run_admitted", "attempt_started"}
                             for e in events))
        self.assertFalse(any(e.get("slice", "").startswith("M002") for e in events))
        self.assertEqual([(e["slice"], e["round"]) for e in events if e["ev"] == "accepted"],
                         [("M001-S01", 2), ("M001-S02", 1)])
        raw = (root / "07_app/input.csv").read_bytes()
        self.assertEqual(raw, b"name\r\nAda\r\nBob\r\n")
        normalized = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
        self.assertNotEqual(hashlib.sha256(raw).hexdigest(), normalized)
        coded = next(e for e in events if e["ev"] == "coded")
        manifest = json.loads((root / coded["manifest"]["path"]).read_bytes())
        row = next(r for r in manifest["changed"] if r["path"] == "07_app/input.csv")
        self.assertEqual(row, dict(path="07_app/input.csv", sha=normalized, kind="added", round=1))
        self.evidence["manifest"] = manifest
        review_event = next(e for e in events if e["ev"] == "artifact"
                            and e.get("path", "").startswith("prompts/for_review_agent/"))
        review = (root / review_event["path"]).read_text()
        self.assertIn(f"`07_app/input.csv` (added, normalized evidence SHA-256 `{normalized}`",
                      review)
        self.assertIn("05_governance/reviews/m001/M001-S01_r1_review.md", review)
        self.evidence["first_review_prompt"] = review
        blob = self.command(root, "git", "show", "HEAD:07_app/input.csv")
        self.assertEqual(blob, b"name\nAda\nBob\n")
        self.assertNotEqual(hashlib.sha256(raw).hexdigest(), hashlib.sha256(blob).hexdigest())
        self.assertIn(
            f"staged raw {hashlib.sha256(blob).hexdigest()} bytes {len(blob)}", transcript
        )
        self.evidence["staged"] = dict(bytes=len(blob), raw_sha256=hashlib.sha256(blob).hexdigest())
        receipts = []
        receipt_documents = []
        for event in events:
            if event["ev"] == "coded":
                self.assertTrue(all(r["path"].startswith("07_app/") for r in event["changed"]))
            if event["ev"] == "verified":
                receipts.append(event)
                receipt = json.loads((root / event["receipt"]).read_bytes())
                self.assertTrue(receipt["tree_dirty_before"])
                self.assertFalse(receipt["tree_clean_after"])
                self.assertTrue(receipt["witness"]["stable"])
                self.assertEqual(receipt["witness"]["before"], receipt["witness"]["after"])
                self.assertEqual(receipt["observation"], "fresh_process")
                self.assertEqual(receipt["commands"][0]["exit"], 0)
                count = 2 if event["slice"] == "M001-S02" else 1
                self.assertIn(f"Ran {count} test", receipt["commands"][0]["stderr_tail"])
                bound = json.loads((root / receipt["manifest"]["path"]).read_bytes())
                self.assertEqual(bound["slice"], event["slice"])
                self.assertEqual(bound["round"], event["round"])
                if (event["slice"], event["round"]) == ("M001-S01", 1):
                    self.assertEqual(receipt["manifest"], coded["manifest"])
                    self.assertEqual(bound, manifest)
                receipt_documents.append(receipt)
        self.assertEqual(len(receipts), 3)
        self.assertTrue(all(e["ok"] for e in receipts))
        self.evidence["verified"] = receipts
        self.evidence["receipts"] = receipt_documents
        self.evidence["coded"] = coded
        self.evidence["events"] = events
        report = root / "05_governance/reviews/m001/M001-S01_r1_review.md"
        sha = hashlib.sha256(report.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        corrected = (root / "05_governance/reviews/m001/M001-S01_r2_review.md").read_text()
        self.assertIn(f"| {report.relative_to(root).as_posix()} | {sha} | M001-S01-R1-F1 | "
                      "closed_by_review | - |", corrected)
        self.evidence["reports"] = {
            p.name: p.read_text() for p in report.parent.glob("*_review.md")
        }
        # Round-specific canned claims agree with the tests admitted in that round.
        reports = self.evidence["reports"]
        for name in ("M001-S01_r1_review.md", "M001-S01_r2_review.md"):
            self.assertNotIn("Missing-path", reports[name])
        self.assertIn("Missing-path exit/stdout/stderr", reports["M001-S02_r1_review.md"])
        coding = [e["path"] for e in events if e["ev"] == "prompt"]
        reviews = [e["path"] for e in events if e["ev"] == "artifact"
                   and e.get("path", "").startswith("prompts/for_review_agent/")]
        suffixes = ["M001-S01_r1.md", "M001-S01_r2.md", "M001-S02_r1.md"]
        self.assertEqual(coding, [f"prompts/for_coding_agent/{i:03}_{s}"
                                 for i, s in zip((1, 3, 5), suffixes)])
        self.assertEqual(reviews, [f"prompts/for_review_agent/{i:03}_{s}"
                                  for i, s in zip((2, 4, 6), suffixes)])
        for path, suffix in zip(reviews, suffixes):
            destination = "05_governance/reviews/m001/" + suffix[:-3] + "_review.md"
            self.assertIn(destination, (root / path).read_text(encoding="utf-8"))
        self.evidence["phase_paths"] = dict(coding=coding, reviews=reviews)
        self.assertIn("closed_by_review", (root / "05_governance/backlog.md").read_text())
        self.assertIn("next: none", transcript.lower())
        for rel in ("07_app/count.py", "07_app/tests/test_count.py", "scripts/verify_project.py"):
            text = (root / rel).read_text()
            self.assertNotIn("_workspace", text)
            self.assertNotIn("test_scaffold", text)
        self.evidence["raw"] = dict(bytes=len(raw), raw_sha256=hashlib.sha256(raw).hexdigest(),
                                    normalized_sha256=normalized)


if __name__ == "__main__":
    unittest.main()
