FROM node:22-slim
# python runtime for the worker + opencode as the worker's brain
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g opencode-ai@1.17.11
ENV HOME=/home/worker
RUN useradd -m -d /home/worker worker
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt
COPY . /app
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && mkdir -p /home/worker/.local/share/opencode && chown -R worker /home/worker /app
USER worker
ENTRYPOINT ["/entrypoint.sh"]
