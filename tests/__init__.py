"""Test package for the catalyst bot.

This file modifies ``sys.path`` at import time so that the project
package (located under ``src``) can be imported without installing
into the environment. Without this adjustment, ``pytest`` would not
discover the ``catalyst_bot`` package under the repository root.
"""

import sys
from pathlib import Path

# Append the ``src`` directory to sys.path to allow imports of
# catalyst_bot modules in tests.
src_path = Path(__file__).resolve().parents[1] / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))