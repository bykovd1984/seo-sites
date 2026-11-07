"""Portable launcher: optional SDK packages are isolated under ignored artifacts."""
import site
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEPENDENCIES = ROOT / 'artifacts/seo-research/dependencies'
if DEPENDENCIES.is_dir():
    # Process pywin32's .pth bootstrap as well as ordinary modules on Windows.
    site.addsitedir(str(DEPENDENCIES))
    sys.path.insert(0, str(DEPENDENCIES))

from research_hub.cli import main

if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, TypeError) as exc:
        raise SystemExit(str(exc) if isinstance(exc, ValueError) else 'Invalid input structure') from None
    except OSError as exc:
        raise SystemExit('Local operation failed: '+type(exc).__name__) from None
