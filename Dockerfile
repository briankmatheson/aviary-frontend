FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3-bottle python3-kubernetes gunicorn \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY app.py aviary004.png favicon.ico /app/
ENV PORT=8086
EXPOSE 8086
USER nobody
CMD ["sh", "-c", "exec gunicorn -b 0.0.0.0:${PORT} --workers 2 --threads 4 app:app"]
