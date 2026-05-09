# File: core/schema.py
from typing import Optional, List
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship

class Category(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    recipes: List["Recipe"] = Relationship(back_populates="category")

class Ingredient(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    default_aisle: str = "Dry goods"
    is_staple: bool = False
    preferred_unit: str = "count"

class Recipe(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    url: Optional[str] = None
    notes: Optional[str] = None
    category_id: Optional[int] = Field(default=None, foreign_key="category.id")
    category: Optional[Category] = Relationship(back_populates="recipes")
    lines: List["RecipeIngredient"] = Relationship(back_populates="recipe")

class RecipeIngredient(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    recipe_id: int = Field(foreign_key="recipe.id")
    ingredient_id: int = Field(foreign_key="ingredient.id")
    quantity: float = 0.0
    unit: str = "count"
    form: Optional[str] = None

    recipe: Recipe = Relationship(back_populates="lines")
    ingredient: Ingredient = Relationship()

class PantryItem(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    ingredient_id: int = Field(primary_key=True, foreign_key="ingredient.id")
    on_hand_qty: float = 0.0
    unit: str = "count"
    min_qty_to_keep: float = 0.0

class ShoppingList(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    title: str
    time_range: Optional[str] = None
    items: List["ShoppingListItem"] = Relationship(back_populates="shopping_list")

class ShoppingListItem(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    shopping_list_id: int = Field(foreign_key="shoppinglist.id")
    ingredient_id: Optional[int] = Field(default=None, foreign_key="ingredient.id")
    quantity_needed: float = 0.0
    unit: str = "count"
    source_recipes: Optional[str] = None

    shopping_list: ShoppingList = Relationship(back_populates="items")
    ingredient: Optional[Ingredient] = Relationship()

