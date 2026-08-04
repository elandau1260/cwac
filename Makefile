# CWAC local-dev shortcuts.
# LOCAL ONLY — Render does not use this file; deploy runs the commands in render.yaml.

PYTHON     ?= .venv/bin/python
SERVE_PORT ?= 8011
MANAGE     = $(PYTHON) manage.py

.PHONY: serve migrate makemigrations shell superuser check collectstatic test install help

serve:          ## Run dev server on $(SERVE_PORT)
	$(MANAGE) runserver $(SERVE_PORT)

migrate:        ## Apply database migrations
	$(MANAGE) migrate

makemigrations: ## Create migrations from model changes
	$(MANAGE) makemigrations

shell:          ## Open the Django shell
	$(MANAGE) shell

superuser:      ## Create an admin user
	$(MANAGE) createsuperuser

check:          ## Run Django system checks
	$(MANAGE) check

collectstatic:  ## Collect static files (mirrors the Render build)
	$(MANAGE) collectstatic --noinput

test:           ## Run the test suite (pytest)
	$(PYTHON) -m pytest

install:        ## Install dev dependencies
	$(PYTHON) -m pip install -r requirements/dev.txt

help:           ## Show this help
	@awk 'BEGIN { FS = ":.*## "; print "Usage: make <target>\n" } /^[a-zA-Z_-]+:.*## / { printf "  %-16s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
