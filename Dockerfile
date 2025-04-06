FROM python:3.13-slim


RUN apk install uv

ENTRYPOINT ["uv", "run", "main.py"]
