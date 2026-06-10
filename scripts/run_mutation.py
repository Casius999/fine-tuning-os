#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Mutation testing runner for core pure modules.

Applies targeted mutations to sanitize.py / crypto.py / targets.py /
envelope.py, runs pytest for each, and reports killed / survived / score.

Usage:
    python scripts/run_mutation.py

Writes results to mutation_results.txt in the project root.
"""

from __future__ import annotations

import ast
import copy
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Mutation operators
# ---------------------------------------------------------------------------


@dataclass
class Mutation:
    module: str
    line: int
    col: int
    description: str
    original_source: str
    mutated_source: str


def _replace_line(source: str, lineno: int, new_line: str) -> str:
    """Replace a 1-indexed line in *source* with *new_line*."""
    lines = source.splitlines(keepends=True)
    # Preserve trailing newline
    if new_line and not new_line.endswith("\n"):
        new_line += "\n"
    lines[lineno - 1] = new_line
    return "".join(lines)


class MutationVisitor(ast.NodeVisitor):
    """Walk AST and generate Mutation objects for targeted operators."""

    def __init__(self, source: str, module_path: str) -> None:
        self.source = source
        self.module_path = module_path
        self.mutations: list[Mutation] = []
        self._lines = source.splitlines()

    def _orig_line(self, lineno: int) -> str:
        return self._lines[lineno - 1] if lineno <= len(self._lines) else ""

    # ---- Comparison operators -----------------------------------------------

    def visit_Compare(self, node: ast.Compare) -> None:
        for i, op in enumerate(node.ops):
            ops_map: dict[type[ast.cmpop], list[type[ast.cmpop]]] = {
                ast.Lt: [ast.LtE, ast.Gt, ast.GtE],
                ast.LtE: [ast.Lt, ast.Gt, ast.GtE],
                ast.Gt: [ast.GtE, ast.Lt, ast.LtE],
                ast.GtE: [ast.Gt, ast.Lt, ast.LtE],
                ast.Eq: [ast.NotEq],
                ast.NotEq: [ast.Eq],
                ast.Is: [ast.IsNot],
                ast.IsNot: [ast.Is],
            }
            replacements = ops_map.get(type(op), [])
            for replacement_cls in replacements[:1]:  # one replacement per op
                new_op = replacement_cls()
                new_node = copy.deepcopy(node)
                new_node.ops[i] = new_op  # type: ignore[assignment]
                orig_src = ast.unparse(node)
                mut_src = ast.unparse(new_node)
                orig_line = self._orig_line(node.lineno)
                # Only mutate if the expression text is on this line
                if orig_src in orig_line:
                    mut_line = orig_line.replace(orig_src, mut_src, 1)
                    mutated_source = _replace_line(self.source, node.lineno, mut_line)
                    self.mutations.append(
                        Mutation(
                            module=self.module_path,
                            line=node.lineno,
                            col=node.col_offset,
                            description=f"Compare {orig_src!r} → {mut_src!r}",
                            original_source=self.source,
                            mutated_source=mutated_source,
                        )
                    )
        self.generic_visit(node)

    # ---- Boolean return values ----------------------------------------------

    def visit_Return(self, node: ast.Return) -> None:
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, bool):
            orig_val = node.value.value
            mut_val = not orig_val
            orig_line = self._orig_line(node.lineno)
            orig_text = f"return {orig_val}"
            mut_text = f"return {mut_val}"
            if orig_text in orig_line:
                mut_line = orig_line.replace(orig_text, mut_text, 1)
                mutated_source = _replace_line(self.source, node.lineno, mut_line)
                self.mutations.append(
                    Mutation(
                        module=self.module_path,
                        line=node.lineno,
                        col=node.col_offset,
                        description=f"Return {orig_val} → {mut_val}",
                        original_source=self.source,
                        mutated_source=mutated_source,
                    )
                )
        self.generic_visit(node)

    # ---- Constant mutations -------------------------------------------------

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, int) and not isinstance(node.value, bool) and node.value > 0:
            orig_line = self._orig_line(node.lineno)
            orig_text = str(node.value)
            # Only mutate standalone literals (not in string context)
            for replacement in [node.value + 1, node.value - 1]:
                mut_text = str(replacement)
                # Avoid replacing inside larger numbers (guard with word boundary logic)
                if (
                    f" {orig_text}" in orig_line
                    or f"={orig_text}" in orig_line
                    or f"({orig_text}" in orig_line
                ):
                    mut_line = orig_line.replace(orig_text, mut_text, 1)
                    if mut_line != orig_line:
                        mutated_source = _replace_line(self.source, node.lineno, mut_line)
                        self.mutations.append(
                            Mutation(
                                module=self.module_path,
                                line=node.lineno,
                                col=node.col_offset,
                                description=f"Constant {node.value} → {replacement} at line {node.lineno}",
                                original_source=self.source,
                                mutated_source=mutated_source,
                            )
                        )
                        break  # one mutation per constant
        self.generic_visit(node)

    # ---- AugAssign mutations (count += n → count += 0) ----------------------

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if isinstance(node.op, ast.Add) and isinstance(node.value, ast.Name):
            orig_line = self._orig_line(node.lineno)
            target_src = ast.unparse(node.target)
            value_src = ast.unparse(node.value)
            orig_text = f"{target_src} += {value_src}"
            mut_text = f"{target_src} += 0"
            if orig_text in orig_line:
                mut_line = orig_line.replace(orig_text, mut_text, 1)
                mutated_source = _replace_line(self.source, node.lineno, mut_line)
                self.mutations.append(
                    Mutation(
                        module=self.module_path,
                        line=node.lineno,
                        col=node.col_offset,
                        description=f"AugAssign {orig_text!r} → {mut_text!r}",
                        original_source=self.source,
                        mutated_source=mutated_source,
                    )
                )
        self.generic_visit(node)

    # ---- None return / early return -----------------------------------------

    def visit_If(self, node: ast.If) -> None:
        # Negate the condition of `if not x:` → `if x:`
        if isinstance(node.test, ast.UnaryOp) and isinstance(node.test.op, ast.Not):
            orig_line = self._orig_line(node.lineno)
            inner = ast.unparse(node.test.operand)
            if f"not {inner}" in orig_line:
                mut_line = orig_line.replace(f"not {inner}", inner, 1)
                mutated_source = _replace_line(self.source, node.lineno, mut_line)
                self.mutations.append(
                    Mutation(
                        module=self.module_path,
                        line=node.lineno,
                        col=node.col_offset,
                        description=f"Negate removal: 'not {inner}' → '{inner}'",
                        original_source=self.source,
                        mutated_source=mutated_source,
                    )
                )
        self.generic_visit(node)


def collect_mutations(module_path: Path) -> list[Mutation]:
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(module_path))
    visitor = MutationVisitor(source, str(module_path))
    visitor.visit(tree)
    # Deduplicate by (line, description)
    seen: set[tuple[int, str]] = set()
    result: list[Mutation] = []
    for m in visitor.mutations:
        key = (m.line, m.description)
        if key not in seen:
            seen.add(key)
            result.append(m)
    return result


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------


def run_tests(project_root: Path, mutated_source: str, module_path: Path) -> bool:
    """Apply mutation, run pytest on fast unit tests, restore. Return True if tests FAIL (mutation killed)."""
    original = module_path.read_text(encoding="utf-8")
    module_path.write_text(mutated_source, encoding="utf-8")
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/",
                # Exclude integration tests — they're slow and not relevant here
                "--ignore=tests/test_live_integration.py",
                "--ignore=tests/test_mcp_live.py",
                "-x",  # stop on first failure
                "-q",
                "--tb=no",
                "--no-header",
                "--timeout=30",
            ],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=60,
        )
        # Killed = tests failed (non-zero exit)
        return result.returncode != 0
    except subprocess.TimeoutExpired:
        return True  # timeout = killed
    finally:
        module_path.write_text(original, encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    project_root = Path(__file__).parent.parent
    modules = [
        project_root / "src/fine_tuning_os/sanitize.py",
        project_root / "src/fine_tuning_os/crypto.py",
        project_root / "src/fine_tuning_os/targets.py",
        project_root / "src/fine_tuning_os/envelope.py",
    ]

    all_mutations: list[tuple[Mutation, bool]] = []  # (mutation, killed)
    total = killed = survived = 0

    print("=" * 70)
    print("MUTATION TESTING — core pure modules")
    print("=" * 70)

    for module in modules:
        mutations = collect_mutations(module)
        module_name = module.name
        print(f"\n[{module_name}] {len(mutations)} mutations")

        for i, mut in enumerate(mutations, 1):
            is_killed = run_tests(project_root, mut.mutated_source, module)
            status = "KILLED" if is_killed else "SURVIVED"
            total += 1
            if is_killed:
                killed += 1
            else:
                survived += 1
            print(f"  [{i:3d}/{len(mutations)}] {status:8s}  L{mut.line}: {mut.description}")
            all_mutations.append((mut, is_killed))

    score_pct = round(killed / total * 100) if total else 0
    summary = textwrap.dedent(f"""
        ================================================================
        MUTATION SCORE SUMMARY
        ================================================================
        Total mutations : {total}
        Killed          : {killed}
        Survived        : {survived}
        Score           : {score_pct}%  ({killed}/{total} killed)
        ================================================================
    """).strip()
    print("\n" + summary)

    # Write detailed results
    results_file = project_root / "mutation_results.txt"
    with results_file.open("w", encoding="utf-8") as f:
        f.write(summary + "\n\n")
        f.write("SURVIVED MUTATIONS (need attention):\n")
        for mut, is_killed in all_mutations:
            if not is_killed:
                f.write(f"  {Path(mut.module).name}:{mut.line}  {mut.description}\n")
        f.write("\nALL MUTATIONS:\n")
        for mut, is_killed in all_mutations:
            status = "KILLED" if is_killed else "SURVIVED"
            f.write(f"  {status:8s}  {Path(mut.module).name}:{mut.line}  {mut.description}\n")

    print(f"\nDetailed results written to: {results_file}")


if __name__ == "__main__":
    main()
