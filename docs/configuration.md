# Configuration

All settings are environment variables with the prefix `TST_`. They can be placed in a `.env` file in
the directory the application is started from (`.env.example` lists all of them). An invalid value
stops the start with a message that names the variable.

## Server

| Variable | Default | Meaning |
|---|---|---|
| `TST_HOST` | `127.0.0.1` | Address to listen on. `0.0.0.0` makes the application reachable from the network. |
| `TST_PORT` | `7860` | Port. |
| `TST_ROOT_PATH` | empty | Path under which a reverse proxy serves the application, for example `/style`. |

## Language model

| Variable | Default | Meaning |
|---|---|---|
| `TST_LLM_BASE_URL` | `http://localhost:8000/v1` | Base URL of the OpenAI-compatible endpoint. |
| `TST_LLM_API_KEY` | `not-needed` | API key, if the endpoint requires one. |
| `TST_LLM_MODEL` | `local-model` | Model name sent with each request. |
| `TST_LLM_TIMEOUT` | `120` | Seconds per request. |
| `TST_LLM_MAX_ATTEMPTS` | `3` | Attempts per call, including the first. Only connection errors, timeouts, 429 and 5xx are retried. |
| `TST_LLM_RETRY_DELAY` | `2` | Seconds before the first retry; doubled each time. |
| `TST_LLM_DEADLINE` | `300` | Upper limit in seconds for all attempts of one call together. |
| `TST_LLM_CONCURRENCY` | `2` | Model requests of this application at the same time; further requests wait. |
| `TST_LLM_EXTRA_BODY` | empty | JSON object merged into every request, for example `{"temperature": 0.7}` or server-specific options. |

No sampling parameters are sent unless they are set in `TST_LLM_EXTRA_BODY`; the server's or model's
defaults apply.

## Limits

| Variable | Default | Meaning |
|---|---|---|
| `TST_MAX_INPUT_TOKENS` | `10000` | Maximum estimated tokens of one text (one token per three characters). |
| `TST_MIN_INPUT_TOKENS` | `20` | Minimum estimated tokens of one text. |
| `TST_OUTPUT_TOKEN_FACTOR` | `2.5` | Output budget = target words × 1.6 × factor … |
| `TST_OUTPUT_TOKEN_MIN` | `512` | … but at least this … |
| `TST_OUTPUT_TOKEN_MAX` | `8000` | … and at most this. |
| `TST_MAX_UPLOAD` | `5mb` | Maximum size of an uploaded file (`b`, `kb`, `mb`). |

## Retention

| Variable | Default | Meaning |
|---|---|---|
| `TST_SESSION_TTL` | `3600` | Seconds a session's data is kept after its last change if the tab stays open. Closing the tab ends the session earlier. |
| `TST_TEMP_TTL` | `1800` | Seconds export files are kept. |
| `TST_HISTORY_SIZE` | `20` | Runs kept in the history of a session. |

## Operation

| Variable | Default | Meaning |
|---|---|---|
| `TST_AUTH_HEADER` | empty | Header in which a reverse proxy passes the authenticated user. Requests without it are rejected. |
| `TST_PROFILE_DIR` | empty | Directory with additional profile JSON files, read once at start. The file name (without `.json`) is the profile id: lowercase letters, digits and `_`. |
| `TST_PRIVACY_NOTICE_FILE` | empty | Markdown file shown in the *About* tab. |
| `TST_SECURITY_HEADERS` | `true` | Send `X-Frame-Options`, `frame-ancestors`, `Referrer-Policy` and `X-Content-Type-Options`. |

## Limits

- The token figures are estimates. The exact count depends on the model's tokenizer, which the
  application does not load.
- `TST_PROFILE_DIR` is read only at start; new files need a restart.
- `TST_LLM_EXTRA_BODY` applies to all steps; a setting per step is not available.
