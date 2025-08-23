# File: app.py
from pathlib import Path
import pandas as pd
import streamlit as st
from sqlmodel import select

from core.db import init_engine, init_db, get_session
from core.schema import Recipe, Ingredient, RecipeIngredient, Category
from core.logic import (
    upsert_ingredient,
    upsert_recipe_with_lines,
    list_recipes,
    list_ingredients,
    consolidate_for_shopping,
    ingredient_usage_counts,
    rename_or_merge_ingredient,
    delete_unused_ingredients,
)
from core.importers import fetch_and_parse_recipe

APP_TITLE = "Meal Planner"

# Anchor DB to this file's directory
BASE_DIR = Path(__file__).parent.resolve()
DB_PATH = BASE_DIR / "data" / "mealplanner.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = init_engine(str(DB_PATH))
init_db(engine)

st.set_page_config(page_title=APP_TITLE, layout="wide")
st.title(APP_TITLE)

# Sidebar: DB path + counts
with st.sidebar:
    st.caption("Storage")
    st.code(str(DB_PATH), language="text")
    with get_session(engine) as ses:
        recipe_count = len(ses.exec(select(Recipe)).all())
        ingredient_count = len(ses.exec(select(Ingredient)).all())
    st.caption(f"Recipes: {recipe_count}  •  Ingredients: {ingredient_count}")

PAGES = ["Recipe Library", "Meal Plan", "Ingredients"]
page = st.sidebar.radio("Navigate", PAGES)

# -------------------------
# Helpers
# -------------------------
def _df_or_blank(rows):
    df = pd.DataFrame(rows or [])
    if df.empty:
        df = pd.DataFrame([{"ingredient": "", "quantity": 0.0, "unit": "count", "form": ""}])
    for c in ["ingredient", "quantity", "unit", "form"]:
        if c not in df.columns:
            df[c] = "" if c in ("ingredient", "unit", "form") else 0.0
    return df[["ingredient", "quantity", "unit", "form"]]

def _clean_lines_for_save(rows):
    out = []
    for r in rows:
        name = (str(r.get("ingredient") or "")).strip()
        if not name:
            continue
        qty_raw = r.get("quantity")
        try:
            qty = float(qty_raw) if qty_raw is not None and str(qty_raw) != "nan" else 0.0
        except Exception:
            qty = 0.0
        unit = (str(r.get("unit") or "count")).strip() or "count"
        form = (str(r.get("form") or "")).strip()
        out.append({"ingredient": name, "quantity": qty, "unit": unit, "form": form})
    return out

def _load_recipe_for_edit(session, recipe_id: int):
    r = session.get(Recipe, recipe_id)
    if not r:
        return None, None, None, None, _df_or_blank([])
    cat_name = r.category.name if r.category else "(none)"
    lines = session.exec(select(RecipeIngredient).where(RecipeIngredient.recipe_id == recipe_id)).all()
    rows = []
    for ln in lines:
        ing = session.get(Ingredient, ln.ingredient_id)
        rows.append({
            "ingredient": ing.name if ing else "",
            "quantity": ln.quantity,
            "unit": ln.unit,
            "form": ln.form or "",
        })
    df = _df_or_blank(rows)
    return r.name or "", r.url or "", r.notes or "", cat_name, df

def _save_edit(session, recipe_id: int, name: str, url: str, notes: str, category_name: str, lines_rows):
    r = session.get(Recipe, recipe_id)
    if not r:
        return False
    # category
    if category_name and category_name != "(none)":
        cat = session.exec(select(Category).where(Category.name == category_name)).first()
        if not cat:
            cat = Category(name=category_name)
            session.add(cat)
            session.commit()
            session.refresh(cat)
        r.category_id = cat.id
    else:
        r.category_id = None
    r.name = (name or "Untitled Recipe").strip()
    r.url = url or None
    r.notes = notes or None
    session.add(r)
    session.commit()
    # clear and re-add lines
    existing = session.exec(select(RecipeIngredient).where(RecipeIngredient.recipe_id == recipe_id)).all()
    for e in existing:
        session.delete(e)
    session.commit()
    for row in _clean_lines_for_save(lines_rows):
        ing = session.exec(select(Ingredient).where(Ingredient.name == row["ingredient"])).first()
        if not ing:
            ing = Ingredient(name=row["ingredient"])
            session.add(ing)
            session.commit()
            session.refresh(ing)
        session.add(RecipeIngredient(
            recipe_id=recipe_id,
            ingredient_id=ing.id,
            quantity=float(row["quantity"] or 0.0),
            unit=row["unit"] or (ing.preferred_unit or "count"),
            form=(row["form"] or None),
        ))
    session.commit()
    return True

def _auto_df_height(nrows: int, row_px: int = 34, base_px: int = 68, max_px: int = 900) -> int:
    """
    Compute a dataframe height that fits its rows, up to a max.
    - base_px ~ header + padding
    - row_px ~ per-row height
    """
    try:
        n = int(nrows or 0)
    except Exception:
        n = 0
    return min(max_px, base_px + row_px * max(3, n))

# -------------------------
# Recipe Library
# -------------------------
if page == "Recipe Library":
    st.header("Recipe Library")

    # State for importer + editing
    if "import_data" not in st.session_state:
        st.session_state["import_data"] = None
    if "import_url_final" not in st.session_state:
        st.session_state["import_url_final"] = None
    if "editing_recipe_id" not in st.session_state:
        st.session_state["editing_recipe_id"] = None

    # Two prominent ways to add recipes
    st.subheader("Add a recipe")
    tab_url, tab_manual = st.tabs(["➕ From URL", "✍️ Manually"])

    # From URL (primary)
    with tab_url:
        u = st.text_input("Recipe URL", key="import_url")
        if st.button("Fetch", key="fetch_url") and u.strip():
            try:
                st.session_state["import_data"] = fetch_and_parse_recipe(u.strip())
                st.session_state["import_url_final"] = u.strip()
                st.success(f"Fetched: {st.session_state['import_data']['name']}")
            except Exception as e:
                st.error(f"Import failed: {e}")

        if st.session_state["import_data"]:
            data = st.session_state["import_data"]
            st.text_area("Instructions (edit if you like)", value=data.get("notes") or "", key="imp_notes")
            imp_df = _df_or_blank(data.get("lines") or [])
            edited = st.data_editor(imp_df, num_rows="dynamic", use_container_width=True, key="imp_table")
            with get_session(engine) as ses:
                cat_options = [c.name for c in ses.exec(select(Category)).all()]
            colA, colB = st.columns(2)
            with colA:
                new_name = st.text_input("Save as recipe name", value=data.get("name") or "Imported Recipe", key="imp_name")
            with colB:
                new_cat = st.selectbox("Category (optional)", ["(none)"] + cat_options, index=0, key="imp_cat")
            save_col1, save_col2 = st.columns([1,1])
            with save_col1:
                if st.button("Save Imported Recipe", key="save_import"):
                    lines = _clean_lines_for_save(edited.to_dict(orient="records"))
                    with get_session(engine) as ses:
                        upsert_recipe_with_lines(
                            ses,
                            name=new_name or "Imported Recipe",
                            url=st.session_state.get("import_url_final", None),
                            notes=st.session_state.get("imp_notes", ""),
                            category_name=None if new_cat == "(none)" else new_cat,
                            lines=lines,
                        )
                        st.success(f"Saved imported recipe: {new_name or 'Imported Recipe'}")
                    st.session_state["import_data"] = None
                    st.session_state["import_url_final"] = None
                    st.rerun()
            with save_col2:
                if st.button("Cancel import"):
                    st.session_state["import_data"] = None
                    st.session_state["import_url_final"] = None
                    st.rerun()

    # Manual add
    with tab_manual:
        with get_session(engine) as ses:
            categories = ses.exec(select(Category)).all()
            cat_options = [c.name for c in categories]
        with st.form("manual_form"):
            r_name = st.text_input("Recipe name")
            url = st.text_input("URL (optional)")
            notes = st.text_area("Notes / Instructions (optional)")
            category = st.selectbox("Category", ["(none)"] + cat_options)
            edit_df = st.data_editor(
                _df_or_blank(
                    [
                        {"ingredient": "", "quantity": 0.0, "unit": "count", "form": ""},
                        {"ingredient": "", "quantity": 0.0, "unit": "count", "form": ""},
                    ]
                ),
                num_rows="dynamic",
                use_container_width=True,
                key="manual_lines_new",
            )
            submitted = st.form_submit_button("Add Recipe")
        if submitted:
            lines = _clean_lines_for_save(edit_df.to_dict(orient="records"))
            with get_session(engine) as ses:
                upsert_recipe_with_lines(
                    ses,
                    name=r_name or "Untitled Recipe",
                    url=url,
                    notes=notes,
                    category_name=None if category == "(none)" else category,
                    lines=lines,
                )
                st.success(f"Saved recipe: {r_name or 'Untitled Recipe'}")
            st.rerun()

    # All Recipes + Edit/Delete
    st.subheader("All Recipes")
    search = st.text_input("Search by name or text")
    with get_session(engine) as ses:
        recipes = list_recipes(ses, search)
        data = []
        for r in recipes:
            data.append({
                "id": r.id,
                "name": r.name,
                "category": r.category.name if r.category else "",
                "url": r.url or "",
                "notes": (r.notes or "")[:120],
            })
        df_recipes = pd.DataFrame(data)
        st.dataframe(df_recipes, use_container_width=True)

        if recipes:
            sel = st.selectbox("Select a recipe", [f"{r.id}: {r.name}" for r in recipes], key="select_recipe_row")
            rid = int(sel.split(":")[0])
            colE, colD = st.columns([1,1])
            with colE:
                if st.button("Edit selected"):
                    st.session_state["editing_recipe_id"] = rid
                    st.rerun()
            with colD:
                if st.button("Delete selected"):
                    # Remove lines first (avoid FK/orphans), keep ingredients table intact
                    lines = ses.exec(select(RecipeIngredient).where(RecipeIngredient.recipe_id == rid)).all()
                    for ln in lines:
                        ses.delete(ln)
                    r = ses.get(Recipe, rid)
                    if r:
                        ses.delete(r)
                    ses.commit()
                    st.success("Recipe deleted.")
                    st.rerun()

    # Inline editor (after clicking "Edit selected")
    if st.session_state.get("editing_recipe_id"):
        with get_session(engine) as ses:
            rid = st.session_state["editing_recipe_id"]
            init_name, init_url, init_notes, init_cat, init_df = _load_recipe_for_edit(ses, rid)
            cat_options = [c.name for c in ses.exec(select(Category)).all()]
        st.markdown("---")
        with st.expander(f"Editing: {init_name or '(unnamed)'}", expanded=True):
            with st.form("edit_form"):
                r_name = st.text_input("Recipe name", value=init_name)
                url = st.text_input("URL (optional)", value=init_url or "")
                notes = st.text_area("Notes / Instructions (optional)", value=init_notes or "")
                category = st.selectbox(
                    "Category",
                    ["(none)"] + cat_options,
                    index=(["(none)"] + cat_options).index(init_cat) if init_cat in ["(none)"] + cat_options else 0
                )
                edit_df = st.data_editor(
                    init_df,
                    num_rows="dynamic",
                    use_container_width=True,
                    key="manual_lines_edit",
                )
                c1, c2 = st.columns(2)
                with c1:
                    save_edit = st.form_submit_button("Save changes")
                with c2:
                    cancel_edit = st.form_submit_button("Cancel")
            if save_edit:
                with get_session(engine) as ses:
                    ok = _save_edit(
                        ses,
                        rid,
                        r_name or "Untitled Recipe",
                        url,
                        notes,
                        None if category == "(none)" else category,
                        edit_df.to_dict(orient="records"),
                    )
                if ok:
                    st.success("Recipe updated.")
                else:
                    st.error("Edit failed (recipe not found).")
                st.session_state["editing_recipe_id"] = None
                st.rerun()
            elif cancel_edit:
                st.session_state["editing_recipe_id"] = None
                st.rerun()

# -------------------------
# Meal Plan (ephemeral shopping list)
# -------------------------
elif page == "Meal Plan":
    st.header("Meal Plan")
    with get_session(engine) as ses:
        recipes = ses.exec(select(Recipe)).all()
    if not recipes:
        st.info("Add some recipes first in the Recipe Library.")
    else:
        names = [f"{r.name} (id {r.id})" for r in recipes]
        selections = st.multiselect("Select recipes for this period", names)
        selected_ids = []
        for s_opt in selections:
            try:
                selected_ids.append(int(s_opt.split("id ")[-1].rstrip(")")))
            except Exception:
                pass

        if selected_ids:
            with get_session(engine) as ses:
                consolidated = consolidate_for_shopping(ses, selected_ids)
            st.subheader("Combined Ingredients")
            df = pd.DataFrame(consolidated["preview_rows"])

            have_df = df[df["staple"]].copy()
            buy_df  = df[~df["staple"]].copy()

            left, right = st.columns(2)
            with left:
                st.write("Likely on hand")
                st.dataframe(
                    have_df,
                    use_container_width=True,
                    height=_auto_df_height(len(have_df)),
                )
            with right:
                st.write("To buy")
                st.dataframe(
                    buy_df,
                    use_container_width=True,
                    height=_auto_df_height(len(buy_df)),
                )

            st.subheader("Export (no save)")
            md_lines = [f"# Shopping List — {', '.join([n.split(' (id ')[0] for n in selections])}\n"]
            for grp, sub in df.groupby(["aisle"], dropna=False):
                md_lines.append(f"## {grp or 'Other'}\n")
                for _, row in sub.iterrows():
                    src = row.get("sources") or []
                    src_txt = ", ".join(src) if isinstance(src, list) else str(src)
                    md_lines.append(
                        f"- {row['ingredient']}: {row['qty']:.2f} {row['unit']} "
                        f"({'staple' if row['staple'] else 'buy'}) — {src_txt}"
                    )
            md_text = "\n".join(md_lines)
            st.download_button("Download Markdown", data=md_text, file_name="shopping_list.md")
        else:
            st.caption("Pick one or more recipes to see the combined list preview.")

# -------------------------
# Ingredients (replaces Pantry)
# -------------------------
elif page == "Ingredients":
    st.header("Ingredients")

    with get_session(engine) as ses:
        ings = list_ingredients(ses)
        usage = ingredient_usage_counts(ses)

    rows = []
    for i in ings:
        rows.append({
            "id": i.id,
            "name": i.name,
            "default_aisle": i.default_aisle,
            "is_staple": bool(i.is_staple),
            "preferred_unit": i.preferred_unit or "count",
            "used_in": usage.get(i.id, 0),
        })
    df_ing = pd.DataFrame(rows)

    if df_ing.empty:
        st.info("No ingredients yet—add a recipe first.")
    else:
        st.caption("Edit aisle/unit/staple. Rename to merge duplicates (same name) automatically.")
        original = df_ing.copy()
        edited = st.data_editor(
            df_ing,
            use_container_width=True,
            num_rows="dynamic",
            column_config={
                "is_staple": st.column_config.CheckboxColumn("staple"),
                "used_in": st.column_config.NumberColumn("used in", disabled=True),
                "id": st.column_config.NumberColumn("id", disabled=True),
            },
            hide_index=True,
            key="ingredient_editor",
        )

        c1, c2 = st.columns([1,1])
        with c1:
            if st.button("Save ingredient changes"):
                with get_session(engine) as ses:
                    # Renames (and merges) first
                    for _, row in edited.iterrows():
                        old = original.loc[original["id"] == row["id"]].iloc[0]
                        if str(row["name"]).strip() != str(old["name"]).strip():
                            rename_or_merge_ingredient(ses, int(row["id"]), str(row["name"]))
                    # Then update fields
                    for _, row in edited.iterrows():
                        upsert_ingredient(
                            ses,
                            name=str(row["name"]),
                            default_aisle=str(row["default_aisle"] or "Dry goods"),
                            is_staple=bool(row["is_staple"]),
                            preferred_unit=str(row["preferred_unit"] or "count"),
                        )
                st.success("Ingredient updates saved.")
                st.rerun()

        with c2:
            unused_count = int((edited["used_in"] == 0).sum()) if not edited.empty else 0
            if st.button(f"Delete all {unused_count} unused ingredients"):
                with get_session(engine) as ses:
                    removed = delete_unused_ingredients(ses)
                st.success(f"Deleted {removed} unused ingredients.")
                st.rerun()
