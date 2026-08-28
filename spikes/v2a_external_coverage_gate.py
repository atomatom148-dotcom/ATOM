#!/usr/bin/env python3
"""Dependency-free statement coverage gate for the Phase 1B adapter."""
from __future__ import annotations
import ast
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"quant"/"v9_v2a_external.py"

def main() -> None:
    with tempfile.TemporaryDirectory(prefix="atom-v2a-coverage-") as name:
        command=[sys.executable,"-m","trace","--count","--coverdir",name,
            "--ignore-dir",f"{sys.base_prefix}:/usr/lib","--module","pytest","-q",
            "tests/test_v2a_external_parity.py"]
        subprocess.run(command,cwd=ROOT,check=True)
        covered=(Path(name)/"quant.v9_v2a_external.cover").read_text().splitlines()
    statements={node.lineno for node in ast.walk(ast.parse(SOURCE.read_text()))
                if isinstance(node,ast.stmt) and not isinstance(node,(ast.Import,ast.ImportFrom))}
    executed={line for line,text in enumerate(covered,1)
              if text[:6].strip().rstrip(":").isdigit()}
    ratio=len(statements & executed)/len(statements)
    print(f"external_v2a_statement_coverage={ratio:.2%} ({len(statements & executed)}/{len(statements)})")
    if ratio < .80: raise SystemExit("external V2A coverage is below 80%")

if __name__=="__main__": main()
