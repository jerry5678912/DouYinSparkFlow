#!/bin/bash
set -euo pipefail

CONFIG_ENV_PATH="/app/.env"

if [[ ! -f "$CONFIG_ENV_PATH" ]]; then
  echo "Config file not found: $CONFIG_ENV_PATH" >&2
  exit 1
fi

python - <<'PY'
import os
import re
import shlex
from dotenv import dotenv_values

config_env_path = "/app/.env"
file_vars = {k: v for k, v in dotenv_values(config_env_path).items() if v is not None}
allowed_keys = {
    "BROWSER_TIMEOUT",
    "FRIEND_LIST_WAIT_TIME",
    "GITHUB_ACTIONS",
    "HITOKOTO_TYPES",
    "LOG_LEVEL",
    "MESSAGE_TEMPLATE",
    "PROXY_ADDRESS",
    "PYTHONUNBUFFERED",
    "TASK_RETRY_TIMES",
    "TASKS",
}

runtime_vars = {
    key: value
    for key, value in os.environ.items()
    if (key in allowed_keys or key.startswith("COOKIES_"))
    and re.fullmatch(r"[A-Z_][A-Z0-9_]*", key)
}
runtime_vars.update(
    {
        key: value
        for key, value in file_vars.items()
        if (key in allowed_keys or key.startswith("COOKIES_"))
        and re.fullmatch(r"[A-Z_][A-Z0-9_]*", key)
    }
)

with open('/etc/douyin-spark-flow.env', 'w', encoding='utf-8') as f:
    for key, value in runtime_vars.items():
        f.write(f'export {key}={shlex.quote(value)}\n')

with open('/tmp/douyin-spark-flow.cron', 'w', encoding='utf-8') as f:
    f.write(file_vars.get('CRON_SCHEDULE', os.environ.get('CRON_SCHEDULE', '')))

with open('/tmp/douyin-spark-flow.tz', 'w', encoding='utf-8') as f:
    f.write(file_vars.get('TZ', os.environ.get('TZ', 'UTC')))
PY

chmod 0600 /etc/douyin-spark-flow.env

CRON_HOUR="$(python - <<'PY'
from dotenv import dotenv_values
values = dotenv_values('/app/.env')
print(values.get('CRON_HOUR', '9'))
PY
)"
CRON_MINUTE="$(python - <<'PY'
from dotenv import dotenv_values
values = dotenv_values('/app/.env')
print(values.get('CRON_MINUTE', '0'))
PY
)"
CRON_SECOND="$(python - <<'PY'
from dotenv import dotenv_values
values = dotenv_values('/app/.env')
print(values.get('CRON_SECOND', '0'))
PY
)"
TZ="$(cat /tmp/douyin-spark-flow.tz)"
export TZ

if [[ -z "$CRON_HOUR" || -z "$CRON_MINUTE" || -z "$CRON_SECOND" ]]; then
  echo "CRON_HOUR, CRON_MINUTE and CRON_SECOND are required." >&2
  exit 1
fi

validate_integer() {
  local name="$1"
  local value="$2"
  local minimum="$3"
  local maximum="$4"

  if [[ ! "$value" =~ ^[0-9]+$ ]]; then
    echo "$name must be an integer." >&2
    exit 1
  fi
  if (( 10#$value < minimum || 10#$value > maximum )); then
    echo "$name must be between $minimum and $maximum." >&2
    exit 1
  fi
}

validate_integer "CRON_HOUR" "$CRON_HOUR" 0 23
validate_integer "CRON_MINUTE" "$CRON_MINUTE" 0 59
validate_integer "CRON_SECOND" "$CRON_SECOND" 0 59

if [[ ! "$TZ" =~ ^[A-Za-z0-9_+/-]{1,64}$ ]]; then
  echo "TZ contains unsupported characters." >&2
  exit 1
fi

CRON_SCHEDULE="${CRON_MINUTE} ${CRON_HOUR} * * *"

cat > /etc/cron.d/douyin-spark-flow <<EOF
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
${CRON_SCHEDULE} root /app/docker/run-task.sh >> /proc/1/fd/1 2>> /proc/1/fd/2
EOF

chmod 0644 /etc/cron.d/douyin-spark-flow

echo "[docker] timezone: ${TZ:-UTC}"
echo "[docker] cron schedule: ${CRON_SCHEDULE} (+${CRON_SECOND}s)"
echo "[docker] container started, waiting for scheduled runs"

exec cron -f
