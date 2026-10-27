# The command-line programs as an image. Nothing here serves traffic; the health command is the image's check.
# Run against a PostgreSQL the container can reach, for example:
#   docker run --rm --network host -e POSTGRES_PASSWORD=... databases-model-two-ways:dev rental-shop-report
FROM python:3.13.1-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.lock ./
RUN pip install --require-hashes -r requirements.lock

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-deps .

RUN useradd --system --uid 10001 --no-create-home app
USER app

HEALTHCHECK --interval=30s --timeout=20s --retries=3 CMD ["rental-shop-health"]
CMD ["rental-shop-health"]
