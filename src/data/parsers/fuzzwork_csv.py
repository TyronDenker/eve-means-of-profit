"""Parser for Fuzzwork market aggregate CSV data.

Expected CSV layout (first field contains pipe-separated values):

Header example:
    regionid|typeid|isbuyorder,weightedaverage,maxval,minval,stddev,median,volume,numorders,fivepercent,orderSet

Row example:
    10000002|34|0,1000.0,1500.0,500.0,200.0,900.0,1000000,50,1100.0,SET

The parser aggregates rows into MarketDataPoint models.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

from models.app import (
    FuzzworkMarketDataPoint,
    FuzzworkMarketStats,
    FuzzworkRegionMarketData,
)

logger = logging.getLogger(__name__)


class FuzzworkCSVParser:
    """Parser for Fuzzwork aggregate market CSV files.

    This parser expects the first CSV column containing pipe-separated
    values regionid|typeid|isbuyorder followed by comma-separated
    values for the rest of the fields. The parser extracts the first three
    pipe-separated fields as `region_id`, `type_id`, and `is_buy_order`, and
    maps the remaining CSV columns to known headers.
    """

    _REST_KEYS: ClassVar[list[str]] = [
        "weightedaverage",
        "maxval",
        "minval",
        "stddev",
        "median",
        "volume",
        "numorders",
        "fivepercent",
        "orderSet",
    ]

    def __init__(self, csv_data: str | Path):
        if isinstance(csv_data, Path):
            self.csv_text = csv_data.read_text(encoding="utf-8")
        else:
            self.csv_text = csv_data or ""

    def load_market_data(self) -> Iterator[FuzzworkMarketDataPoint]:
        """Load and yield FuzzworkMarketDataPoint objects from CSV data.

        Aggregates CSV rows by type_id and region_id, separating buy/sell data.

        Yields:
            FuzzworkMarketDataPoint objects with full market statistics

        """
        snapshot_time = datetime.now(UTC)

        # Temporary structure: type_id -> region_id -> (buy_row, sell_row)
        aggregated: dict[int, dict[int, dict[str, dict | None]]] = defaultdict(
            lambda: defaultdict(lambda: {"buy": None, "sell": None})
        )

        # Parse and aggregate CSV rows
        for row in self._parse():
            type_id = row["type_id"]
            region_id = row["region_id"]
            is_buy = row["is_buy_order"]

            # Create stats data from row
            stats_data = {
                "weighted_average": row["weighted_average"],
                "max_price": row["max_val"],
                "min_price": row["min_val"],
                "stddev": row["stddev"],
                "median": row["median"],
                "volume": row["volume"],
                "num_orders": row["num_orders"],
                "five_percent": row["five_percent"],
            }

            # Store in appropriate bucket
            order_type = "buy" if is_buy else "sell"
            aggregated[type_id][region_id][order_type] = stats_data

        # Yield MarketDataPoint objects
        for type_id, regions_dict in aggregated.items():
            region_data: dict[int, FuzzworkRegionMarketData] = {}

            for region_id, orders in regions_dict.items():
                try:
                    buy_stats = (
                        FuzzworkMarketStats(**orders["buy"])
                        if orders["buy"] is not None
                        else None
                    )
                    sell_stats = (
                        FuzzworkMarketStats(**orders["sell"])
                        if orders["sell"] is not None
                        else None
                    )

                    region_data[region_id] = FuzzworkRegionMarketData(
                        region_id=region_id,
                        buy_stats=buy_stats,
                        sell_stats=sell_stats,
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to parse market data for type {type_id}, "
                        f"region {region_id}: {e}"
                    )
                    continue

            try:
                yield FuzzworkMarketDataPoint(
                    type_id=type_id,
                    snapshot_time=snapshot_time,
                    region_data=region_data,
                )
            except Exception as e:
                logger.error(
                    f"Failed to create FuzzworkMarketDataPoint for type {type_id}: {e}"
                )
                continue

    def _parse_line(self, line: str) -> dict[str, Any] | None:
        """Parse a single CSV line.

        Handles a first field that may contain pipe-separated values.
        """
        # Be strict about input format: let exceptions propagate to the caller.
        first_block, rest = line.split(",", 1)
        rest_values = [v.strip() for v in rest.split(",")]

        parts = [p.strip() for p in first_block.split("|")]

        region_id = int(parts[0])
        type_id = int(parts[1])
        is_buy_order = parts[2] == "true"

        kv = dict(zip(self._REST_KEYS, rest_values, strict=True))

        weighted_average = float(kv["weightedaverage"])  # may raise

        return {
            "region_id": region_id,
            "type_id": type_id,
            "is_buy_order": is_buy_order,
            "weighted_average": weighted_average,
            "max_val": float(kv["maxval"]),
            "min_val": float(kv["minval"]),
            "stddev": float(kv["stddev"]),
            "median": float(kv["median"]),
            "volume": int(float(kv["volume"])),
            "num_orders": int(float(kv["numorders"])),
            "five_percent": float(kv["fivepercent"]),
        }

    def _parse(self) -> Iterator[dict[str, Any]]:
        """Yield parsed rows as dicts.

        Returned keys:
            - region_id (int)
            - type_id (int)
            - is_buy_order (bool)  # True if buy order, False otherwise
            - weighted_average (float)
            - max_val (float)
            - min_val (float)
            - stddev (float)
            - median (float)
            - volume (int)
            - num_orders (int)
            - five_percent (float)
        """
        if not self.csv_text:
            return

        lines = [ln for ln in self.csv_text.splitlines() if ln.strip()]
        if not lines:
            return

        # Skip header
        data_lines = lines[1:]

        for idx, line in enumerate(data_lines, start=2):
            try:
                parsed = self._parse_line(line)
                if parsed is not None:
                    yield parsed
            except Exception as e:
                logger.warning("Failed to parse line %d: %s (line: %r)", idx, e, line)
                continue
