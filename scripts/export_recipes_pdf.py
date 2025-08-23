# scripts/export_recipes_pdf.py
"""
Export all recipes from the SQLite DB into a printable PDF.
- Full-page layout (no two-up). Long recipes flow across pages.
- Each recipe starts on a new page (no blank pages).
- Ingredients are rendered in two columns (qty+desc | qty+desc).

Usage:
  source .venv/bin/activate
  python scripts/export_recipes_pdf.py --output exports/recipes.pdf
  # optional:
  #   --contains "chicken"
  #   --category "Dinner"
"""

from pathlib import Path
import argparse
from typing import List, Tuple

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# Ensure project imports no matter the CWD
import sys
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core.db import init_engine, init_db, get_session  # noqa: E402
from core.schema import Recipe, RecipeIngredient, Ingredient, Category  # noqa: E402
from sqlmodel import select  # noqa: E402

# ---------- Layout config ----------
# Tight margins, minimal vertical padding
MARGINS = (0.5 * inch, 0.5 * inch, 0.5 * inch, 0.5 * inch)  # left, right, top, bottom


def format_qty_unit(qty: float, unit: str) -> str:
    unit = (unit or "").strip().lower()
    try:
        q = float(qty or 0.0)
    except Exception:
        q = 0.0
    if q == 0:
        q_str = ""
    else:
        q_str = f"{int(q)}" if abs(q - int(q)) < 1e-6 else f"{q:g}"
    return q_str if unit in ("", "count", None) else f"{q_str} {unit}".strip()


def fetch_recipes(engine, name_contains: str = "", category_name: str = "") -> List[Tuple[Recipe, List[Tuple[Ingredient, RecipeIngredient]]]]:
    with get_session(engine) as ses:
        stmt = select(Recipe)
        if name_contains:
            like = f"%{name_contains.strip()}%"
            stmt = stmt.where(Recipe.name.ilike(like))
        if category_name:
            cat = ses.exec(select(Category).where(Category.name == category_name)).first()
            if cat:
                stmt = stmt.where(Recipe.category_id == cat.id)
            else:
                return []

        recipes = ses.exec(stmt).all()
        out = []
        for r in sorted(recipes, key=lambda x: ((x.category.name if x.category else ""), x.name or "")):
            lines = ses.exec(select(RecipeIngredient).where(RecipeIngredient.recipe_id == r.id)).all()
            pairs = []
            for ln in lines:
                ing = ses.get(Ingredient, ln.ingredient_id) if ln.ingredient_id else None
                pairs.append((ing, ln))
            out.append((r, pairs))
        return out


def build_styles():
    styles = getSampleStyleSheet()

    # Smaller, dense typography
    styles["Heading1"].fontName = "Helvetica-Bold"
    styles["Heading1"].fontSize = 14
    styles["Heading1"].spaceBefore = 0
    styles["Heading1"].spaceAfter = 2

    styles["Normal"].fontName = "Helvetica"
    styles["Normal"].fontSize = 9
    styles["Normal"].leading = 11
    styles["Normal"].spaceBefore = 0
    styles["Normal"].spaceAfter = 0

    small = ParagraphStyle(
        "Small",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        textColor=colors.grey,
        spaceBefore=0,
        spaceAfter=1,
    )
    h2 = ParagraphStyle(
        "H2",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        spaceBefore=2,
        spaceAfter=1,
    )
    return styles, small, h2


def ingredients_two_column_table(ing_pairs: List[Tuple[Ingredient, RecipeIngredient]]):
    """Build a 4-col table: qty1, desc1, qty2, desc2 (tight paddings)."""
    items = []
    for ing, ln in ing_pairs:
        name = (ing.name if ing else "(ingredient)").strip()
        form = (ln.form or "").strip()
        desc = f"{name}{', ' + form if form else ''}"
        qtyu = format_qty_unit(ln.quantity, ln.unit)
        items.append((qtyu, desc))
    if not items:
        items = [("", "(no ingredients recorded)")]

    mid = (len(items) + 1) // 2
    col1, col2 = items[:mid], items[mid:]
    if len(col2) < len(col1):
        col2 += [("", "")] * (len(col1) - len(col2))

    rows = [[q1, d1, q2, d2] for (q1, d1), (q2, d2) in zip(col1, col2)]

    # Widths sum ~7.2" to fit letter with 0.5" margins
    col_widths = [0.9 * inch, 2.7 * inch, 0.9 * inch, 2.7 * inch]

    tbl = Table(
        rows,
        colWidths=col_widths,
        style=TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 1),
                ("RIGHTPADDING", (0, 0), (-1, -1), 1),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        ),
    )
    return tbl


def recipe_flowables(r: Recipe, ing_pairs: List[Tuple[Ingredient, RecipeIngredient]], styles, small, h2):
    flows = []
    flows.append(Paragraph(r.name or "Untitled Recipe", styles["Heading1"]))

    meta_bits = []
    if r.category:
        meta_bits.append(r.category.name)
    if r.url:
        meta_bits.append(r.url)
    if meta_bits:
        flows.append(Paragraph(" • ".join(meta_bits), small))

    # Ingredients (tight)
    flows.append(Paragraph("Ingredients", h2))
    flows.append(ingredients_two_column_table(ing_pairs))

    # Instructions / Notes (tight)
    notes = (r.notes or "").strip()
    if notes:
        flows.append(Paragraph("Instructions", h2))
        for para in notes.split("\n\n"):
            p = para.strip()
            if p:
                flows.append(Paragraph(p.replace("\n", "<br/>"), styles["Normal"]))
    return flows


def export_pdf(engine, output_path: Path, name_contains: str = "", category_name: str = ""):
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Single full-page frame; long content flows across pages automatically
    PAGE_W, PAGE_H = letter
    L, R, T, B = MARGINS
    usable_w = PAGE_W - L - R
    usable_h = PAGE_H - T - B

    frame_full = Frame(L, B, usable_w, usable_h, id="full")

    doc = BaseDocTemplate(
        str(output_path),
        pagesize=letter,
        leftMargin=L,
        rightMargin=R,
        topMargin=T,
        bottomMargin=B,
    )
    doc.addPageTemplates([PageTemplate(id="full-page", frames=[frame_full])])

    styles, small, h2 = build_styles()
    recipes = fetch_recipes(engine, name_contains=name_contains, category_name=category_name)

    story = []
    for idx, (r, pairs) in enumerate(recipes):
        story.extend(recipe_flowables(r, pairs, styles, small, h2))
        if idx != len(recipes) - 1:
            story.append(PageBreak())

    if not recipes:
        story.append(Paragraph("No recipes found.", styles["Normal"]))

    doc.build(story)


def main():
    parser = argparse.ArgumentParser(description="Export recipes to a printable PDF.")
    parser.add_argument("--output", "-o", default="exports/recipes.pdf", help="Output PDF path")
    parser.add_argument("--contains", default="", help="Filter recipes whose name contains this substring (case-insensitive)")
    parser.add_argument("--category", default="", help="Filter by exact category name")
    args = parser.parse_args()

    db_path = REPO_ROOT / "data" / "mealplanner.db"
    engine = init_engine(str(db_path))
    init_db(engine)

    export_pdf(engine, Path(args.output), name_contains=args.contains, category_name=args.category)
    print(f"Wrote: {args.output}")


if __name__ == "__main__":
    main()
