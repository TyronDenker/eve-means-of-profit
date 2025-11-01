"""Blueprint service for manufacturing calculations.

This service provides business logic for blueprint-related operations,
including cost calculations and profit analysis for manufacturing.
"""

import logging
from typing import Any

from data.managers import MarketDataManager, SDEManager

logger = logging.getLogger(__name__)


class BlueprintService:
    """Service for blueprint-related business operations.

    This service handles manufacturing cost calculations and
    profit analysis for blueprint production.
    """

    def __init__(
        self,
        sde_manager: SDEManager,
        market_manager: MarketDataManager | None = None,
    ):
        """Initialize the blueprint service.

        Args:
            sde_manager: SDEManager for blueprint and type data
            market_manager: Optional MarketDataManager for price data

        """
        self._sde_manager = sde_manager
        self._market_manager = market_manager

    def calculate_material_costs(
        self,
        blueprint_id: int,
        region_id: int = 10000002,
        activity: str = "manufacturing",
    ) -> dict[str, Any] | None:
        """Calculate material costs for a blueprint.

        Args:
            blueprint_id: Blueprint ID
            region_id: Region ID for material prices
            activity: Activity type (manufacturing, invention, etc.)

        Returns:
            Dictionary with material costs breakdown or None

        """
        blueprint = self._sde_manager.get_blueprint_by_id(blueprint_id)
        if not blueprint:
            logger.warning(f"Blueprint {blueprint_id} not found")
            return None

        # Get activity data
        activities = blueprint.activities
        if not activities or activity not in activities:
            logger.warning(f"Activity {activity} not found in blueprint {blueprint_id}")
            return None

        activity_data = activities[activity]
        materials = activity_data.get("materials", [])

        if not self._market_manager:
            logger.info("No market manager, returning material list only")
            return {
                "materials": materials,
                "total_cost": None,
                "region_id": region_id,
            }

        # Calculate costs
        material_costs: list[dict[str, Any]] = []
        total_cost = 0.0

        for material in materials:
            type_id = material.get("type_id")
            quantity = material.get("quantity", 0)

            if type_id is None:
                continue

            # Get material price
            price_data = self._market_manager.get_price(
                type_id, region_id, is_buy_order=False
            )

            unit_price = price_data.min_val if price_data else 0.0  # Use lowest sell
            line_cost = unit_price * quantity

            material_costs.append(
                {
                    "type_id": type_id,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "line_cost": line_cost,
                }
            )

            total_cost += line_cost

        return {
            "blueprint_id": blueprint_id,
            "activity": activity,
            "materials": material_costs,
            "total_cost": total_cost,
            "region_id": region_id,
        }

    def calculate_manufacturing_cost(
        self, blueprint_id: int, region_id: int = 10000002
    ) -> float | None:
        """Calculate total manufacturing cost for a blueprint.

        Args:
            blueprint_id: Blueprint ID
            region_id: Region ID for material prices

        Returns:
            Total manufacturing cost or None

        """
        cost_data = self.calculate_material_costs(
            blueprint_id, region_id, "manufacturing"
        )
        return cost_data["total_cost"] if cost_data else None

    def calculate_blueprint_profit(
        self,
        blueprint_id: int,
        region_id: int = 10000002,
        runs: int = 1,
    ) -> dict[str, Any] | None:
        """Calculate profit for manufacturing from a blueprint.

        Args:
            blueprint_id: Blueprint ID
            region_id: Region ID for prices
            runs: Number of production runs

        Returns:
            Dictionary with profit analysis or None

        """
        blueprint = self._sde_manager.get_blueprint_by_id(blueprint_id)
        if not blueprint or not self._market_manager:
            return None

        # Get manufacturing data
        activities = blueprint.activities
        if not activities or "manufacturing" not in activities:
            return None

        manufacturing = activities["manufacturing"]
        products = manufacturing.get("products", [])

        if not products:
            logger.warning(f"No products for blueprint {blueprint_id}")
            return None

        # Assume first product (most blueprints have one)
        product = products[0]
        product_type_id = product.get("type_id")
        product_quantity = product.get("quantity", 1)

        if product_type_id is None:
            return None

        # Calculate costs
        material_cost_data = self.calculate_material_costs(
            blueprint_id, region_id, "manufacturing"
        )
        if not material_cost_data:
            return None

        cost_per_run = material_cost_data["total_cost"]
        total_cost = cost_per_run * runs

        # Get product price
        product_price = self._market_manager.get_price(
            product_type_id, region_id, is_buy_order=False
        )

        if not product_price:
            return {
                "blueprint_id": blueprint_id,
                "product_type_id": product_type_id,
                "cost_per_run": cost_per_run,
                "total_cost": total_cost,
                "revenue": None,
                "profit": None,
                "profit_margin": None,
            }

        # Calculate revenue and profit
        units_produced = product_quantity * runs
        revenue_per_unit = product_price.min_val  # Conservative estimate
        total_revenue = revenue_per_unit * units_produced

        profit = total_revenue - total_cost
        profit_margin = (profit / total_cost * 100) if total_cost > 0 else 0.0

        return {
            "blueprint_id": blueprint_id,
            "product_type_id": product_type_id,
            "units_produced": units_produced,
            "cost_per_run": cost_per_run,
            "total_cost": total_cost,
            "revenue_per_unit": revenue_per_unit,
            "total_revenue": total_revenue,
            "profit": profit,
            "profit_margin": profit_margin,
            "runs": runs,
        }

    def get_material_costs(
        self, blueprint_id: int, region_id: int = 10000002
    ) -> list[dict[str, Any]]:
        """Get material list with costs for a blueprint.

        Convenience method that returns just the materials list.

        Args:
            blueprint_id: Blueprint ID
            region_id: Region ID for prices

        Returns:
            List of material dictionaries with costs

        """
        cost_data = self.calculate_material_costs(blueprint_id, region_id)
        return cost_data["materials"] if cost_data else []
