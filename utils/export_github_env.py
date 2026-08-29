import json
import os
import re
import secrets
import sys


ENV_KEY_PATTERN = re.compile(r"^[A-Z_][A-Z0-9_]*$")


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def to_dotenv_value(value: str) -> str:
    # Keep .env single-line values by escaping real line breaks.
    return value.replace("\r", "").replace("\n", "\\n")


def validate_env_key(key: str) -> str:
    if not ENV_KEY_PATTERN.fullmatch(key):
        raise ValueError(
            f"Invalid environment variable name: {key!r}; use A-Z, 0-9 and underscore"
        )
    return key


def append_github_env_block(env_file, key: str, value: str) -> None:
    key = validate_env_key(key)
    delimiter = f"__ENV_{secrets.token_hex(16)}__"
    while delimiter in value.splitlines():
        delimiter = f"__ENV_{secrets.token_hex(16)}__"
    env_file.write(f"{key}<<{delimiter}\n")
    env_file.write(value)
    env_file.write(f"\n{delimiter}\n")


def as_env_string(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def main() -> None:
    vars_raw = os.getenv("VARS_JSON", "{}")
    secrets_raw = os.getenv("SECRETS_JSON", "{}")
    github_env = os.getenv("GITHUB_ENV")

    if not github_env:
        fail("GITHUB_ENV is not set")

    try:
        vars_map = json.loads(vars_raw)
    except json.JSONDecodeError as exc:
        fail(f"VARS_JSON is not valid JSON: {exc}")

    try:
        secrets_map = json.loads(secrets_raw)
    except json.JSONDecodeError as exc:
        fail(f"SECRETS_JSON is not valid JSON: {exc}")

    if not isinstance(vars_map, dict):
        fail("VARS_JSON must be a JSON object")
    if not isinstance(secrets_map, dict):
        fail("SECRETS_JSON must be a JSON object")

    dotenv_map = {}
    try:
        vars_map = {validate_env_key(str(key)): value for key, value in vars_map.items()}
        secrets_map = {
            validate_env_key(str(key)): value for key, value in secrets_map.items()
        }
    except ValueError as exc:
        fail(str(exc))

    with open(github_env, "a", encoding="utf-8") as env_file:
        for key, value in vars_map.items():
            env_value = as_env_string(value)
            append_github_env_block(env_file, str(key), env_value)
            dotenv_map[str(key)] = env_value

        for key, value in secrets_map.items():
            env_value = as_env_string(value)
            append_github_env_block(env_file, str(key), env_value)
            dotenv_map[str(key)] = env_value

    dotenv_lines = [f"{key}={to_dotenv_value(value)}" for key, value in dotenv_map.items()]
    with open(".env", "w", encoding="utf-8") as dotenv_file:
        dotenv_file.write("\n".join(dotenv_lines) + "\n")
    os.chmod(".env", 0o600)

    print("Environment values exported; .env refreshed with restricted permissions.")
    print(f"VARS_JSON exported: {len(vars_map)}")
    print(f"SECRETS_JSON exported: {len(secrets_map)}")


if __name__ == "__main__":
    main()
