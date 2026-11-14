FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.0 /uv /uvx /bin/
WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/opt/terps-venv
ENV PATH="/opt/terps-venv/bin:$PATH"
COPY pyproject.toml uv.lock /app/
RUN uv sync --locked --python /usr/local/bin/python
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 && rm -rf /var/lib/apt/lists/*
COPY pipeline /app/pipeline
COPY public/data /app/public/data
CMD ["uv", "run", "--no-sync", "pytest", "-q"]
