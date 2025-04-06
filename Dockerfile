FROM python:3.13-slim


RUN pip install uv

ENTRYPOINT ["uv", "run", "main.py"]
