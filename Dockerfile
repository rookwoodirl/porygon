FROM python:3.13-slim


RUN pip install uv

COPY . .
RUN uv sync

ENTRYPOINT ["uv", "run", "main.py", "--deploy"]
