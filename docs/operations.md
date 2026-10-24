# Operation

Each section lists the commands for a task and the commands for checking its result.

## Start and stop

```bash
text-style-transfer                       # runs in the foreground; Ctrl+C stops it
docker compose up -d                      # with Docker
docker compose stop                       # sends SIGTERM; the temporary directory is removed
```

Check:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:7860/      # 200
docker compose ps                                                     # "healthy"
```

## Connection to the language model

In the tab *Transform*, a short text is run through *Style directly*. If the endpoint is configured incorrectly, the status
line names the problem: endpoint not reachable, key rejected, model not found, or the status code of
the answer. The endpoint can be tested without the application:

```bash
curl -s "$TST_LLM_BASE_URL/models" -H "Authorization: Bearer $TST_LLM_API_KEY"
```

## Operation for other users

1. Keep `TST_HOST=127.0.0.1` (or the default of the compose file) and place a reverse proxy in front
   of the application.
2. Configure the proxy to authenticate users, to set one header with the user name and to remove this
   header from incoming requests.
3. Set `TST_AUTH_HEADER` to the name of the header and, if required, `TST_ROOT_PATH`.
4. Restart the application.

Check:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:7860/                              # 401
curl -s -o /dev/null -w '%{http_code}\n' -H 'X-Remote-User: test' http://127.0.0.1:7860/     # 200
curl -sI https://proxy.example/style/ | grep -i -E 'x-frame-options|content-security'       # both present
```

## Additional profiles

1. Set up a profile in the application and download it as JSON in the tab *Profile*.
2. Copy the file into the profile directory. The file name without `.json` becomes the id and may
   contain lowercase letters, digits and `_`, for example `house_style.json`. An optional entry
   `"labels": {"en": "…", "de": "…"}` sets the displayed names.
3. Set `TST_PROFILE_DIR` to the directory and restart the application.

Check: the start log contains no `data error`, and the profile appears in the list of profiles. A
file that does not validate stops the start; the message names the file.

## Privacy notice

Write the notice as a Markdown file, set `TST_PRIVACY_NOTICE_FILE` to its path and restart the
application. Check: the notice appears in the tab *About*, together with the host name of the
language-model endpoint.

## Update

```bash
git pull
pip install -c constraints.txt .          # or: docker compose up --build -d
text-style-transfer --version
```

The application reads profile codes and profile files of format version 1.

## Logs

The log contains event types, durations and numbers of attempts. It contains no texts, prompts,
profile contents or file names. Failed requests to the model appear with the error type and the
number of the attempt.

```bash
docker compose logs --tail 50
```

## Limits

- The application has no user management; access control is a task of the proxy.
- All sessions are held by one process. A restart ends all sessions; profiles that were not kept as a
  code or file are lost.
- Profiles in `TST_PROFILE_DIR` are read at start and are not reloaded while the application runs.
