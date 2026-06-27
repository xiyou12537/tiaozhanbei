#!/usr/bin/env python3
"""
One-click launcher for the Quantum Circuit Partitioning System.

Starts both the FastAPI backend and the Vite React frontend.

Usage:
    python run.py              # Start both servers
    python run.py --backend    # Backend only (port 8000)
    python run.py --frontend   # Frontend only (port 5173)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))


def _get_python() -> str:
    """Return the path to the venv Python if available, else sys.executable."""
    venv_python = os.path.join(ROOT, "venv", "Scripts", "python.exe")
    if os.path.isfile(venv_python):
        return venv_python
    print("[system] venv not found, using system Python (may have dependency conflicts)")
    return sys.executable


def start_backend() -> subprocess.Popen:
    """Start the FastAPI backend server."""
    python = _get_python()
    print(f"[backend] Starting FastAPI on http://localhost:8000 ...")
    return subprocess.Popen(
        [python, "-m", "uvicorn", "backend.main:app",
         "--host", "0.0.0.0", "--port", "8000"],
        cwd=ROOT,
    )


def start_frontend() -> subprocess.Popen:
    """Start the Vite React dev server."""
    frontend_dir = os.path.join(ROOT, "frontend")
    print("[frontend] Starting Vite on http://localhost:5173 ...")

    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"

    # Install deps if node_modules missing
    if not os.path.isdir(os.path.join(frontend_dir, "node_modules")):
        print("[frontend] Installing dependencies (first run)...")
        subprocess.run([npm_cmd, "install"], cwd=frontend_dir, check=True)

    return subprocess.Popen(
        [npm_cmd, "run", "dev", "--", "--host"],
        cwd=frontend_dir,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Quantum Partitioning System Launcher")
    parser.add_argument("--backend", action="store_true", help="Backend only")
    parser.add_argument("--frontend", action="store_true", help="Frontend only")
    args = parser.parse_args()

    run_both = not args.backend and not args.frontend

    procs = []

    try:
        if args.backend or run_both:
            procs.append(start_backend())

        if args.frontend or run_both:
            procs.append(start_frontend())

        if run_both:
            time.sleep(3)
            print("\n" + "=" * 55)
            print("  System ready!")
            print(f"  Frontend: http://localhost:5173")
            print(f"  Backend:  http://localhost:8000/docs")
            print("=" * 55)
            webbrowser.open("http://localhost:5173")

        print("\nPress Ctrl+C to stop all servers.\n")

        # Wait for any process to exit
        while procs:
            for p in procs[:]:
                if p.poll() is not None:
                    print(f"[system] Process exited with code {p.returncode}")
                    procs.remove(p)
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n[system] Shutting down...")
    finally:
        for p in procs:
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        print("[system] All servers stopped.")


if __name__ == "__main__":
    main()
