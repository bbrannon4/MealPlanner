# File: core/logic.py
from typing import List, Dict, Any, Optional
from collections import defaultdict
import json
from sqlalchemy import func
from sqlmodel import select

from .schema import (
    Ingredient,
    Recipe,
    RecipeIngredient,
    Category,
    ShoppingList,         # kept for compatibility if present elsewhere
    ShoppingListItem,     # kept for compatibility
    PantryItem,           # unused now; fine to keep in schema
)
from .units import normalize_unit_str, try_convert

# --- CRUD helpers ---

def upsert_ingredient(session, name: str, default_aisle: str, is_staple: bool, preferred_unit: str) -> Ingredient:
    name_key = name.strip()
    ing = session.exec(select(Ingredient).where(Ingredient.name == name_key)).first()
    if not ing:
        ing = Ingredient(name=name_key)
    ing.default_aisle = default_aisle
    ing.is_staple = is_staple
    ing.preferred_unit = normalize_unit_str(preferred_unit)
    session.add(ing)
    session.commit()
    session.refresh(ing)
    # Pantry rows are legacy; safe to ignore
    return ing


def _get_or_create_category(session, name: Optional[str]) -> Optional[Category]:
    if not name:
        return None
    c = session.exec(select(Category).where(Category.name == name)).first()
    if not c:
        c = Category(name=name)
        session.add(c)
        session.commit()
        session.refresh(c)
    return c


def upsert_recipe_with_lines(session, name: str, url: str, notes: str, category_name: Optional[str], lines: List[Dict[str, Any]]) -> Recipe:
    r = session.exec(select(Recipe).where(Recipe.name == name.strip())).first()
    if not r:
        r = Recipe(name=name.strip())
    r.url = url or None
    r.notes = notes or None
    r.category = _get_or_create_category(session, category_name)
    session.add(r)
    session.commit()
    session.refresh(r)

    # Clear existing lines
    existing = session.exec(select(RecipeIngredient).where(RecipeIngredient.recipe_id == r.id)).all()
    for e in existing:
        session.delete(e)
    session.commit()

    # Insert new lines; auto-create ingredients if missing
    for line in lines:
        ing_name = (line.get("ingredient") or "").strip()
        if not ing_name:
            continue
        ing = session.exec(select(Ingredient).where(Ingredient.name == ing_name)).first()
        if not ing:
            ing = Ingredient(name=ing_name)
            session.add(ing)
            session.commit()
            session.refresh(ing)
        qty = float(line.get("quantity") or 0.0)
        unit = normalize_unit_str(line.get("unit") or ing.preferred_unit or "count")
        form = (line.get("form") or None)
        session.add(RecipeIngredient(recipe_id=r.id, ingredient_id=ing.id, quantity=qty, unit=unit, form=form))
    session.commit()
    return r


def list_recipes(session, search: Optional[str] = None) -> List[Recipe]:
    stmt = select(Recipe)
    if search and search.strip():
        s = f"%{search.strip()}%"
        stmt = stmt.where(Recipe.name.like(s))
    return session.exec(stmt).all()


def list_ingredients(session) -> List[Ingredient]:
    return session.exec(select(Ingredient)).all()

# --- Ingredient maintenance helpers ---

def ingredient_usage_counts(session) -> Dict[int, int]:
    """Return {ingredient_id: count_of_recipe_lines_using_it}."""
    rows = session.exec(
        select(RecipeIngredient.ingredient_id, func.count(RecipeIngredient.id))
        .group_by(RecipeIngredient.ingredient_id)
    ).all()
    counts = {ing_id: int(cnt) for ing_id, cnt in rows if ing_id is not None}
    return counts


def rename_or_merge_ingredient(session, ingredient_id: int, new_name: str) -> bool:
    """Rename an ingredient. If another ingredient already has new_name, merge by
    re-pointing lines to that ingredient and deleting the old one."""
    new_name = (new_name or "").strip()
    if not new_name:
        return False
    src = session.get(Ingredient, ingredient_id)
    if not src:
        return False
    if src.name == new_name:
        return True

    tgt = session.exec(select(Ingredient).where(Ingredient.name == new_name)).first()
    if tgt and tgt.id != src.id:
        # Merge: repoint lines, then delete src
        lines = session.exec(select(RecipeIngredient).where(RecipeIngredient.ingredient_id == src.id)).all()
        for ln in lines:
            ln.ingredient_id = tgt.id
            session.add(ln)
        session.delete(src)
        session.commit()
        return True
    else:
        # Simple rename
        src.name = new_name
        session.add(src)
        session.commit()
        return True


def delete_unused_ingredients(session) -> int:
    """Delete ingredients that are not referenced by any recipe line."""
    used_ids = {iid for (iid,) in session.exec(select(RecipeIngredient.ingredient_id)).all() if iid is not None}
    all_ings = session.exec(select(Ingredient)).all()
    deleted = 0
    for ing in all_ings:
        if ing.id not in used_ids:
            session.delete(ing)
            deleted += 1
    session.commit()
    return deleted

# --- Planning / consolidation ---

def consolidate_for_shopping(session, recipe_ids: List[int]) -> Dict[str, Any]:
    lines = session.exec(select(RecipeIngredient).where(RecipeIngredient.recipe_id.in_(recipe_ids))).all()
    ing_map = {i.id: i for i in session.exec(select(Ingredient)).all()}
    # accumulate per ingredient in preferred unit where possible
    total: Dict[int, Dict[str, Any]] = defaultdict(lambda: {"qty": 0.0, "unit": None, "sources": set()})
    warnings = []

    for line in lines:
        ing = ing_map.get(line.ingredient_id)
        if not ing:
            continue
        target_unit = ing.preferred_unit or line.unit
        ok, converted_qty = try_convert(line.quantity, line.unit, target_unit)
        qty = converted_qty if ok else line.quantity
        u = target_unit if ok else line.unit
        if not ok and line.unit != target_unit:
            warnings.append(f"Could not convert {ing.name} from {line.unit} to {target_unit}; kept {line.unit}.")
        rec = total[line.ingredient_id]
        if rec["unit"] is None:
            rec["unit"] = u
        if rec["unit"] == u:
            rec["qty"] += qty
        else:
            warnings.append(f"Conflicting units for {ing.name}: {rec['unit']} vs {u}.")
            rec["qty"] += qty
        rec["sources"].add(line.recipe.name if line.recipe else "recipe")

    # Build preview rows (sources as list)
    rows = []
    for ing_id, rec in total.items():
        ing = ing_map.get(ing_id)
        rows.append({
            "aisle": ing.default_aisle if ing else "",
            "ingredient": ing.name if ing else str(ing_id),
            "qty": rec["qty"],
            "unit": rec["unit"],
            "staple": ing.is_staple if ing else False,
            "sources": sorted(rec["sources"]),
        })

    rows.sort(key=lambda r: (r["staple"], r["aisle"], r["ingredient"]))
    return {"preview_rows": rows, "warnings": warnings}
