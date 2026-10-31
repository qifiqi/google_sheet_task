FROM python:3.11-slim-trixie

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_APP=run.py \
    PORT=5000 \
    TZ=Asia/Shanghai

COPY requirements.txt .
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

# Word 报告转 PDF 依赖 LibreOffice（writer 足够，不装全套）；构建机需可访问 Debian 源。
RUN apt-get update \
    && apt-get install -y --no-install-recommends libreoffice-writer fontconfig tzdata \
    && rm -rf /var/lib/apt/lists/*

# 运行用户先建好，后面 COPY 直接带 owner，避免收尾 chown -R 在 overlay 里再复制一份全量文件。
RUN addgroup --system --gid 1000 appgroup \
    && adduser --system --uid 1000 --ingroup appgroup appuser \
    && mkdir -p /app/logs /app/data

COPY --chown=appuser:appgroup app ./app
COPY --chown=appuser:appgroup static ./static
COPY --chown=appuser:appgroup templates ./templates
COPY --chown=appuser:appgroup run.py .
COPY --chown=appuser:appgroup run.sh .

COPY --chown=appuser:appgroup dockers/gunicorn.conf.py /app/docker-gunicorn.conf.py

# 报告中文字体（仓库自带，OFL 许可）装入系统字体目录，并显式映射雅黑→Noto。
COPY app/assets/fonts/ /usr/share/fonts/custom/
COPY dockers/fontconfig/62-microsoft-yahei-alias.conf /etc/fonts/conf.d/62-microsoft-yahei-alias.conf
RUN fc-cache -f && chmod 777 /app/logs /app/data

EXPOSE 5000

USER appuser


#CMD ["/bin/bash", "./run.sh"]

CMD ["gunicorn", "-c", "/app/docker-gunicorn.conf.py", "run:app"]
