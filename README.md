# alembic migration
uv run python -m db.migrate up
uv run python -m db.migrate status
uv run alembic revision --autogenerate -m "init"
uv run alembic upgrade head