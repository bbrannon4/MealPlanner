# Meal Planner

Meal-planning tool for two people (or more): add recipes, build a weekly plan, and generate a consolidated shopping list split into staples vs. buy-this-week.

**Live app:** once deployed, both people just open the shared URL — no install needed.

## Local development (SQLite)

```bash
git clone <repo-url> && cd MealPlanner
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Without any configuration the app falls back to a local `data/mealplanner.db` SQLite file.

---

## Cloud deployment (shared, free)

### 1 — Create a Supabase database

1. Go to [supabase.com](https://supabase.com) and sign up (free).
2. Create a new project; wait ~2 min for it to provision.
3. Go to **Project Settings → Database → Connection string → URI**.
4. Copy the URI — it looks like:
   ```
   postgresql://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres
   ```

### 2 — Migrate your existing recipes

```bash
# In your local repo with .venv active:
export DATABASE_URL="postgresql://postgres.[ref]:[password]@..."
python scripts/migrate_to_postgres.py
```

This reads `data/mealplanner.db` and copies all recipes, ingredients, and categories to Supabase. Safe to re-run — skips records that already exist.

### 3 — Deploy to Streamlit Community Cloud

1. Push this repo to GitHub (can be private).
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
3. Click **New app**, select this repo and `app.py`.
4. In **Advanced settings → Secrets**, paste:
   ```toml
   DATABASE_URL = "postgresql://postgres.[ref]:[password]@..."
   ```
5. Click **Deploy**. Streamlit gives you a public URL — share it with your partner.

### 4 — Local dev pointing at Supabase (optional)

If you want your local copy to use the same cloud DB:

```bash
# .streamlit/secrets.toml  (gitignored — never commit this)
DATABASE_URL = "postgresql://..."
```

Then `streamlit run app.py` as normal.

---

## Project structure

```
meal-planner/
  app.py                    # Streamlit UI
  core/
    db.py                   # DB engine (SQLite fallback or Postgres via DATABASE_URL)
    schema.py               # SQLModel table definitions
    logic.py                # Business logic
    importers.py            # URL recipe scraper
    units.py, pantry.py
  scripts/
    migrate_to_postgres.py  # One-time SQLite → Postgres migration
  .streamlit/
    config.toml             # App settings (committed)
    secrets.toml            # Local secrets — DO NOT COMMIT (gitignored)
  data/.gitkeep
  requirements.txt
```

## Notes

- **Recipe import:** paste a URL in *Recipe Library → From URL*. Uses `recipe-scrapers`; edit ingredient list before saving.
- **Staples:** mark ingredients as staples in the Ingredients page — they appear in "likely on hand" and are excluded from the buy list.
- **Free tier limits:** Supabase pauses projects after 1 week of inactivity (wakes in ~5 sec on next visit). Streamlit Community Cloud apps also sleep after inactivity (~10 sec to wake). Both are fine for personal use.
