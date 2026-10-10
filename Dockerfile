FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY app app
COPY data data
COPY migrations migrations
COPY scripts scripts
COPY ui ui

RUN useradd --create-home coach
USER coach

EXPOSE 8000
# One worker: the /ask rate limiter keeps its counters in process memory.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
