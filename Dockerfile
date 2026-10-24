# SPDX-FileCopyrightText: 2026 Malte Dreyer
# SPDX-License-Identifier: MIT
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TST_HOST=0.0.0.0 \
    TST_PORT=7860

RUN useradd --create-home --uid 10001 app
WORKDIR /app
COPY pyproject.toml constraints.txt README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir -c constraints.txt . && rm -rf /app/src /app/build

USER app
EXPOSE 7860
# Inside the container the app must listen on all interfaces; compose.yaml
# publishes the port on 127.0.0.1 of the host only.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('TST_PORT', '7860') + '/', timeout=4)"]
CMD ["text-style-transfer"]
