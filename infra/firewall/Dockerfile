FROM debian:bookworm-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends nftables tcpdump iproute2 procps \
 && rm -rf /var/lib/apt/lists/*
COPY lab.nft /etc/nftables/lab.nft
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
