# AI News (auto-refreshing)

Setup:
1. Create a GitHub repo and push these files to `main`.
2. Repo Settings > Pages > Source: **GitHub Actions**.
3. Actions tab > "Update AI news" > Run workflow (first deploy).

It then rebuilds and redeploys at 11:00 and 23:00 UTC daily.
Edit `FEEDS` in `build.py` to change sources. Local preview: `pip install -r requirements.txt && python build.py`, open `docs/index.html`.
