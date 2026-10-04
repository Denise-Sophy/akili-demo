# Deploying to AWS Lambda

The MCP server runs on AWS Lambda (Python 3.12, eu-west-1) behind a public Function URL.

```bash
python scripts/build_lambda.py     # Linux zip from the exact versions tested locally, no Docker needed
python scripts/deploy_lambda.py    # idempotent: role, function, URL, log retention
AKILI_MCP_URL=https://<function-url>/mcp python -m evals.security_check   # run the suite against the live server
```

## Security setup
- **Deploy user:** an inline IAM policy scoped to one role, one function and its log group. No admin rights.
- **Execution role:** basic Lambda logging only.
- **Auth:** the Function URL is public; the server's own bearer-token check and scopes do the gating.
- **Secrets:** tokens are Lambda environment variables (KMS-encrypted at rest), never in the image or repo.
- **Audit:** audit lines go to CloudWatch Logs with 14-day retention.
- **Host check:** DNS-rebinding protection stays on, with only the Function URL hostname allowed.

## Gotchas found along the way
1. **Every request got 421.** The MCP SDK accepts only `localhost` by default. The Function URL hostname is now allowed explicitly via `AKILI_ALLOWED_HOSTS`.
2. **The second request crashed.** The MCP session manager runs once per app, but the Lambda adapter (Mangum) starts and stops the app on every request. A fresh app is now built per invocation (`build_app()`); the server is stateless, so nothing is lost.
3. **The build failed on Windows.** pip evaluates platform markers against the build machine, so Linux dependencies are resolved from the tested venv instead.
4. **403 before the code ran.** Public Function URLs need `lambda:InvokeFunctionUrl` plus `lambda:InvokeFunction` limited to URL calls (set via boto3, since older AWS CLIs lack the flag).

## Not yet
- A managed database. Memory is SQLite in `/tmp` and resets on restarts; production would use RDS Postgres.
- Secrets Manager.
- A WAF and API gateway in front.
- A reserved-concurrency cap (the account's concurrency limit is too low to set one).
