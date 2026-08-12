FROM python:3.11.10-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_APP=run.py \
    PORT=5000

COPY requirements.txt .
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY . .
COPY dockers/gunicorn.conf.py /app/docker-gunicorn.conf.py

RUN addgroup --system appgroup \
    && adduser --system --ingroup appgroup appuser \
    && mkdir -p data logs \
    && chown -R appuser:appgroup /app

EXPOSE 5000

USER appuser


CMD ["/bin/bash", "./run.sh"]

#CMD ["gunicorn", "-c", "/app/docker-gunicorn.conf.py", "run:app"]
