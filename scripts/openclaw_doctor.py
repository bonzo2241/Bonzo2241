#!/usr/bin/env python3
"""Quick diagnostics for running LMS with real OpenClaw + LLM support."""

from __future__ import annotations

import importlib
import os
import socket
import sys
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass
class Check:
    name: str
    ok: bool
    details: str


def _check_import(module: str) -> Check:
    try:
        mod = importlib.import_module(module)
        return Check(f"python import: {module}", True, getattr(mod, "__file__", "built-in"))
    except Exception as exc:
        return Check(f"python import: {module}", False, repr(exc))


def _check_env(name: str, required: bool = True) -> Check:
    value = os.getenv(name, "")
    if value:
        masked = value[:8] + "..." if len(value) > 12 else "***"
        return Check(f"env: {name}", True, f"set ({masked})")
    if required:
        return Check(f"env: {name}", False, "not set")
    return Check(f"env: {name}", True, "not set (optional)")


def _check_gateway(url: str) -> Check:
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=2):
            return Check("openclaw gateway socket", True, f"reachable at {host}:{port}")
    except Exception as exc:
        return Check("openclaw gateway socket", False, f"{host}:{port} unreachable: {exc}")


def main() -> int:
    gateway = os.getenv("OPENCLAW_GATEWAY_URL", "http://localhost:18789")

    checks = [
        _check_import("openclaw"),
        _check_import("openai"),
        _check_env("OPENAI_API_KEY", required=True),
        _check_env("OPENAI_BASE_URL", required=False),
        _check_env("AI_MODEL", required=False),
        _check_gateway(gateway),
    ]

    print("OpenClaw/LLM doctor")
    print("=" * 60)
    print(f"OPENCLAW_GATEWAY_URL={gateway}")
    print("-" * 60)

    failures = 0
    for ch in checks:
        status = "OK" if ch.ok else "FAIL"
        print(f"[{status}] {ch.name}: {ch.details}")
        if not ch.ok:
            failures += 1

    print("-" * 60)
    if failures == 0:
        print("All checks passed. You can run: python run.py")
        return 0

    print(
        "Some checks failed.\n"
        "Recommended quick fix order:\n"
        "  1) pip install -r requirements.txt\n"
        "  2) start openclaw gateway\n"
        "  3) export OPENAI_API_KEY=...\n"
        "  4) run python run.py"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
