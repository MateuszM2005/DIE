# DIE

Two implementations of the same puzzle game:

| Folder | What it is |
| --- | --- |
| `DIE-TS` | Browser client (TypeScript + Canvas) with a Django backend and live leaderboard |
| `DIE_Py` | Desktop client (Pygame), same levels and assets |

Game logic is unchanged. This repo is for running and sharing the projects, not as a public production deploy.

The browser leaderboard uses a local SQLite file that is **not** in git. `migrate` creates an empty database, so no previous scores are shipped.

## Requirements

- **Web:** Node.js 18+, Python 3.11+, and the packages in `DIE-TS/requirements.txt`
- **Desktop:** Python 3.11+, `pygame`, `Pillow` (see `DIE_Py/requirements.txt`)
- **Optional:** Docker, for the browser game only (the desktop build needs a real window)

## Web (`DIE-TS`)

From the repository root:

```bash
cd DIE-TS
npm install
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
npm run build
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

Listens on all interfaces, not only loopback. Open http://127.0.0.1:8000 or `http://<this-machine-ip>:8000` from another device on the same network.

Rebuild the client after TypeScript edits: `npm run build` (or `npm run dev` to watch).

### Makefile / Docker

```bash
make web          # build + migrate + runserver (uses python on PATH)
make docker       # docker compose up --build
```

```bash
docker compose up --build
```

Then http://127.0.0.1:8000 (or `http://<this-machine-ip>:8000`) — the container migrates a **new empty** database. The compose port is published on all host interfaces.

## Desktop (`DIE_Py`)

Must be started from `DIE_Py` so `font/`, `textures/`, and `levels/` resolve:

```bash
cd DIE_Py
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

```bash
make desktop
```

The window opens fullscreen. There is no Docker image for this target: Pygame needs a display.

## Layout

```
DIE-TS/        Django project + TypeScript client
  game/        Django app (auth, scores, SSE leaderboard)
  src/         TypeScript
  die/         Django project (settings, URLs, WSGI/ASGI)
DIE_Py/        Pygame entry: main.py
```
