# Privacy defaults and sessions

## Decision

All data produced by a user is held in the memory of that user's session and in a temporary directory
of the session. The settings that ensure this are part of the code and are not configurable.

## Measures

| Measure | Implementation |
|---|---|
| Session state | one `gr.State` object per session, with a time-to-live and a callback that deletes the session's temporary files; no user data at module level |
| Browser storage | `run_history=False`; Gradio would otherwise store inputs and outputs in the browser |
| Telemetry | `analytics_enabled=False`, `GRADIO_ANALYTICS_ENABLED=False` and `HF_HUB_DISABLE_TELEMETRY=1`, set before Gradio is imported |
| Additional endpoints | `enable_monitoring=False`, `mcp_server=False`, `pwa=False`, `ssr_mode=False`; the footer contains no link to the API page |
| Uploads | size limit (`TST_MAX_UPLOAD`); each file is read once and then deleted |
| Downloads | unique names in the session directory; Gradio's cache is cleared after `TST_TEMP_TTL` |
| Logs | no texts, prompts, profile contents or file names |
| Error messages | taken from the message catalogue; no tracebacks or paths in the interface (`show_error=False`) |
| Network | local address by default; outbound connections only to the model endpoint, verified by a test with a socket guard |
| Response headers | `X-Frame-Options: DENY`, `frame-ancestors 'none'`, `Referrer-Policy: no-referrer`, `nosniff` |

## Hidden events

Gradio can exclude an event from its API page (`api_visibility="private"`). A test showed that such an
event can still be called directly in the way the browser calls it. The setting therefore reduces the
visible interface without restricting access. For this reason, no event performs an operation beyond
the caller's own session.

## Limits

- Gradio serves uploaded and generated files to any client that knows their URL; the URL contains a
  long random component. Uploads are therefore deleted immediately and downloads after `TST_TEMP_TTL`.
- Texts are sent to the model endpoint. Their handling there depends on the endpoint.
- Data in the temporary directory is not encrypted; the directory is protected by the file permissions
  `0700`.
