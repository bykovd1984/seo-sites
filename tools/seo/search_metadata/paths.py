"""Resolve the workspace used for local ManualsDump artifacts."""
import os
from pathlib import Path

package = Path(__file__).resolve().parent
source_root = package.parents[2] if package.parent.name == 'seo' and package.parent.parent.name == 'tools' else Path.cwd()
ROOT = Path(os.environ.get('MANUALSDUMP_WORKSPACE', source_root)).resolve()
