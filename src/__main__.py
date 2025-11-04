"""Entry point for the EVE Means of Profit application."""

import sys
from pathlib import Path

# Add the src directory to the Python module search path
src_dir = Path(__file__).resolve().parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
