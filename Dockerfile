FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

COPY pyproject.toml README.md ./
COPY src ./src
COPY docs ./docs
COPY config.toml ./config.toml

CMD ["python", "-m", "devmate"]
