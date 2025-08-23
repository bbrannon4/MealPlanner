# File: README.md

# Meal Planner (Streamlit + SQLite)

Local, lightweight meal-planning tool for two people (or more): add recipes, select a plan, and generate a consolidated shopping list split into staples vs. buy-this-week.

## Quick start

```bash
# 1) clone the repo, cd into it
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

streamlit run app.py
```

The app creates a local SQLite DB at `data/mealplanner.db`.

## Structure
```
meal-planner/
  app.py
  core/
    __init__.py
    db.py
    schema.py
    units.py
    logic.py
    pantry.py
    importers.py
  data/
    .gitkeep
  exports/
    .gitkeep
  requirements.txt
  README.md
```

## Notes
- Put the `data/mealplanner.db` in a synced folder (iCloud/Dropbox) if you want to use it on multiple Macs.
- Unit handling via `pint`. Canonical units are simple defaults per ingredient; edit in-app later.
- **Recipe import:** paste a URL or ingredient text under *Recipe Library → Import Recipe*. Uses `recipe-scrapers`; you can edit before saving.
