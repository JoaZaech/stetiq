# The maintenance assistant's image, as docker-compose.yml builds it. The build context is
# the repo root, since the showcase takes stetiq as a uv path source (../..); only what
# Dockerfile.dockerignore lets through is sent.

FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv
RUN useradd --create-home --uid 1000 assistant
WORKDIR /src
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY showcase/plant-assistant ./showcase/plant-assistant
WORKDIR /src/showcase/plant-assistant
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
RUN uv sync --frozen --no-dev && chown -R assistant:assistant /src
USER assistant
EXPOSE 8000
# The assistant's stetiq token is issued once the server is up (compose's `tokens`
# service) and read from the file it writes.
CMD ["sh", "-c", "STETIQ_TOKEN=$(cat /tokens/maintenance-assistant) exec .venv/bin/uvicorn plant_assistant.assistant:app_from_env --factory --host 0.0.0.0 --port 8000"]
