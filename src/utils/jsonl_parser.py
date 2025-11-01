"""JSONL file parsing utilities."""

import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class JSONLParser:
    """Parser for JSONL (JSON Lines) files."""

    def __init__(self, file_path: Path | str):
        """Initialize the parser.

        Args:
            file_path: Path to the JSONL file

        """
        self.file_path = Path(file_path)
        self.errors: list[tuple[int, str]] = []

    def parse(self, sample_size: int | None = None) -> Iterator[dict[str, Any]]:
        """Parse JSONL file and yield JSON objects.

        This is a generator function for memory efficiency with large files.

        Args:
            sample_size: If provided, only yield first N records

        Yields:
            Parsed JSON objects

        """
        if not self.file_path.exists():
            logger.error(f"File not found: {self.file_path}")
            raise FileNotFoundError(f"File not found: {self.file_path}")

        count = 0
        with open(self.file_path, encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue

                try:
                    obj = json.loads(line)
                    yield obj
                    count += 1

                    if sample_size and count >= sample_size:
                        break

                except json.JSONDecodeError as e:
                    error_msg = f"Invalid JSON at line {line_num}: {e}"
                    logger.warning(error_msg)
                    self.errors.append((line_num, error_msg))
                    continue
