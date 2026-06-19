"""Bundle external assets, sync static_site mirror, and verify deploy readiness."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def run(name: str) -> int:
    path = SCRIPTS / name
    print(f"\n=== {name} ===")
    result = subprocess.run([sys.executable, str(path)], cwd=str(ROOT))
    return result.returncode


def main() -> int:
    steps = [
        "bundle_deploy_assets.py",
        "sync_static_site_assets.py",
        "verify_deploy_assets.py",
    ]
    for step in steps:
        code = run(step)
        if code != 0:
            print(f"\nFailed at {step} (exit {code})")
            return code
    print("\nDeploy bundle ready — MiNe folder is self-contained.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
