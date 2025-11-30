"""Entry point for the EVE Means of Profit application."""

import sys
from pathlib import Path

src_dir = Path(__file__).resolve().parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from main import main_window  # noqa: E402

if __name__ == "__main__":
    sys.exit(main_window())
