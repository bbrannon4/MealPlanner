# File: core/units.py
from typing import Optional, Tuple
from pint import UnitRegistry

_ureg = UnitRegistry(autoconvert_offset_to_baseunit=True)
Q_ = _ureg.Quantity

# Simple helpers for three canonical families: mass (g), volume (ml), count (ea)
CANONICAL = {"mass": "gram", "volume": "milliliter", "count": "count"}

# Map common unit strings to families; extend as needed
_UNIT_FAMILY = {
    "g": "mass", "gram": "mass", "kg": "mass", "oz": "mass", "lb": "mass",
    "ml": "volume", "l": "volume", "tsp": "volume", "tbsp": "volume", "cup": "volume", "fl_oz": "volume",
    "count": "count", "each": "count", "ea": "count",
}

# Aliases
_ALIASES = {"ea": "count", "pcs": "count", "piece": "count", "pieces": "count", "teaspoon": "tsp", "tablespoon": "tbsp", "ounce": "oz"}


def normalize_unit_str(u: str) -> str:
    u = (u or "").strip().lower()
    return _ALIASES.get(u, u)


def unit_family(u: str) -> Optional[str]:
    u = normalize_unit_str(u)
    return _UNIT_FAMILY.get(u)


def try_convert(qty: float, from_unit: str, to_unit: str) -> Tuple[bool, float]:
    f, t = normalize_unit_str(from_unit), normalize_unit_str(to_unit)
    if f == t:
        return True, qty
    fam_f, fam_t = unit_family(f), unit_family(t)
    if fam_f is None or fam_t is None or fam_f != fam_t:
        return False, qty
    if fam_f == "count":
        # counts don't convert
        return False, qty
    try:
        v = Q_(qty, f).to(t).magnitude
        return True, float(v)
    except Exception:
        return False, qty

