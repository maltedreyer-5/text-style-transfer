# Security

## Supported versions

Security fixes are provided for the latest release.

## Reporting a vulnerability

Vulnerabilities are reported through GitHub's private vulnerability reporting:
[Report a vulnerability](https://github.com/maltedreyer-5/text-style-transfer/security/advisories/new).
Public issues are not suitable for this purpose. A report should state the version, the deployment
(local, Docker, behind a proxy), the steps to reproduce and the effect for an attacker. It should not
contain API keys, `.env` files or texts with personal data.

## Assumed deployments

The threat model assumes one of two deployments:

1. Local use by one person. The application listens on `127.0.0.1`; whoever can open the page is the
   person who started the application.
2. Use within an institution. The application listens on a local address and is reached only through
   a reverse proxy that authenticates users and passes the user name in a header (`TST_AUTH_HEADER`).
   The operator controls the configuration, the profile directory and the choice of the
   language-model endpoint.

## Protected assets

| Asset | Protection |
|---|---|
| Texts and profiles of a user | held only in the user's session, not shared between sessions, not written to logs, not stored in the browser |
| Uploaded files | size limit; deletion immediately after reading |
| Exported files | unique names in a session directory with permissions `0700`; deletion at the end of the session and after `TST_TEMP_TTL` |
| API key of the endpoint | read from the environment; neither logged nor shown in the interface |
| Shared language model | one retry layer with an overall deadline; a limit on concurrent requests (`TST_LLM_CONCURRENCY`) |
| Browser session | `X-Frame-Options`, `frame-ancestors 'none'`, `Referrer-Policy: no-referrer`, `nosniff` |
| Server | validation of profile codes and files with size limits, also during decompression; rejection of uploads of unknown types; Word files are parsed without resolving external entities |

The interface contains no privileged operations. Packaged data and the profile directory are only
read.

## Outside the scope

The following properties are intended or result from operation. They are not regarded as
vulnerabilities.

- Operation without authentication. With `TST_HOST=0.0.0.0` or a published port and without an
  authenticating proxy, every function is available to every client that reaches the port. The
  application has no user management of its own.
- Identity headers from clients. `TST_AUTH_HEADER` trusts the configured header. A proxy that does not
  remove this header from incoming requests allows any client to claim any identity.
- Processing at the endpoint. Every text is sent to `TST_LLM_BASE_URL`. Logging, retention and
  training at the endpoint are outside the application.
- Model output. Results can be wrong or offensive or contain additions. The checks are heuristics.
- Prompt injection by the user. The user's text, description, rules and own sliders become part of
  the instructions to the model and affect only that user's results. Free text from a loaded profile
  code is shown after loading; a code does not identify its author.
- File URLs within the retention time. Gradio serves cached files to any client that has the exact
  URL, which contains a long random component. Uploads are deleted at once, downloads after
  `TST_TEMP_TTL`.
- Load by authenticated users within the limits. Rate limiting per user is a task of the proxy.
- Local access to the machine. Whoever can read the memory of the process, the temporary directory or
  the environment of the process can read texts and the API key.
- Content of exported skills. A skill contains the description, rules and own sliders of a profile
  unchanged and gives instructions to a model. A skill received from another person is untrusted input
  for the system that loads it; Anthropic recommends using skills only from trusted sources.
- Content of the profile directory. Profiles placed there by the operator are trusted in the same way
  as the configuration.
