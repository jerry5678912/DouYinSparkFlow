FROM mcr.microsoft.com/playwright/python:v1.58.0-noble@sha256:678457c4c323b981d8b4befc57b95366bb1bb6aa30057b1269f6b171e8d9975a

WORKDIR /app

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements.txt

COPY --chown=pwuser:pwuser . /app
RUN mkdir -p /app/logs && chown -R pwuser:pwuser /app

# Cloud Run Jobs should run headlessly and exit when the task is complete.
ENV GITHUB_ACTIONS=true \
    PYTHONUNBUFFERED=1 \
    HOME=/home/pwuser

USER pwuser

ENTRYPOINT ["python", "main.py"]
