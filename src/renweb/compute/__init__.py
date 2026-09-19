"""Renewable-energy statistics calculated from a loaded balances warehouse."""

from renweb.compute.dag import compute
from renweb.compute.formulas import METHOD_VERSION

__all__ = ["METHOD_VERSION", "compute"]
