"""Installed entry point for the existing ManualsDump console."""
import sys
from pathlib import Path


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from app import main as run
    try:
        run()
    except (ValueError, RuntimeError) as exc:
        raise SystemExit(str(exc)) from None


def drafts_main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from codex_drafts import main as run
    try:
        run()
    except (ValueError, RuntimeError) as exc:
        raise SystemExit(str(exc)) from None


def groups_main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from codex_groups import main as run
    try:
        run()
    except (ValueError, RuntimeError) as exc:
        raise SystemExit(str(exc)) from None
