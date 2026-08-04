# CWAC — Community Wellness Animal Clinic (pre-registration)

Django backend for the CWAC pre-registration system: a fair lottery replaces "first in line,"
and owner/pet info is collected ahead of time so check-in is fast and labels print.

> Full spec lives in [`Documents/`](Documents/) — `ImplementationPlan.md` is the authoritative,
> phased build plan. **Phases 0 and 1 are complete; the current branch implements Phase 2
> (staff auth, event management, signup URL, and QR download).**

---

## Setup (one time)

```bash
cd ~/cwac
python3 -m venv .venv                 # already done
source .venv/bin/activate
pip install -r requirements/dev.txt   # already done
cp .env.example .env                  # defaults work as-is; edit if you like
python manage.py migrate
python manage.py createsuperuser      # your first Admin (superuser + role=admin)
```

## Everyday commands

> Activate the venv first (`source .venv/bin/activate`), or call its interpreter directly:
> `.venv/bin/python manage.py ...`. The `make` targets below handle activation for you.

| What | Command |
|---|---|
| Run dev server (port **8011**) | `python manage.py runserver 8011` |
| Apply migrations | `python manage.py migrate` |
| Make migrations after model changes | `python manage.py makemigrations` |
| Django shell | `python manage.py shell` |
| Admin account | `python manage.py createsuperuser` (creates a full Admin: `is_staff` + `is_superuser` + `role=admin`) |
| System check | `python manage.py check` |
| Collect static (mirrors the Render build) | `python manage.py collectstatic --noinput` |
| Show migrations | `python manage.py showmigrations` |
| Run tests | `pytest` |

### Why port 8011?
Other Django sites on this server already use `8000`, so CWAC runs on **8011** to avoid
conflicts. `runserver 8011` binds to loopback (`127.0.0.1`) only — fine for on-box use or
SSH tunneling. Use `runserver 0.0.0.0:8011` if you must reach it from another LAN machine
(it's the dev server with `DEBUG=True`; don't expose it publicly).

## Makefile shortcuts

| Target | Action |
|---|---|
| `make serve` | `runserver` on `$SERVE_PORT` (default **8011**) |
| `make serve SERVE_PORT=8090` | run on a different port |
| `make migrate` | apply migrations |
| `make makemigrations` | create migrations |
| `make shell` | Django shell |
| `make superuser` | create an admin |
| `make check` | `manage.py check` |
| `make collectstatic` | collect static files |
| `make test` | run pytest |
| `make install` | `pip install -r requirements/dev.txt` |
| `make help` | list targets |

> The Makefile is **local-dev convenience only**. Render ignores it — deploy runs the
> `buildCommand` / `startCommand` / `preDeployCommand` in `render.yaml` directly.

## Environment

Dev runs out of the box on **SQLite** (no local Postgres needed). To use Postgres locally,
set `DATABASE_URL` in `.env`. `SMS_BACKEND=console` prints texts to the terminal during dev;
set it to `twilio` (with Twilio creds) only in production. See `.env.example`.

## Deploy

Render reads `render.yaml` (web service + managed Postgres). All secrets come from
environment variables and are never committed. Full deployment is wired in **Phase 11**.

> `communications/` is gitignored — it holds the original stakeholder email with real
> contact info, and this repo is public, so it stays local-only.
