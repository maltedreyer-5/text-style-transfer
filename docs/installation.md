# Installation

## Requirements

- Python 3.11 or later; the CI tests Python 3.11, 3.12 and 3.13.
- An OpenAI-compatible chat-completions endpoint and, if the endpoint requires it, an API key.
- About 400 MB of disk space for the Python environment including the development tools (measured on
  Linux with Python 3.12).

The application establishes outbound connections only to the configured endpoint and requires no
internet access for its start.

## Installation with pip

```bash
git clone https://github.com/maltedreyer-5/text-style-transfer.git
cd text-style-transfer
python -m venv .venv
. .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -c constraints.txt .
cp .env.example .env              # then edit .env
text-style-transfer
```

`constraints.txt` pins all packages to the versions used in the tests. Without this file, pip
installs the newest versions within the ranges declared in `pyproject.toml`.

Verification:

```bash
text-style-transfer --version                                    # prints the version
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:7860/     # 200 while the application runs
```

## Installation with Docker

```bash
cp .env.example .env              # then edit .env
docker compose up --build -d
docker compose ps                 # the status shows "healthy" after the health check has passed
```

The compose file publishes the port on `127.0.0.1` only. The container runs with a read-only root
file system, without additional capabilities, with `no-new-privileges` and with a `tmpfs` for
temporary files.

## Operation behind a reverse proxy

1. Configure the proxy to authenticate users and to pass the user name in a header, for example
   `X-Remote-User`. The proxy must remove this header from incoming requests.
2. Set `TST_AUTH_HEADER=X-Remote-User`. Requests without the header are answered with status 401.
3. If the application is served under a path, set `TST_ROOT_PATH`, for example `/style`.

The verification is described in [Operation](operations.md#operation-for-other-users).

## Limits

- No Docker image is published; the image is built locally.
- The application was tested against a local test server that implements the chat-completions API.
  Providers that reject unknown parameters in `TST_LLM_EXTRA_BODY` answer with an error, which the
  interface reports.
