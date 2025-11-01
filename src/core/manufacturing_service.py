"""Manufacturing service for EVE Online industry calculations.

This service provides comprehensive manufacturing calculations including:
- Material requirements with ME bonuses
- Manufacturing time with TE and skill bonuses
- Structure bonuses (material, time, cost)
- System Cost Index (SCI) calculations
- Total job costs including taxes and fees
"""

import logging
from typing import Any, TypedDict

from data.managers import MarketDataManager, SDEManager

logger = logging.getLogger(__name__)


class MaterialBreakdown(TypedDict):
    """Material breakdown for a single material."""

    type_id: int
    type_name: str
    base_quantity: int
    me_adjusted_quantity: int
    structure_adjusted_quantity: int
    final_quantity: int
    unit_price: float
    total_cost: float


class ManufacturingCostBreakdown(TypedDict):
    """Complete manufacturing cost breakdown."""

    blueprint_id: int
    product_type_id: int
    product_quantity: int
    runs: int
    me_level: int
    te_level: int

    # Material costs
    materials: list[MaterialBreakdown]
    total_material_cost: float

    # Time calculations
    base_time_per_run: int  # seconds
    skill_adjusted_time: int  # seconds
    te_adjusted_time: int  # seconds
    structure_time_bonus: float
    final_time_per_run: int  # seconds
    total_manufacturing_time: int  # seconds

    # Job costs
    estimated_item_value: float
    system_cost_index: float
    structure_material_bonus: float
    structure_time_bonus_percent: float
    structure_cost_bonus: float
    facility_tax: float
    scc_surcharge: float
    alpha_clone_tax: float
    job_installation_cost: float
    total_job_cost: float

    # Final totals
    total_cost: float  # Materials + job cost
    cost_per_unit: float


class ManufacturingService:
    """Service for manufacturing calculations and analysis."""

    # Default values (can be overridden)
    DEFAULT_FACILITY_TAX = 0.0025  # 0.25% for NPC stations
    DEFAULT_SCC_SURCHARGE = 0.04  # 4%
    DEFAULT_ALPHA_TAX = 0.0  # 0.25% only for alpha clones

    # Skill bonuses (hardcoded - user can modify)
    DEFAULT_INDUSTRY_LEVEL = 5  # Industry skill (4% time reduction/lvl)
    DEFAULT_ADVANCED_INDUSTRY_LEVEL = 5  # Advanced Industry (3% time/lvl)

    # Structure bonuses (hardcoded - user can modify)
    DEFAULT_STRUCTURE_MATERIAL_BONUS = 0.01  # 1% material (Eng Complex)
    DEFAULT_STRUCTURE_TIME_BONUS = 0.15  # 15% time reduction (Medium EC)
    DEFAULT_STRUCTURE_COST_BONUS = 0.0  # Structure can have cost reduction rigs

    def __init__(
        self,
        sde_manager: SDEManager,
        market_manager: MarketDataManager | None = None,
    ):
        """Initialize the manufacturing service.

        Args:
            sde_manager: SDEManager for blueprint and type data
            market_manager: Optional MarketDataManager for price data

        """
        self._sde_manager = sde_manager
        self._market_manager = market_manager

    def calculate_manufacturing_cost(
        self,
        blueprint_id: int,
        runs: int = 1,
        me_level: int = 10,
        te_level: int = 20,
        region_id: int = 10000002,
        system_cost_index: float = 0.02,
        structure_material_bonus: float | None = None,
        structure_time_bonus: float | None = None,
        structure_cost_bonus: float | None = None,
        facility_tax: float | None = None,
        is_alpha_clone: bool = False,
        industry_skill: int | None = None,
        advanced_industry_skill: int | None = None,
    ) -> ManufacturingCostBreakdown | None:
        """Calculate complete manufacturing cost breakdown.

        Args:
            blueprint_id: Blueprint ID
            runs: Number of production runs
            me_level: Material Efficiency level (0-10)
            te_level: Time Efficiency level (0-20, represents 0%-20% reduction)
            region_id: Region for material prices
            system_cost_index: System cost index (0.0 to ~1.0)
            structure_material_bonus: Structure material bonus (e.g., 0.01 = 1%)
            structure_time_bonus: Structure time bonus (e.g., 0.15 = 15%)
            structure_cost_bonus: Structure cost bonus (e.g., 0.02 = 2%)
            facility_tax: Facility tax (default 0.25% for NPC)
            is_alpha_clone: Whether using alpha clone (adds 0.25% tax)
            industry_skill: Industry skill level (0-5)
            advanced_industry_skill: Advanced Industry skill level (0-5)

        Returns:
            ManufacturingCostBreakdown or None if blueprint not found

        """
        # Get blueprint
        blueprint = self._sde_manager.get_blueprint_by_id(blueprint_id)
        if not blueprint or not blueprint.activities.manufacturing:
            logger.warning(f"Blueprint {blueprint_id} not found or no manufacturing")
            return None

        manufacturing = blueprint.activities.manufacturing

        # Get product info
        if not manufacturing.products or len(manufacturing.products) == 0:
            logger.warning(f"No products for blueprint {blueprint_id}")
            return None

        product = manufacturing.products[0]
        product_type_id = product.type_id
        product_quantity = product.quantity

        # Apply defaults
        if structure_material_bonus is None:
            structure_material_bonus = self.DEFAULT_STRUCTURE_MATERIAL_BONUS
        if structure_time_bonus is None:
            structure_time_bonus = self.DEFAULT_STRUCTURE_TIME_BONUS
        if structure_cost_bonus is None:
            structure_cost_bonus = self.DEFAULT_STRUCTURE_COST_BONUS
        if facility_tax is None:
            facility_tax = self.DEFAULT_FACILITY_TAX
        if industry_skill is None:
            industry_skill = self.DEFAULT_INDUSTRY_LEVEL
        if advanced_industry_skill is None:
            advanced_industry_skill = self.DEFAULT_ADVANCED_INDUSTRY_LEVEL

        # Calculate material requirements
        materials_breakdown: list[MaterialBreakdown] = []
        total_material_cost = 0.0
        estimated_item_value = 0.0  # For job cost calculation

        if manufacturing.materials:
            for material in manufacturing.materials:
                type_id = material.type_id
                base_quantity = material.quantity

                # Get type name
                eve_type = self._sde_manager.get_type_by_id(type_id)
                type_name = eve_type.name.en if eve_type else f"Type {type_id}"

                # Calculate adjusted quantities
                # ME bonus: -1% per level (max -10%)
                me_multiplier = 1.0 - (me_level * 0.01)
                me_adjusted = base_quantity * me_multiplier

                # Structure material bonus
                structure_multiplier = 1.0 - structure_material_bonus
                structure_adjusted = me_adjusted * structure_multiplier

                # Apply runs and round up (per job, not per run)
                total_adjusted = structure_adjusted * runs
                # Round up, min 1 per run
                final_quantity = max(runs, int(total_adjusted + 0.9999))

                # Get price
                unit_price = 0.0
                if self._market_manager:
                    price_data = self._market_manager.get_price(
                        type_id, region_id, is_buy_order=False
                    )
                    if price_data:
                        unit_price = price_data.min_val

                total_cost = unit_price * final_quantity
                total_material_cost += total_cost

                # For EIV, use adjusted price
                # (would need ESI, using market price as approximation)
                estimated_item_value += base_quantity * runs * unit_price

                materials_breakdown.append(
                    MaterialBreakdown(
                        type_id=type_id,
                        type_name=type_name,
                        base_quantity=base_quantity,
                        me_adjusted_quantity=int(me_adjusted * runs + 0.9999),
                        structure_adjusted_quantity=int(
                            structure_adjusted * runs + 0.9999
                        ),
                        final_quantity=final_quantity,
                        unit_price=unit_price,
                        total_cost=total_cost,
                    )
                )

        # Calculate manufacturing time
        base_time_per_run = manufacturing.time if manufacturing.time else 0

        # Skill time reduction
        # Industry: 4% per level
        # Advanced Industry: 3% per level
        skill_time_multiplier = 1.0
        skill_time_multiplier *= 1.0 - (industry_skill * 0.04)
        skill_time_multiplier *= 1.0 - (advanced_industry_skill * 0.03)
        skill_adjusted_time = int(base_time_per_run * skill_time_multiplier)

        # TE reduction: -2% per level (max -20%)
        te_multiplier = 1.0 - (te_level * 0.01)  # te_level is 0-20, representing 0-20%
        te_adjusted_time = int(skill_adjusted_time * te_multiplier)

        # Structure time bonus
        structure_time_multiplier = 1.0 - structure_time_bonus
        final_time_per_run = int(te_adjusted_time * structure_time_multiplier)
        total_manufacturing_time = final_time_per_run * runs

        # Calculate job installation cost
        # Formula: EIV * ((SCI * Structure bonuses) + taxes)

        structure_bonus_multiplier = 1.0 - structure_cost_bonus
        sci_component = system_cost_index * structure_bonus_multiplier

        alpha_tax = self.DEFAULT_ALPHA_TAX if is_alpha_clone else 0.0
        scc_surcharge = self.DEFAULT_SCC_SURCHARGE

        total_tax_rate = sci_component + facility_tax + scc_surcharge + alpha_tax
        job_installation_cost = estimated_item_value * total_tax_rate

        # Total cost
        total_job_cost = job_installation_cost
        total_cost = total_material_cost + total_job_cost
        total_units = product_quantity * runs
        cost_per_unit = total_cost / total_units if total_units > 0 else 0.0

        return ManufacturingCostBreakdown(
            blueprint_id=blueprint_id,
            product_type_id=product_type_id,
            product_quantity=product_quantity,
            runs=runs,
            me_level=me_level,
            te_level=te_level,
            materials=materials_breakdown,
            total_material_cost=total_material_cost,
            base_time_per_run=base_time_per_run,
            skill_adjusted_time=skill_adjusted_time,
            te_adjusted_time=te_adjusted_time,
            structure_time_bonus=structure_time_bonus,
            final_time_per_run=final_time_per_run,
            total_manufacturing_time=total_manufacturing_time,
            estimated_item_value=estimated_item_value,
            system_cost_index=system_cost_index,
            structure_material_bonus=structure_material_bonus,
            structure_time_bonus_percent=structure_time_bonus * 100,
            structure_cost_bonus=structure_cost_bonus,
            facility_tax=facility_tax,
            scc_surcharge=scc_surcharge,
            alpha_clone_tax=alpha_tax,
            job_installation_cost=job_installation_cost,
            total_job_cost=total_job_cost,
            total_cost=total_cost,
            cost_per_unit=cost_per_unit,
        )

    def calculate_profit_with_manufacturing(
        self,
        blueprint_id: int,
        runs: int = 1,
        me_level: int = 10,
        te_level: int = 20,
        region_id: int = 10000002,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        """Calculate manufacturing profit.

        Args:
            blueprint_id: Blueprint ID
            runs: Number of runs
            me_level: Material Efficiency level
            te_level: Time Efficiency level
            region_id: Region for prices
            **kwargs: Additional parameters for calculate_manufacturing_cost

        Returns:
            Dictionary with profit analysis or None

        """
        cost_breakdown = self.calculate_manufacturing_cost(
            blueprint_id=blueprint_id,
            runs=runs,
            me_level=me_level,
            te_level=te_level,
            region_id=region_id,
            **kwargs,
        )

        if not cost_breakdown or not self._market_manager:
            return None

        # Get product sell price
        product_type_id = cost_breakdown["product_type_id"]
        product_price = self._market_manager.get_price(
            product_type_id, region_id, is_buy_order=True
        )

        if not product_price:
            return {
                "cost_breakdown": cost_breakdown,
                "sell_price": None,
                "total_revenue": None,
                "profit": None,
                "profit_margin": None,
            }

        # Calculate revenue and profit
        units_produced = cost_breakdown["product_quantity"] * runs
        sell_price_per_unit = product_price.max_val  # Best buy order
        total_revenue = sell_price_per_unit * units_produced

        profit = total_revenue - cost_breakdown["total_cost"]
        profit_margin = (
            (profit / cost_breakdown["total_cost"] * 100)
            if cost_breakdown["total_cost"] > 0
            else 0.0
        )

        return {
            "cost_breakdown": cost_breakdown,
            "sell_price_per_unit": sell_price_per_unit,
            "units_produced": units_produced,
            "total_revenue": total_revenue,
            "profit": profit,
            "profit_margin": profit_margin,
        }
