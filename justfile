venv:
    uv venv
    uv sync --extra dev

# Set shell to bash and source venv before each command
set shell := ["bash", "-c", "source .venv/bin/activate && bash -c \"$0\""]

format:
    ruff format .

lint:
    ruff check .

lint-fix:
    ruff check --fix .
    
typecheck:
    pyrefly check .
    ty check .

test:
    pytest tests/

check: lint typecheck test

fix: format lint-fix typecheck test

set positional-arguments

run *args:
    generate "$@"

