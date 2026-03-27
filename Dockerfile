FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir .

COPY docs ./docs
COPY .skills ./.skills
COPY config.toml ./config.toml
COPY config.docker.toml ./config.docker.toml

EXPOSE 8001 8765

CMD ["python", "-m", "devmate"]
