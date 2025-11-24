"""Utility functions and classes for EVE Means of Profit."""

from .config import global_config
from .jsonl_parser import JSONLParser

__all__ = ["JSONLParser", "global_config"]
