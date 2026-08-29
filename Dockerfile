FROM mcr.microsoft.com/playwright/python:v1.58.0-noble

WORKDIR /app

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY --chown=pwuser:pwuser . /app
RUN mkdir -p /app/logs && chown -R pwuser:pwuser /app

# Cloud Run Jobs should run headlessly and exit when the task is complete.
ENV GITHUB_ACTIONS=true \
    PYTHONUNBUFFERED=1 \
    HOME=/home/pwuser

USER pwuser

ENTRYPOINT ["python", "main.py"]
