format:
	ruff check --fix-only src/ tests/
	ruff format src/ tests/

lint:
	ruff check src/
	mypy src/ tests/