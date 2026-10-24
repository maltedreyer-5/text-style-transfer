# Changes to the system

This chapter lists what the application writes, opens or changes, and how each change is undone.

| Object | Location | Time | Removal |
|---|---|---|---|
| Python packages | the virtual environment or the Docker image | installation | delete the environment (`rm -rf .venv`) or the image (`docker image rm text-style-transfer:1.0.0`) |
| Listening socket | `TST_HOST:TST_PORT`, by default `127.0.0.1:7860` | while running | stop the process |
| Temporary directory `text-style-transfer-*` | the temporary directory of the system (`TMPDIR`, usually `/tmp`) | at start; one subdirectory per session for exports | removed at a regular stop (SIGINT or SIGTERM); session subdirectories at the end of the session; otherwise by the cleanup of the operating system or by hand |
| Gradio cache | `gradio/` in the temporary directory | for uploads and for files offered for download | entries older than `TST_TEMP_TTL` are removed while the application runs; the directory can be deleted when the application is stopped |
| Log output | standard output and standard error | while running | no removal required; the log contains no texts, prompts or file names |
| Outbound connections | `TST_LLM_BASE_URL` only | for each model request | not applicable |

The application does not write into its installation directory, the working directory or the
repository. It does not store data in the browser. Gradio's run history in local storage is disabled,
and no cookies are set as long as `TST_AUTH_HEADER` is not set; the tests verify both properties.
With an authenticating proxy, the proxy determines the cookies. The application does not contact
Gradio, Hugging Face or other services for updates, telemetry or fonts, and it does not modify the
profile directory (`TST_PROFILE_DIR`).

## Verification

```bash
# while running: the listening socket of the process
ss -ltnp | grep 7860

# temporary files of the running instance
ls -la "${TMPDIR:-/tmp}"/text-style-transfer-*

# after a regular stop
ls -d "${TMPDIR:-/tmp}"/text-style-transfer-* 2>/dev/null || echo "removed"
```

## Limits

- If the process is terminated without cleanup, for example by `kill -9` or a power failure, the
  temporary directory remains and has to be removed by hand or by the operating system.
- Uploaded files exist on disk between upload and reading. A file of a type that the upload field
  does not accept is rejected by Gradio before the application receives it; it remains in the Gradio
  cache until it is older than `TST_TEMP_TTL`.
- Files offered for download remain in the Gradio cache until they are older than `TST_TEMP_TTL`.
