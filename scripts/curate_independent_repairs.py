"""Curate function and object repair tasks from the pinned Exercism Python checkout."""

import argparse
import ast
import copy
import io
import json
from pathlib import Path
import re
import sys
import types
import unittest

PIN = "479f11b44b02337b0413e805b948491c2179615a"
DATA = (
    Path(__file__).resolve().parents[1]
    / "src/sandboxed_agent_eval_harness/benchmarks/independent/data"
)
SKIP = set(
    """affine-cipher atbash-cipher crypto-square diffie-hellman rail-fence-cipher rotational-cipher
simple-cipher vigenere-cipher nucleotide-count point-mutations protein-translation rna-transcription
minesweeper queen-attack robot-name satellite parallel-letter-frequency rest-api grep paasio variable-length-quantity
zebra-puzzle alphametics two-fer hello-world bottle-song hexadecimal octal binary resistor-color-duo resistor-color-trio
resistor-color-expert bottle-song food-chain house pig-latin say proverbs""".split()
)
SAFE = set(
    "abc ast bisect calendar cmath collections contextlib copy csv dataclasses datetime decimal enum fractions functools heapq io itertools json math operator random re statistics string textwrap typing unicodedata unittest".split()
)


def dump(x):
    return json.dumps(x, sort_keys=True, ensure_ascii=False)


def names(node):
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def exports(tree, module):
    return {
        a.asname or a.name
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module == module
        for a in node.names
    }


def safe_imports(tree, module):
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and (n.module or "").split(".")[
            0
        ] not in SAFE | {module, "__future__"}:
            return False
        if isinstance(n, ast.Import) and any(
            a.name.split(".")[0] not in SAFE for a in n.names
        ):
            return False
        if isinstance(n, ast.Name) and n.id in {
            "open",
            "exec",
            "eval",
            "__import__",
            "breakpoint",
            "input",
        }:
            return False
    return True


def error_observation(binding, following):
    """Recognize the error attribute asserted by the pinned tests, including local aliases."""
    if not isinstance(binding, ast.Name):
        return None
    arguments = {binding.id + ".exception.args[0]"}
    for st in following:
        if isinstance(st, ast.Assign) and ast.unparse(st.value) in arguments:
            arguments.update(t.id for t in st.targets if isinstance(t, ast.Name))
        if not isinstance(st, ast.Expr) or not isinstance(st.value, ast.Call):
            continue
        call = st.value
        if ast.unparse(call.func) != "self.assertEqual" or len(call.args) != 2:
            continue
        for expr, literal in (call.args, reversed(call.args)):
            if isinstance(literal, ast.Constant) and isinstance(literal.value, str):
                if ast.unparse(expr) in arguments:
                    return "error_argument"
                if ast.unparse(expr) in {"str(" + arg + ")" for arg in arguments}:
                    return "error_argument_text"
    return None


def probes(tree, module):
    imported = exports(tree, module)
    if not imported:
        return []
    preamble = []
    for st in tree.body:
        if isinstance(st, (ast.Import, ast.ImportFrom)):
            if isinstance(st, ast.ImportFrom) and st.module == module:
                st = copy.deepcopy(st)
                st.module = "subject"
            preamble.append(ast.unparse(st))
        if isinstance(st, ast.Assign) and not any(
            isinstance(n, ast.Call) for n in ast.walk(st)
        ):
            preamble.append(ast.unparse(st))
    # This pinned upstream helper asserts a nonempty message through a regex.
    nonempty_message = any(
        isinstance(fun, ast.FunctionDef)
        and fun.name == "assertRaisesWithMessage"
        and any(
            isinstance(node, ast.Call)
            and ast.unparse(node.func) == "self.assertRaisesRegex"
            and len(node.args) == 2
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value == ".+"
            for node in ast.walk(fun)
        )
        for fun in ast.walk(tree)
    )
    results = {}

    def add(prefix, val, mode=None):
        source = render(preamble, prefix, val)
        if source:
            results[source, mode] = (
                {"source": source, "observe": mode} if mode else source
            )

    for fun in [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
    ]:
        tainted = set(imported)
        prefix = []
        for pos, st in enumerate(fun.body):
            if isinstance(st, ast.Assign):
                if names(st.value) & tainted:
                    tainted.update(set().union(*(names(t) for t in st.targets)))
                prefix.append(st)
                continue
            if isinstance(st, ast.With) and len(st.items) == 1:
                expr = st.items[0].context_expr
                if (
                    isinstance(expr, ast.Call)
                    and len(st.body) == 1
                    and isinstance(st.body[0], ast.Expr)
                ):
                    val = st.body[0].value
                    if names(val) & tainted:
                        method = ast.unparse(expr.func)
                        if method == "self.assertRaises":
                            mode = error_observation(
                                st.items[0].optional_vars, fun.body[pos + 1 :]
                            )
                            add(prefix, val, mode)
                        elif (
                            method == "self.assertRaisesWithMessage"
                            and nonempty_message
                        ):
                            add(prefix, val, "error_has_message")
                break
            if not isinstance(st, ast.Expr) or not isinstance(st.value, ast.Call):
                break
            call = st.value
            if (
                not isinstance(call.func, ast.Attribute)
                or not isinstance(call.func.value, ast.Name)
                or call.func.value.id != "self"
            ):
                if names(call) & tainted:
                    prefix.append(st)
                    continue
                break
            method = call.func.attr
            if method not in {
                "assertEqual",
                "assertIs",
                "assertAlmostEqual",
                "assertTrue",
                "assertFalse",
                "assertIsNone",
                "assertCountEqual",
                "assertListEqual",
                "assertDictEqual",
                "assertSetEqual",
                "assertTupleEqual",
            }:
                break
            options = [e for e in call.args[:2] if names(e) & tainted]
            if len(options) != 1:
                break
            val = options[0]
            if method == "assertCountEqual":
                val = ast.Call(
                    func=ast.Name(id="sorted", ctx=ast.Load()), args=[val], keywords=[]
                )
            identity = method == "assertIs" and any(
                isinstance(arg, ast.Constant) and type(arg.value) is bool
                for arg in call.args
            )
            add(prefix, val, "boolean_identity" if identity else None)
    return list(results.values())


def render(preamble, prefix, val):
    needed = names(val)
    keep = []
    for st in reversed(prefix):
        if isinstance(st, ast.Assign):
            lhs = set().union(*(names(t) for t in st.targets))
            if not lhs & needed:
                continue
            needed = (needed - lhs) | names(st.value)
        elif not names(st) & needed:
            continue
        else:
            needed.update(names(st))
        keep.append(ast.unparse(st))
    if "self" in needed:
        return None
    return "\n".join(preamble + list(reversed(keep)) + ["answer = " + ast.unparse(val)])


def run_local(code, probes_):
    from sandboxed_agent_eval_harness.benchmarks.independent.repairs import WORKER

    scope = {"datetime": __import__("datetime"), "math": __import__("math"), "re": re}
    exec(WORKER[WORKER.index("def encode") : WORKER.index("# Execute probes")], scope)
    mod = types.ModuleType("subject")
    sys.modules["subject"] = mod
    try:
        exec(code, mod.__dict__)
        return [scope["observe"](p) for p in probes_]
    finally:
        sys.modules.pop("subject", None)


def official_ok(code, tests, module):
    mod = types.ModuleType(module)
    sys.modules[module] = mod
    suite = types.ModuleType("upstream_tests")
    try:
        exec(code, mod.__dict__)
        exec(tests, suite.__dict__)
        checks = unittest.defaultTestLoader.loadTestsFromModule(suite)
        res = unittest.TextTestRunner(stream=io.StringIO()).run(checks)
        return res.testsRun if res.wasSuccessful() else 0
    finally:
        sys.modules.pop(module, None)


def mutations(code):
    tree = ast.parse(code)
    swaps = {
        ast.Lt: ast.LtE,
        ast.LtE: ast.Lt,
        ast.Gt: ast.GtE,
        ast.GtE: ast.Gt,
        ast.Eq: ast.NotEq,
        ast.NotEq: ast.Eq,
        ast.And: ast.Or,
        ast.Or: ast.And,
        ast.Add: ast.Sub,
        ast.Sub: ast.Add,
    }
    for n in ast.walk(tree):
        fields = []
        if isinstance(n, ast.Compare) and len(n.ops) == 1 and type(n.ops[0]) in swaps:
            fields = [("ops", [swaps[type(n.ops[0])]()])]
        elif isinstance(n, (ast.BoolOp, ast.BinOp)) and type(n.op) in swaps:
            fields = [("op", swaps[type(n.op)]())]
        elif (
            isinstance(n, ast.Constant)
            and type(n.value) is int
            and -1 <= n.value <= 1000
        ):
            fields = [("value", n.value + 1)]
        elif isinstance(n, ast.Constant) and type(n.value) is bool:
            fields = [("value", not n.value)]
        elif isinstance(n, ast.Slice) and n.lower is None:
            fields = [("lower", ast.Constant(value=1))]
        elif (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id in {"min", "max"}
        ):
            fields = [
                (
                    "func",
                    ast.Name(id="max" if n.func.id == "min" else "min", ctx=ast.Load()),
                )
            ]
        for field, new in fields:
            old = getattr(n, field)
            setattr(n, field, new)
            broken = ast.unparse(tree) + "\n"
            setattr(n, field, old)
            yield broken


def curate(folder):
    slug = folder.name
    examples = list((folder / ".meta").glob("example.py")) + list(
        (folder / ".meta").glob("exemplar.py")
    )
    t = list(folder.glob("*_test.py"))
    if slug in SKIP or not examples or len(t) != 1:
        return
    module = t[0].name[:-8]
    code = examples[0].read_text()
    tests = t[0].read_text()
    tree = ast.parse(tests)
    if not safe_imports(tree, module) or not safe_imports(ast.parse(code), module):
        return
    qs = probes(tree, module)
    if len(qs) < 3:
        return
    try:
        n = official_ok(code, tests, module)
    except Exception:
        return
    if n < 3:
        return
    expected = run_local(code, qs)
    if any(
        x[0] == "error"
        and x[1]
        in {
            "NameError",
            "ImportError",
            "ModuleNotFoundError",
            "AttributeError",
            "TypeError",
            "NotImplementedError",
        }
        for x in expected
    ):
        return
    if expected != run_local(code, qs):
        return
    # Timeouts exclude mutations which introduce nontermination.
    import signal

    class MutationTimeout(BaseException):
        pass

    def interrupt(*args):
        raise MutationTimeout()

    signal.signal(signal.SIGALRM, interrupt)
    for bad in mutations(code):
        try:
            signal.setitimer(signal.ITIMER_REAL, 0.3)
            actual = run_local(bad, qs)
        except (Exception, MutationTimeout):
            continue
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
        differences = sum(a != b for a, b in zip(actual, expected))
        if not 0 < differences < len(qs) or not any(
            a != b and a[0] == b[0] and a[0] in {"value", "boolean"}
            for a, b in zip(actual, expected)
        ):
            continue
        doc = "\n\n".join(
            f.read_text().strip()
            for f in [
                folder / ".docs/introduction.md",
                folder / ".docs/instructions.md",
                folder / ".docs/instructions.append.md",
            ]
            if f.is_file()
        )
        if not doc:
            continue
        prompt = (
            "Repair the defect in subject.py. Preserve the documented Python interface and return values.\n\n"
            + doc
        )
        loc = folder.relative_to(folder.parents[2]).as_posix()
        task = dict(
            task_id="repair-" + slug,
            domain="coding",
            source_group="exercism/" + slug,
            instruction=prompt,
            tool="python.repair",
            provenance="https://github.com/exercism/python/tree/" + PIN + "/" + loc,
            starter=bad,
        )
        key = dict(
            task_id=task["task_id"],
            reference=code,
            probes=qs,
            expected=expected,
            upstream_tests_passed=n,
            incorrect_probes=differences,
        )
        return task, key


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("checkout", type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for folder in sorted((args.checkout / "exercises").glob("*/*")):
        if not folder.is_dir():
            continue
        try:
            result = curate(folder)
            if result:
                (args.output / (folder.name + ".json")).write_text(dump(result) + "\n")
                print(folder.name, flush=True)
        except (Exception, SystemExit) as e:
            print("skip", folder.name, type(e).__name__, file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
