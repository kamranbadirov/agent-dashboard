.PHONY: setup shell tui web

PYTHON ?= python3.11

setup:
	brew bundle --file=Brewfile
	$(PYTHON) -m venv .venv
	.venv/bin/pip install textual textual-image

shell:
	@if [ -f .venv/bin/activate ]; then . .venv/bin/activate; fi; exec "$${SHELL:-/bin/sh}"

tui:
	.venv/bin/python server.py --tui

web:
	python3 server.py
