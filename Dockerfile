FROM debian:bookworm-slim
# helm is used to stop/start apps from the Apps list (uninstall / reinstall).
ARG HELM_VERSION=v3.16.4
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3-bottle python3-kubernetes python3-yaml gunicorn curl ca-certificates \
    && curl -fsSL "https://get.helm.sh/helm-${HELM_VERSION}-linux-amd64.tar.gz" \
        | tar -xz -C /tmp \
    && mv /tmp/linux-amd64/helm /usr/local/bin/helm \
    && rm -rf /tmp/linux-amd64 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY app.py aviary004.png favicon.ico /app/
ENV PORT=8086
EXPOSE 8086
USER nobody
CMD ["sh", "-c", "exec gunicorn -b 0.0.0.0:${PORT} --workers 2 --threads 4 app:app"]
