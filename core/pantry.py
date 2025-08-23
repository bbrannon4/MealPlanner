# File: core/pantry.py
from typing import List, Dict
from sqlmodel import select
from .schema import PantryItem, Ingredient
from .units import try_convert, normalize_unit_str


def get_pantry_status(session) -> List[Dict]:
    rows = (
        session.exec(select(PantryItem, Ingredient).where(PantryItem.ingredient_id == Ingredient.id)).all()
    )
    out = []
    for p, ing in rows:
        out.append({
            "ingredient": ing.name,
            "on_hand_qty": p.on_hand_qty,
            "unit": p.unit,
            "min_qty_to_keep": p.min_qty_to_keep,
            "is_staple": ing.is_staple,
        })
    return out


def adjust_pantry_levels(session, ingredient_name: str, delta_qty: float, unit: str) -> bool:
    ing = session.exec(select(Ingredient).where(Ingredient.name == ingredient_name)).first()
    if not ing:
        return False
    p = session.get(PantryItem, ing.id)
    if not p:
        p = PantryItem(ingredient_id=ing.id, on_hand_qty=0.0, unit=normalize_unit_str(unit), min_qty_to_keep=0.0)
    ok, converted = try_convert(delta_qty, unit, p.unit)
    if not ok and normalize_unit_str(unit) != normalize_unit_str(p.unit):
        return False
    p.on_hand_qty += converted if ok else delta_qty
    session.add(p)
    session.commit()
    return True
