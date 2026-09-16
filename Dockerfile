FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends bubblewrap sudo iptables \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 jobgroup \
    && useradd --uid 10001 --gid jobgroup --no-create-home --home-dir /nonexistent appuser \
    && useradd --uid 10002 --gid jobgroup --no-create-home --home-dir /nonexistent sandboxuser
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py ./
COPY agent/ ./agent/
COPY analysis/ ./analysis/
COPY execution/ ./execution/
COPY api/ ./api/
COPY demos/ ./demos/
COPY deploy/sandbox.py /usr/local/bin/flake-sandbox
COPY deploy/sudoers /etc/sudoers.d/flakedetective
RUN chmod 0755 /usr/local/bin/flake-sandbox \
    && chmod 0440 /etc/sudoers.d/flakedetective \
    && visudo -cf /etc/sudoers.d/flakedetective \
    && mkdir -p /data /work/jobs \
    && chown appuser:jobgroup /data /work/jobs \
    && chmod 2770 /work/jobs
USER appuser
EXPOSE 8000
CMD ["python", "-m", "api.serve"]
