
.PHONY: help docs tests test tox hook pre-commit black isort pylint flake8 mypy Makefile

# Trick to allow passing commands to make
# Use quotes (" ") if command contains flags (-h / --help)
args = `arg="$(filter-out $@,$(MAKECMDGOALS))" && echo $${arg:-${1}}`

# If command doesn't match, do not throw error
%:
	@:

help:
	@echo ""
	@echo "Commands:"
	@echo "  docs       	  Serve mkdocs on for development."
	@echo "  tests            Run tests with pytest-cov."
	@echo "  test <name>      Run tests maching the given <name>"
	@echo "  tox              Run tests with tox."
	@echo "  hook             Install pre-commit hook."
	@echo "  pre-commit       Run pre-commit hooks on all files."
	@echo "  black            Run black on all files."
	@echo "  isort            Run isort on all files."
	@echo "  pylint           Run pylint on all files."
	@echo "  flake8           Run flake8 on all files."
	@echo "  mypy             Run mypy on all files."


docs:
	@poetry run mkdocs serve

tests:
	@poetry run coverage run -m pytest -vv -s --log-cli-level=INFO

test:
	@poetry run pytest -s -vv --log-cli-level=INFO -k $(call args, "")

tox:
	@poetry run tox

hook:
	@poetry run pre-commit install

pre-commit:
	@poetry run pre-commit run --all-files

black:
	@poetry run black ./

isort:
	@poetry run isort ./

pylint:
	@poetry run pylint savestate/

flake8:
	@poetry run flake8 --max-line-length=120 --extend-ignore=E203,E501 savestate/

mypy:
	@poetry run mypy savestate/
