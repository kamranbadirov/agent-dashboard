.PHONY: setup shell tui

PYTHON ?= python3.11
VENV := .venv
STAMP := $(VENV)/.installed

setup:
	brew bundle --file=Brewfile
	@rm -f $(STAMP)
	@$(MAKE) $(STAMP)

$(STAMP): requirements.txt
	$(PYTHON) -m venv --clear $(VENV)
	$(VENV)/bin/pip install -r requirements.txt
	$(VENV)/bin/pip check
	$(VENV)/bin/python -c "import textual, textual_image, PIL"
	@touch $@

shell:
	@if [ -f .venv/bin/activate ]; then . .venv/bin/activate; fi; exec "$${SHELL:-/bin/sh}"

tui: $(STAMP)
	.venv/bin/python server.py --tui
