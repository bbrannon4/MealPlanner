#!/usr/bin/env python3
"""
Migrate local SQLite data to a Postgres database (e.g. Supabase).

Usage:
    DATABASE_URL="postgresql://..." python scripts/migrate_to_postgres.py

The script reads from data/mealplanner.db and writes to the Postgres DB
specified by DATABASE_URL. It is idempotent — re-running it will skip
records that already exist (matched by name).
"""

import os
import sys
from pathlib import Path

# Ensure the project root is on the path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from sqlmodel import Session, create_engine, select

from core.schema import Category, Ingredient, Recipe, RecipeIngredient

SQLITE_PATH = ROOT / "data" / "mealplanner.db"
PG_URL = os.environ.get("DATABASE_URL")

if not PG_URL:
    print("ERROR: Set DATABASE_URL to your Postgres connection string.")
    print("  export DATABASE_URL='postgresql://...'")
    sys.exit(1)

if not SQLITE_PATH.exists():
    print(f"ERROR: SQLite database not found at {SQLITE_PATH}")
    sys.exit(1)

print(f"Source : {SQLITE_PATH}")
print(f"Target : {PG_URL[:40]}...")

src_engine = create_engine(f"sqlite:///{SQLITE_PATH}", echo=False)
dst_engine = create_engine(PG_URL, echo=False, pool_pre_ping=True)

# Create tables in Postgres if they don't exist
from core import schema as _schema_module  # noqa: F401 — registers models
from sqlmodel import SQLModel
SQLModel.metadata.create_all(dst_engine)

with Session(src_engine) as src, Session(dst_engine) as dst:

    # --- Categories ---
    src_cats = src.exec(select(Category)).all()
    cat_id_map: dict[int, int] = {}  # old id → new id
    for cat in src_cats:
        existing = dst.exec(select(Category).where(Category.name == cat.name)).first()
        if existing:
            cat_id_map[cat.id] = existing.id
        else:
            new_cat = Category(name=cat.name)
            dst.add(new_cat)
            dst.commit()
            dst.refresh(new_cat)
            cat_id_map[cat.id] = new_cat.id
    print(f"Categories : {len(src_cats)} processed")

    # --- Ingredients ---
    src_ings = src.exec(select(Ingredient)).all()
    ing_id_map: dict[int, int] = {}
    for ing in src_ings:
        existing = dst.exec(select(Ingredient).where(Ingredient.name == ing.name)).first()
        if existing:
            ing_id_map[ing.id] = existing.id
        else:
            new_ing = Ingredient(
                name=ing.name,
                default_aisle=ing.default_aisle,
                is_staple=ing.is_staple,
                preferred_unit=ing.preferred_unit,
            )
            dst.add(new_ing)
            dst.commit()
            dst.refresh(new_ing)
            ing_id_map[ing.id] = new_ing.id
    print(f"Ingredients: {len(src_ings)} processed")

    # --- Recipes ---
    src_recipes = src.exec(select(Recipe)).all()
    recipe_id_map: dict[int, int] = {}
    for r in src_recipes:
        existing = dst.exec(select(Recipe).where(Recipe.name == r.name)).first()
        if existing:
            recipe_id_map[r.id] = existing.id
            print(f"  skip (exists): {r.name}")
        else:
            new_cat_id = cat_id_map.get(r.category_id) if r.category_id else None
            new_r = Recipe(
                name=r.name,
                url=r.url,
                notes=r.notes,
                category_id=new_cat_id,
            )
            dst.add(new_r)
            dst.commit()
            dst.refresh(new_r)
            recipe_id_map[r.id] = new_r.id
            print(f"  migrated: {r.name}")
    print(f"Recipes    : {len(src_recipes)} processed")

    # --- Recipe ingredients ---
    src_lines = src.exec(select(RecipeIngredient)).all()
    migrated_lines = 0
    for ln in src_lines:
        new_recipe_id = recipe_id_map.get(ln.recipe_id)
        new_ing_id = ing_id_map.get(ln.ingredient_id)
        if not new_recipe_id or not new_ing_id:
            continue
        # Skip if this recipe was already in Postgres (lines came with it)
        already = dst.exec(
            select(RecipeIngredient).where(
                RecipeIngredient.recipe_id == new_recipe_id,
                RecipeIngredient.ingredient_id == new_ing_id,
            )
        ).first()
        if already:
            continue
        dst.add(RecipeIngredient(
            recipe_id=new_recipe_id,
            ingredient_id=new_ing_id,
            quantity=ln.quantity,
            unit=ln.unit,
            form=ln.form,
        ))
        migrated_lines += 1
    dst.commit()
    print(f"Ingredients in recipes: {migrated_lines} lines migrated")

print("\nDone! Your Postgres database is ready.")
