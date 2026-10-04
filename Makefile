PYTHON ?= python3

.PHONY: check test compile

check: compile test

compile:
	$(PYTHON) -m compileall -q spark40 tests

test:
	$(PYTHON) -m unittest discover -s tests -t .
