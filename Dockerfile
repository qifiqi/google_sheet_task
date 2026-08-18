FROM python:3.11.10-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_APP=run.py \
    PORT=5000

COPY requirements.txt .
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY static ./static
COPY templates ./templates
COPY stock_sdk ./stock_sdk
COPY run.py .
COPY .env .env.example .env.development .env.production .env.testing ./
COPY run.sh .

COPY dockers/gunicorn.conf.py /app/docker-gunicorn.conf.py

RUN addgroup --system --gid 1000 appgroup \
    && adduser --system --uid 1000 --ingroup appgroup appuser \
    && mkdir -p /app/logs /app/data \
    && chown -R appuser:appgroup /app \
    && chmod 777 /app/logs /app/data

EXPOSE 5000

USER appuser


CMD ["/bin/bash", "./run.sh"]

#CMD ["gunicorn", "-c", "/app/docker-gunicorn.conf.py", "run:app"]
