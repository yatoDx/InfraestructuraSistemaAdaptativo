FROM python:3.12-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends iproute2 nmap curl \
 && rm -rf /var/lib/apt/lists/*
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
