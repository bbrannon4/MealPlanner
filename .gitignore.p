# --- OS junk ---
.DS_Store
.AppleDouble
.LSOverride
Icon?
Thumbs.db

# --- Python build/artifacts ---
__pycache__/
*.py[cod]
*$py.class
*.so
build/
dist/
*.egg-info/
.eggs/
wheels/
pip-wheel-metadata/

# --- Virtual environments ---
.venv/
venv/
env/
ENV/

# --- Caches / tooling ---
.pytest_cache/
.mypy_cache/
.ruff_cache/
.cache/
.tox/
.nox/
.coverage
.coverage.*
htmlcov/

# --- Notebooks ---
.ipynb_checkpoints/
.ipython/

# --- Editors/IDEs ---
.vscode/
.idea/
*.code-workspace
*.sublime-*

# --- Streamlit ---
.streamlit/

# --- Project data & outputs ---
# (keep folders but ignore contents)
data/*
!data/.gitkeep
exports/*
!exports/.gitkeep

# --- SQLite databases (safety net) ---
*.db
*.sqlite
*.sqlite3

# --- Logs ---
*.log

# --- Env files (if you ever add them) ---
.env
.env.*
