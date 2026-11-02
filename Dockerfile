# The stetiq demo image: the web UI over the plant-kg example's tracking database.
#
#   cd frontend && npm ci && npm run build && cd ..   # the wheel ships the built UI (ADR 0003)
#   docker build -t stetiq .
#   docker run --rm -p 5000:5000 stetiq                # then http://localhost:5000/ui
#
# Set STETIQ_TRACKING_URI (and mount a volume) to open your own tracking database instead.
#
# Build arg SEED (default plant-kg) picks what the image holds. SEED=none skips the plant-kg
# seed: the image runs `stetiq server` with auth on, over an empty SQLite tracking database
# in /data (mount a volume there to keep it). Issue an API token inside the container:
#
#   docker build --build-arg SEED=none -t stetiq-server .
#   docker run -d --name stetiq -p 5000:5000 -v stetiq-data:/data stetiq-server
#   docker exec stetiq stetiq token create ada --grant '*=edit'   # prints the token once

FROM python:3.14-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv
WORKDIR /src
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN test -f src/stetiq/_frontend/index.html \
    || { echo "src/stetiq/_frontend is missing: run 'npm run build' in frontend/ first" >&2; exit 1; }
RUN uv build --wheel --out-dir /dist

FROM python:3.14-slim
ARG SEED=plant-kg
RUN case "$SEED" in plant-kg|none) ;; *) echo "SEED must be plant-kg or none, not '$SEED'" >&2; exit 1;; esac
RUN useradd --create-home --uid 1000 stetiq \
    && mkdir /data && chown stetiq:stetiq /data
COPY --from=build /dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

# Seed the demo (SEED=plant-kg) by replaying its committed Claude recording
# (examples/plant-kg/llm-cache/, copied with the example): reproducible, no claude CLI, no
# network. The example's own code is only needed to build the data; the UI reads the
# tracking database.
COPY --chown=stetiq:stetiq examples/plant-kg /tmp/plant-kg
USER stetiq
RUN if [ "$SEED" = plant-kg ]; then \
        python /tmp/plant-kg/demo.py \
            --tracking-uri sqlite:////data/stetiq.db \
            --graph-file /tmp/plant-kg/.graphdb/plant.json; \
    fi \
    && rm -rf /tmp/plant-kg

# STETIQ_DATABASE_URL is the server's and `stetiq token create`'s; the same file.
ENV STETIQ_SEED=$SEED \
    STETIQ_TRACKING_URI=sqlite:////data/stetiq.db \
    STETIQ_DATABASE_URL=sqlite:////data/stetiq.db \
    STETIQ_ACTOR=demo
WORKDIR /data
EXPOSE 5000
# Both bind every interface inside the container; Docker's -p decides who can reach it.
# The demo serves its UI with --no-auth; SEED=none runs the server, which needs a token.
CMD ["sh", "-c", "if [ \"$STETIQ_SEED\" = none ]; then exec stetiq server --host 0.0.0.0 --port 5000; else exec stetiq ui --host 0.0.0.0 --port 5000 --no-auth; fi"]
