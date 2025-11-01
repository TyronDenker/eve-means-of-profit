"""Fuzzwork market data CSV loader for EVE Online market prices."""

import csv
import logging
from collections.abc import Iterator
from pathlib import Path

from models.eve import MarketPrice
from utils.config import Config

logger = logging.getLogger(__name__)


class FuzzworkCSVLoader:
    """Loader for Fuzzwork aggregate market data CSV files."""

    def __init__(self, base_path: Path | str | None = None):
        """Initialize the loader with a base path to Fuzzwork data.

        Args:
            base_path: Path to the Fuzzwork data directory.
                      If None, uses Config.DATA_PATH / 'fuzzwork'

        """
        if base_path is None:
            self.base_path = Config.DATA_PATH / "fuzzwork"
        else:
            self.base_path = Path(base_path)

        if not self.base_path.exists():
            logger.warning(f"Fuzzwork data path does not exist: {self.base_path}")

    def _parse_what_field(self, what: str) -> tuple[int, int, bool] | None:
        """Parse the 'what' field from Fuzzwork CSV.

        Format: regionID|typeID|isBuyOrder (e.g., "10000002|34|true")

        Args:
            what: The composite key string

        Returns:
            Tuple of (region_id, type_id, is_buy_order) or None if parsing fails

        """
        try:
            parts = what.split("|")
            if len(parts) != 3:
                logger.warning(f"Invalid 'what' field format: {what}")
                return None

            region_id = int(parts[0])
            type_id = int(parts[1])
            is_buy_order = parts[2].lower() == "true"

            return region_id, type_id, is_buy_order
        except (ValueError, IndexError) as e:
            logger.error(f"Error parsing 'what' field '{what}': {e}")
            return None

    def _parse_float_safe(self, value: str, field_name: str) -> float:
        """Safely parse a float value, returning 0.0 on error.

        Args:
            value: String value to parse
            field_name: Name of the field (for logging)

        Returns:
            Parsed float or 0.0 on error

        """
        try:
            return float(value)
        except (ValueError, TypeError) as e:
            logger.debug(f"Error parsing {field_name} '{value}': {e}, using 0.0")
            return 0.0

    def _parse_int_safe(self, value: str, field_name: str) -> int:
        """Safely parse an int value, returning 0 on error.

        Args:
            value: String value to parse
            field_name: Name of the field (for logging)

        Returns:
            Parsed int or 0 on error

        """
        try:
            return int(float(value))  # Handle "1.0" -> 1
        except (ValueError, TypeError) as e:
            logger.debug(f"Error parsing {field_name} '{value}': {e}, using 0")
            return 0

    def load_market_prices(
        self, filename: str = "aggregatecsv.csv"
    ) -> Iterator[MarketPrice]:
        """Load market prices from Fuzzwork aggregate CSV.

        CSV Format:
        what,weightedaverage,maxval,minval,stddev,median,volume,numorders,fivepercent,orderSet

        Args:
            filename: Name of the CSV file to load

        Yields:
            MarketPrice objects

        Raises:
            FileNotFoundError: If the CSV file doesn't exist

        """
        file_path = self.base_path / filename

        if not file_path.exists():
            error_msg = f"Market data file not found: {file_path}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)

        logger.info(f"Loading market prices from {file_path}...")

        try:
            with open(file_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)

                count = 0
                errors = 0

                for row in reader:
                    try:
                        # Parse the composite 'what' field
                        what_parsed = self._parse_what_field(row["what"])
                        if what_parsed is None:
                            errors += 1
                            continue

                        region_id, type_id, is_buy_order = what_parsed

                        # Build MarketPrice object with safe parsing
                        price = MarketPrice(
                            type_id=type_id,
                            region_id=region_id,
                            is_buy_order=is_buy_order,
                            weighted_average=self._parse_float_safe(
                                row["weightedaverage"], "weightedaverage"
                            ),
                            max_val=self._parse_float_safe(row["maxval"], "maxval"),
                            min_val=self._parse_float_safe(row["minval"], "minval"),
                            std_dev=self._parse_float_safe(row["stddev"], "stddev"),
                            median=self._parse_float_safe(row["median"], "median"),
                            volume=self._parse_float_safe(row["volume"], "volume"),
                            num_orders=self._parse_int_safe(
                                row["numorders"], "numorders"
                            ),
                            five_percent=self._parse_float_safe(
                                row["fivepercent"], "fivepercent"
                            ),
                            order_set=self._parse_int_safe(row["orderSet"], "orderSet"),
                        )

                        yield price
                        count += 1

                    except Exception as e:
                        logger.error(f"Failed to parse row: {row}. Error: {e}")
                        errors += 1
                        continue

                logger.info(
                    f"Loaded {count} market prices ({errors} errors) from {filename}"
                )

        except Exception as e:
            logger.error(f"Error reading market data file: {e}", exc_info=True)
            raise
