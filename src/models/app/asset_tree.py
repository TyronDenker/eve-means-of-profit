"""Asset tree node model for hierarchical asset organization."""

from __future__ import annotations

from typing import Literal


class AssetTreeNode:
    """Represents a node in the asset tree hierarchy.

    Nodes can represent regions, constellations, systems, stations,
    or structures, forming a hierarchical tree of asset locations.
    """

    def __init__(
        self,
        location_id: int,
        location_name: str,
        location_type: Literal[
            "region", "constellation", "solar_system", "station", "structure"
        ],
        parent_id: int | None = None,
        item_count: int = 0,
        total_value: float = 0.0,
    ):
        """Initialize an asset tree node.

        Args:
            location_id: ID of the location
            location_name: Display name of the location
            location_type: Type of location (region, constellation, etc.)
            parent_id: ID of parent location (if any)
            item_count: Number of items at this location
            total_value: Total ISK value of items
        """
        self.location_id = location_id
        self.location_name = location_name
        self.location_type = location_type
        self.parent_id = parent_id
        self.item_count = item_count
        self.total_value = total_value
        self.children: list[AssetTreeNode] = []

    def add_child(self, child: AssetTreeNode) -> None:
        """Add a child node to this node.

        Args:
            child: Child node to add
        """
        if child not in self.children:
            self.children.append(child)

    def get_total_value(self) -> float:
        """Get total value including all children.

        Returns:
            Total ISK value of this node and all descendants
        """
        total = self.total_value
        for child in self.children:
            total += child.get_total_value()
        return total

    def get_item_count(self) -> int:
        """Get total item count including all children.

        Returns:
            Total number of items at this node and all descendants
        """
        count = self.item_count
        for child in self.children:
            count += child.get_item_count()
        return count

    def __repr__(self) -> str:
        return (
            f"AssetTreeNode(id={self.location_id}, "
            f"name='{self.location_name}', "
            f"type={self.location_type}, "
            f"items={self.item_count}, "
            f"value={self.total_value:.2f}, "
            f"children={len(self.children)})"
        )
