# Deploy — Announce & Bounce Thesis Dashboard

Two steps. ~10 minutes total.

## 1) Push to GitHub

Open a terminal in the project root and run:

```bash
cd /Users/hamzabalik/binance-sentiment-bot

# Stage every dashboard-relevant file (gitignore drops the heavy ML
# artefacts automatically).
git add -A

git commit -m "deploy: public thesis dashboard"

# Replace HAMZA-USERNAME with your GitHub handle. Repo can be public OR
# private — Render supports both for free.
git remote add origin https://github.com/HAMZA-USERNAME/announce-and-bounce.git
git branch -M main
git push -u origin main
```

If GitHub asks to authenticate, paste a Personal Access Token instead of
your password (Settings → Developer settings → Tokens → Generate, scope
= `repo`).

## 2) Deploy on Render

1. Sign up at https://render.com (free, GitHub login works).
2. Dashboard → **New +** → **Blueprint**.
3. Connect the GitHub repo you just pushed.
4. Render reads `render.yaml`, shows the service config, hit **Apply**.
5. Wait ~3 minutes for the first build. The URL appears at the top:
   `https://announce-and-bounce.onrender.com`

That's it. Every future `git push` redeploys automatically.

## Free-tier caveat

The service sleeps after ~15 minutes of inactivity. First visitor after
sleep waits ~30 seconds for cold start. Subsequent visits are instant.
For your defence: open the URL 1 minute before, it'll be warm.

## What ships

- `src/` — backend + frontend static assets
- `data/processed/` — 14 dashboard data files (~1.8 MB total)
- `requirements-web.txt` — slim deps (no torch / transformers / playwright)
- `render.yaml` — service config

What stays local (gitignored): raw scraper data, FinBERT/CryptoBERT
scores, all kline parquets, model weights, the thesis Word file, etc.

## Local dev still works

```bash
python3 -m src.web.app
```

`ENV=production` is only set on Render, so locally you still get loopback
+ auto-reload.
