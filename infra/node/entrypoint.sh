#!/bin/sh
# Enruta todo el tráfico entre zonas por el firewall (172.30.0.0/16 vía FW_GW).
set -e
if [ -n "$FW_GW" ]; then
  ip route replace 172.30.0.0/16 via "$FW_GW" || true
fi
exec "$@"
