# The stetiq demo image: the web UI over the plant-kg example's tracking database.
#
#   cd frontend && npm ci && npm run build && cd ..   # the wheel ships the built UI (ADR 0003)
#   docker build -t stetiq .
#   docker run --rm -p 5000:5000 stetiq                # then http://localhost:5000/ui
#
# Set STETIQ_TRACKING_URI (and mount a volume) to open your own tracking database instead.

FROM python:3.14-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv
WORKDIR /src
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN test -f src/stetiq/_frontend/index.html \
    || { echo "src/stetiq/_frontend is missing: run 'npm run build' in frontend/ first" >&2; exit 1; }
RUN uv build --wheel --out-dir /dist

FROM python:3.14-slim
RUN useradd --create-home --uid 1000 stetiq \
    && mkdir /data && chown stetiq:stetiq /data
COPY --from=build /dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

# Seed the demo with the offline rules extractor: reproducible, no LLM, no network. The
# example's own code is only needed to build the data; the UI reads the tracking database.
COPY --chown=stetiq:stetiq examples/plant-kg /tmp/plant-kg
USER stetiq
RUN python /tmp/plant-kg/demo.py --extractor rules \
        --tracking-uri sqlite:////data/stetiq.db \
        --graph-file /tmp/plant-kg/.graphdb/plant.json \
    && rm -rf /tmp/plant-kg

ENV STETIQ_TRACKING_URI=sqlite:////data/stetiq.db \
    STETIQ_ACTOR=demo
WORKDIR /data
EXPOSE 5000
# --no-auth: inside the container the UI must bind every interface; Docker's -p decides
# who can reach it.
CMD ["stetiq", "ui", "--host", "0.0.0.0", "--port", "5000", "--no-auth"]
