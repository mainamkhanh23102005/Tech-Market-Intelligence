# Configuration and Secrets

## Environments

`APP_ENV` must be `local`, `test`, or `production`. `LOG_LEVEL` must be a standard uppercase Python level. Defaults are safe for local development; CI tests set values explicitly where behavior matters.

## Local setup

Copy `.env.example` to `.env`. Never add credentials to `.env.example`. `.env` and all environment variants are ignored except `.env.example`.

```powershell
Copy-Item .env.example .env
```

## Secret rules

- Supply secrets through process environment or future deployment secret manager.
- Never commit API keys, passwords, private keys, access tokens, connection strings with credentials, or real user data.
- Future provider keys are optional and absent by default.
- Use `SecretStr` or equivalent secret-aware types at configuration boundary.
- Do not serialize configuration objects containing secrets.
- Do not include secrets in exceptions, logs, test assertions, telemetry, URLs, command arguments, screenshots, or support bundles.
- Rotate a secret immediately if exposed; removal from latest file does not erase Git history.

## Validation behavior

Configuration loads at process startup. Invalid names/types fail fast. Error output may include field name and validation reason but never field value for secrets. M0 tests prove invalid environment handling and redacted secret representation.

## Logging fields

Allowed baseline fields: timestamp, level, event, component, request ID, trace ID, duration, status, and bounded counts. Job descriptions, profile text, raw source payloads, authorization headers, cookies, and secret values are prohibited.
