"""Development entry point for MiNe.

Prefer the project `.venv` so `python run.py` works even when system Python
is missing packages (e.g. python-dotenv).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _venv_python() -> Path:
    if os.name == "nt":
        return ROOT / ".venv" / "Scripts" / "python.exe"
    return ROOT / ".venv" / "bin" / "python"


def _ensure_runtime() -> None:
    """Prefer project venv so `python run.py` works without manual activation."""
    try:
        import dotenv  # noqa: F401
        import flask  # noqa: F401

        return
    except ImportError:
        pass

    vpy = _venv_python()
    if not vpy.is_file():
        print("Required packages are missing and .venv was not found.")
        print("Set up once:")
        print("  python -m venv .venv")
        print(r"  .\.venv\Scripts\python -m pip install -r requirements.txt")
        print("Then run:")
        print("  python run.py")
        sys.exit(1)

    if Path(sys.executable).resolve() == vpy.resolve():
        print("Packages are missing inside .venv. Install deps:")
        print(r"  .\.venv\Scripts\python -m pip install -r requirements.txt")
        sys.exit(1)

    print(f"Using project virtualenv: {vpy}")
    os.execv(str(vpy), [str(vpy), str(ROOT / "run.py"), *sys.argv[1:]])


_ensure_runtime()

from mine import create_app  # noqa: E402

app = create_app()


def _port_in_use(port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("0.0.0.0", port))
        except OSError:
            return True
    return False


if __name__ == "__main__":
    # Default 5000. Do not set PORT=5001 here — that port is reserved for the GE app.
    port = int(os.environ.get("PORT", "5000"))
    if port == 5001:
        print("Warning: port 5001 is normally used by GE. MiNe should use 5000.")
    if _port_in_use(port):
        print(f"Port {port} is already in use.")
        print("If you see the GE site at http://127.0.0.1:5000, stop GE first (Ctrl+C),")
        print("or run GE on 5001:  cd Desktop\\GE && python run.py")
        sys.exit(1)
    print(f"MiNe (Freeport portal) — http://127.0.0.1:{port}")
    print("GE (if running) should be on http://127.0.0.1:5001")
    app.run(host="0.0.0.0", port=port, debug=True)
