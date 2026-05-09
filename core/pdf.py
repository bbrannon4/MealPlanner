# File: core/pdf.py
import io
from typing import List, Tuple

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    PageBreak,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from sqlmodel import Session, select

from .schema import Ingredient, Recipe, RecipeIngredient

MARGINS = (0.5 * inch, 0.5 * inch, 0.5 * inch, 0.5 * inch)


def _format_qty_unit(qty: float, unit: str) -> str:
    unit = (unit or "").strip().lower()
    try:
        q = float(qty or 0.0)
    except Exception:
        q = 0.0
    if q == 0:
        q_str = ""
    else:
        q_str = f"{int(q)}" if abs(q - int(q)) < 1e-6 else f"{q:g}"
    return q_str if unit in ("", "count") else f"{q_str} {unit}".strip()


def _build_styles():
    styles = getSampleStyleSheet()
    styles["Heading1"].fontName = "Helvetica-Bold"
    styles["Heading1"].fontSize = 14
    styles["Heading1"].spaceBefore = 0
    styles["Heading1"].spaceAfter = 2
    styles["Normal"].fontName = "Helvetica"
    styles["Normal"].fontSize = 9
    styles["Normal"].leading = 11
    small = ParagraphStyle(
        "Small", parent=styles["Normal"],
        fontSize=8, leading=10, textColor=colors.grey,
    )
    h2 = ParagraphStyle(
        "H2", parent=styles["Normal"],
        fontName="Helvetica-Bold", fontSize=11, spaceBefore=2, spaceAfter=1,
    )
    return styles, small, h2


def _ingredients_table(ing_pairs: List[Tuple[Ingredient, RecipeIngredient]]):
    items = []
    for ing, ln in ing_pairs:
        name = (ing.name if ing else "(ingredient)").strip()
        form = (ln.form or "").strip()
        desc = f"{name}{', ' + form if form else ''}"
        items.append((_format_qty_unit(ln.quantity, ln.unit), desc))
    if not items:
        items = [("", "(no ingredients recorded)")]

    mid = (len(items) + 1) // 2
    col1, col2 = items[:mid], items[mid:]
    col2 += [("", "")] * (len(col1) - len(col2))
    rows = [[q1, d1, q2, d2] for (q1, d1), (q2, d2) in zip(col1, col2)]

    return Table(
        rows,
        colWidths=[0.9 * inch, 2.7 * inch, 0.9 * inch, 2.7 * inch],
        style=TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 1),
            ("RIGHTPADDING", (0, 0), (-1, -1), 1),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]),
    )


def _recipe_flowables(r: Recipe, ing_pairs, styles, small, h2):
    flows = [Paragraph(r.name or "Untitled Recipe", styles["Heading1"])]
    meta = []
    if r.category:
        meta.append(r.category.name)
    if r.url:
        meta.append(r.url)
    if meta:
        flows.append(Paragraph(" • ".join(meta), small))
    flows.append(Paragraph("Ingredients", h2))
    flows.append(_ingredients_table(ing_pairs))
    notes = (r.notes or "").strip()
    if notes:
        flows.append(Paragraph("Instructions", h2))
        for para in notes.split("\n\n"):
            p = para.strip()
            if p:
                flows.append(Paragraph(p.replace("\n", "<br/>"), styles["Normal"]))
    return flows


def recipe_pdf_bytes(session: Session, recipe_id: int) -> bytes:
    """Return PDF bytes for a single recipe."""
    r = session.get(Recipe, recipe_id)
    if not r:
        raise ValueError(f"Recipe {recipe_id} not found")

    lines = session.exec(select(RecipeIngredient).where(RecipeIngredient.recipe_id == recipe_id)).all()
    ing_pairs = [(session.get(Ingredient, ln.ingredient_id), ln) for ln in lines]

    PAGE_W, PAGE_H = letter
    L, R, T, B = MARGINS
    buf = io.BytesIO()
    doc = BaseDocTemplate(
        buf, pagesize=letter,
        leftMargin=L, rightMargin=R, topMargin=T, bottomMargin=B,
    )
    doc.addPageTemplates([PageTemplate(
        id="full", frames=[Frame(L, B, PAGE_W - L - R, PAGE_H - T - B, id="full")]
    )])

    styles, small, h2 = _build_styles()
    doc.build(_recipe_flowables(r, ing_pairs, styles, small, h2))
    return buf.getvalue()
