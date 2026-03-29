"""Pre-commit wrapper for pytest unit tests.

Exit code 5 (no tests collected) is treated as success —
allows committing before any unit tests are written.
"""

import subprocess
import sys

result = subprocess.run(
    ["uv", "run", "pytest", "tests/unit/", "-q", "--tb=short"],
    check=False,
)

# 0 = tests passed, 5 = no tests collected (both are OK)
sys.exit(0 if result.returncode in (0, 5) else result.returncode)
