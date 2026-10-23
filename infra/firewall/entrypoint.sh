#!/bin/sh
set -e
sysctl -w net.ipv4.ip_forward=1 >/dev/null 2>&1 || true
sysctl -w net.ipv4.conf.all.rp_filter=0 >/dev/null 2>&1 || true

nft -f /etc/nftables/lab.nft

mkdir -p /data/pcap
# Solo cabeceras (-s 96), tráfico entrante por cada interfaz (-Q in) para no duplicar paquetes,
# y un archivo nuevo cada 60 s (-G 60) que luego procesa el colector.
tcpdump -i any -Q in -n -s 96 -Z root -G 60 \
  -w '/data/pcap/fw_%Y%m%d_%H%M%S.pcap' ip &

exec sleep infinity
