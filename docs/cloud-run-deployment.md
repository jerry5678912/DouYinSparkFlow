# Cloud Run Jobs deployment

The production container is configured as a one-shot Cloud Run Job: it starts
`python main.py`, processes the configured accounts sequentially, and exits.
Cloud Scheduler triggers the job at the desired time.

## Prerequisites

- A Google Cloud project with billing enabled.
- The Google Cloud CLI (`gcloud`) installed and authenticated.
- A region selected for both Artifact Registry and Cloud Run.
- Your `TASKS` JSON and each `COOKIES_<unique_id>` JSON ready locally.

Do not commit cookie files or put cookie values in this repository.

## 1. Configure the project

Replace the placeholders before running these commands:

```bash
gcloud auth login
gcloud config set project PROJECT_ID
gcloud services enable run.googleapis.com \
  cloudscheduler.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com
```

## 2. Build and publish the image

Use the same region for Artifact Registry and Cloud Run to avoid unnecessary
cross-region transfer:

```bash
gcloud artifacts repositories create douyin-spark-flow \
  --repository-format=docker \
  --location=REGION

gcloud builds submit \
  --tag REGION-docker.pkg.dev/PROJECT_ID/douyin-spark-flow/app:latest .
```

The image entrypoint is already `python main.py`; do not use the old cron
entrypoint for Cloud Run Jobs.

## 3. Store configuration as secrets

Create local files outside Git (for example, `tasks.json` and
`cookies_ID1.json`) containing the JSON values. Then create one Secret Manager
secret for `TASKS` and one for each account cookie variable:

```bash
gcloud secrets create TASKS --data-file=tasks.json
gcloud secrets create COOKIES_ID1 --data-file=cookies_ID1.json
```

Repeat the second command for every account. Grant the Cloud Run Job's runtime
service account the `roles/secretmanager.secretAccessor` role on these secrets.

## 4. Create the Cloud Run Job

The following example is sized for two sequential accounts. Increase memory if
your own run logs show Chromium pressure:

```bash
gcloud run jobs create douyin-spark-flow \
  --image=REGION-docker.pkg.dev/PROJECT_ID/douyin-spark-flow/app:latest \
  --region=REGION \
  --tasks=1 \
  --max-retries=1 \
  --task-timeout=30m \
  --cpu=2 \
  --memory=4Gi \
  --set-env-vars=GITHUB_ACTIONS=true,PYTHONUNBUFFERED=1 \
  --set-secrets=TASKS=TASKS:latest,COOKIES_ID1=COOKIES_ID1:latest
```

Add more `COOKIES_<unique_id>=<secret>:latest` mappings as needed. If the job
already exists, use `gcloud run jobs update` with the same options.

Run one manual execution before scheduling:

```bash
gcloud run jobs execute douyin-spark-flow --region=REGION --wait
```

## 5. Schedule the job

Create a Cloud Scheduler HTTP job that calls the Cloud Run Jobs `:run` endpoint.
Use a dedicated scheduler service account and grant it permission to invoke the
Cloud Run Job:

```bash
gcloud scheduler jobs create http douyin-daily \
  --location=REGION \
  --schedule="17 9 * * *" \
  --time-zone="Asia/Singapore" \
  --uri="https://run.googleapis.com/v2/projects/PROJECT_ID/locations/REGION/jobs/douyin-spark-flow:run" \
  --http-method=POST \
  --oauth-service-account-email=SCHEDULER_SERVICE_ACCOUNT
```

This example runs daily at 09:17 Singapore time. Pick a minute other than `00`
to reduce schedule contention.

## Operations

```bash
gcloud run jobs executions list --job=douyin-spark-flow --region=REGION
gcloud run jobs executions describe EXECUTION_NAME --job=douyin-spark-flow --region=REGION
gcloud logging read 'resource.type="cloud_run_job"' --limit=50
```

Cloud Run Jobs are ephemeral: the container is recreated for each execution,
but the configuration remains in Secret Manager. A cookie only needs replacing
when Douyin invalidates it.
