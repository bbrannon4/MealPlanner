# File: core/importers.py
from typing import List, Dict, Any
import re

# Optional URL scraping via recipe-scrapers
try:
    from recipe_scrapers import scrape_me
    _HAS_SCRAPER = True
except Exception:
    _HAS_SCRAPER = False

# Normalization for common units (lightweight; full conversion handled elsewhere)
_UNIT_ALIASES = {
    "t": "tsp", "tsp": "tsp", "teaspoon": "tsp", "teaspoons": "tsp",
    "tbsp": "tbsp", "tbs": "tbsp", "tablespoon": "tbsp", "tablespoons": "tbsp",
    "c": "cup", "cup": "cup", "cups": "cup",
    "oz": "oz", "ounce": "oz", "ounces": "oz",
    "lb": "lb", "pound": "lb", "pounds": "lb",
    "g": "g", "gram": "g", "grams": "g",
    "kg": "kg", "l": "l", "liter": "l", "liters": "l",
    "ml": "ml",
    # treat packaging/count-like words as counts
    "pinch": "count", "clove": "count", "cloves": "count", "can": "count", "cans": "count",
    "package": "count", "packages": "count", "pkg": "count", "egg": "count", "eggs": "count"
}

# patterns: number, fraction, or decimal (supports "1 1/2" or "3/4")
_FRACTION = r"(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)"
_UNIT = r"(?:[A-Za-z_\-\.]+)"  # allow hyphenated like "15-oz"

ING_PATTERN = re.compile(
    rf"^\s*(?P<qty>{_FRACTION})?\s*(?P<unit>{_UNIT})?\s*(?P<name>.*)$"
)

def _parse_qty(q: str) -> float:
    if not q:
        return 0.0
    q = q.strip()
    # handle mixed fractions like '1 1/2'
    if ' ' in q and '/' in q:
        whole, frac = q.split(' ', 1)
        num, den = frac.split('/')
        return float(whole) + (float(num) / float(den))
    if '/' in q:
        num, den = q.split('/')
        return float(num) / float(den)
    return float(q)

def parse_ingredient_line(line: str) -> Dict[str, Any]:
    """Parse a single free-text ingredient line into name/qty/unit/form.
    Robust to missing unit/qty and None values.
    """
    if line is None:
        line = ""
    line = line.strip()
    if not line:
        return {"ingredient": "", "quantity": 0.0, "unit": "count", "form": ""}

    m = ING_PATTERN.match(line)
    qty = _parse_qty(m.group('qty')) if (m and m.group('qty')) else 0.0
    unit_raw = ((m.group('unit') or '') if m else '').strip().lower()

    # Handle cases like "15-oz can" → unit becomes "oz" and qty 15
    if unit_raw.endswith("-oz"):
        try:
            qty = float(unit_raw.split('-')[0])
            unit_raw = 'oz'
        except Exception:
            pass

    unit = _UNIT_ALIASES.get(unit_raw, unit_raw or 'count')
    name = (m.group('name') if m else line).strip()

    # Split form notes with a comma (e.g., "onion, chopped")
    form = ""
    if ',' in name:
        name, form = [s.strip() for s in name.split(',', 1)]

    return {"ingredient": name, "quantity": qty, "unit": unit or 'count', "form": form}

def parse_ingredients_block(block: str) -> List[Dict[str, Any]]:
    """Parse a multi-line block of ingredients."""
    if block is None:
        return []
    lines = [l for l in block.splitlines() if (l or '').strip()]
    return [parse_ingredient_line(l) for l in lines]

def fetch_and_parse_recipe(url: str) -> Dict[str, Any]:
    """Fetch a recipe page and return structured data.
    Returns: {name, notes, lines[list of {ingredient, quantity, unit, form}]}
    """
    if not _HAS_SCRAPER:
        raise RuntimeError("recipe-scrapers not available; install it from requirements.txt")
    s = scrape_me(url)

    # Defensive reads because some scrapers return None
    name = s.title() or "Imported Recipe"
    raw_ingredients = s.ingredients() or []
    # guard against None entries from some sites
    safe_ingredients = [i for i in raw_ingredients if isinstance(i, str) and i.strip()]
    instructions = s.instructions() or ""

    lines = parse_ingredients_block("\n".join(safe_ingredients))
    return {"name": name, "notes": instructions, "lines": lines}
