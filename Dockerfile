FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy
WORKDIR /app
RUN pip install --no-cache-dir uv==0.13.7
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev
COPY probe_core ./probe_core
COPY service ./service
COPY agent ./agent
COPY migrations ./migrations
COPY alembic.ini ./
RUN useradd --create-home --uid 10001 netguardian
USER netguardian
CMD ["/app/.venv/bin/uvicorn", "service.api:app_factory", "--factory", "--host", "0.0.0.0", "--port", "8000"]
