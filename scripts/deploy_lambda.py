"""Create or update the Akili MCP server on AWS Lambda behind a Function URL. Idempotent.

    python scripts/build_lambda.py && python scripts/deploy_lambda.py

Needs the AWS CLI and boto3 (pip install boto3). Uses the CLI's current credentials and region. Tokens come from AKILI_TOKENS in .env
and are set as (KMS-encrypted) Lambda environment variables; they are never printed.
"""
import json
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
FUNCTION = "akili-mcp"
ROLE = "akili-mcp-lambda-role"
ZIP = "build/akili-lambda.zip"
ENV_FILE = ROOT / "build" / "lambda-env.json"
RESERVED_CONCURRENCY = 5
LOG_RETENTION_DAYS = 14


def aws(*args: str, check: bool = True) -> dict | None:
    proc = subprocess.run(["aws", *args, "--output", "json"], cwd=ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        if check:
            sys.exit(f"aws {' '.join(args[:2])} failed:\n{proc.stderr.strip()}")
        return None
    return json.loads(proc.stdout) if proc.stdout.strip() else {}


def write_env(allowed_hosts: str) -> str:
    tokens = dotenv_values(ROOT / ".env").get("AKILI_TOKENS")
    if not tokens:
        sys.exit("AKILI_TOKENS missing from .env")
    ENV_FILE.write_text(json.dumps({"Variables": {
        "AKILI_TOKENS": tokens,
        "AKILI_AUDIT_LOG": "stdout",
        "AKILI_MEMORY_DB": "/tmp/memory.db",
        "AKILI_ALLOWED_HOSTS": allowed_hosts,
    }}), encoding="utf-8")
    return f"file://{ENV_FILE.relative_to(ROOT).as_posix()}"


def main() -> None:
    if not (ROOT / ZIP).exists():
        sys.exit(f"{ZIP} not found: run scripts/build_lambda.py first")

    role = aws("iam", "get-role", "--role-name", ROLE, check=False)
    if role is None:
        trust = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"},
                                                        "Action": "sts:AssumeRole"}]}
        role = aws("iam", "create-role", "--role-name", ROLE, "--assume-role-policy-document", json.dumps(trust))
        aws("iam", "attach-role-policy", "--role-name", ROLE,
            "--policy-arn", "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole")
        print("created role; waiting for IAM to propagate")
        time.sleep(12)
    role_arn = role["Role"]["Arn"]

    existing = aws("lambda", "get-function", "--function-name", FUNCTION, check=False)
    current = aws("lambda", "get-function-url-config", "--function-name", FUNCTION, check=False) if existing else None
    host = urlparse(current["FunctionUrl"]).hostname if current else ""
    try:
        env_arg = write_env(host)
        if existing is None:
            aws("lambda", "create-function", "--function-name", FUNCTION, "--runtime", "python3.12",
                "--handler", "server.lambda_handler.handler", "--role", role_arn,
                "--zip-file", f"fileb://{ZIP}", "--memory-size", "512", "--timeout", "30",
                "--architectures", "x86_64", "--environment", env_arg)
            print("created function")
        else:
            aws("lambda", "update-function-code", "--function-name", FUNCTION, "--zip-file", f"fileb://{ZIP}")
            aws("lambda", "wait", "function-updated-v2", "--function-name", FUNCTION)
            aws("lambda", "update-function-configuration", "--function-name", FUNCTION, "--environment", env_arg)
            print("updated function code and configuration")
        aws("lambda", "wait", "function-updated-v2", "--function-name", FUNCTION)

        if current is None:
            current = aws("lambda", "create-function-url-config", "--function-name", FUNCTION, "--auth-type", "NONE")
            aws("lambda", "add-permission", "--function-name", FUNCTION, "--statement-id", "FunctionUrlPublic",
                "--action", "lambda:InvokeFunctionUrl", "--principal", "*", "--function-url-auth-type", "NONE")
            # Public Function URLs also need lambda:InvokeFunction, limited to calls arriving via the URL.
            # Older AWS CLIs lack --invoked-via-function-url, so this one call goes through boto3.
            import boto3

            boto3.client("lambda").add_permission(
                FunctionName=FUNCTION, StatementId="FunctionUrlInvoke", Action="lambda:InvokeFunction",
                Principal="*", InvokedViaFunctionUrl=True)
            print("created function URL (auth is the server's own bearer-token check)")
            host = urlparse(current["FunctionUrl"]).hostname
            aws("lambda", "update-function-configuration", "--function-name", FUNCTION, "--environment", write_env(host))
            aws("lambda", "wait", "function-updated-v2", "--function-name", FUNCTION)
    finally:
        ENV_FILE.unlink(missing_ok=True)  # never leave tokens on disk outside .env

    if aws("lambda", "put-function-concurrency", "--function-name", FUNCTION,
           "--reserved-concurrent-executions", str(RESERVED_CONCURRENCY), check=False) is None:
        print(f"note: could not reserve concurrency {RESERVED_CONCURRENCY} (new accounts often have a low "
              "account limit); the function still works without the cap")

    log_group = f"/aws/lambda/{FUNCTION}"
    aws("logs", "create-log-group", "--log-group-name", log_group, check=False)
    aws("logs", "put-retention-policy", "--log-group-name", log_group, "--retention-in-days", str(LOG_RETENTION_DAYS))

    print(f"\nlive: {current['FunctionUrl'].rstrip('/')}/mcp")


if __name__ == "__main__":
    main()
