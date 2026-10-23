.PHONY: setup shell tui web

setup:
	brew bundle --file=Brewfile
	python3 -m venv .venv
	.venv/bin/pip install textual

shell:
	@if [ -f .venv/bin/activate ]; then . .venv/bin/activate; fi; exec "$${SHELL:-/bin/sh}"

tui:
	.venv/bin/python server.py --tui

web:
	python3 server.py
