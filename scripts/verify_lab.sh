#!/usr/bin/env bash
# Verifica el laboratorio en ejecución: contenedores, aislamiento de Internet, firewall y captura.
# Uso:  bash scripts/verify_lab.sh        (con la red levantada: make up)
set -uo pipefail
cd "$(dirname "$0")/.."

PASS=0; FAIL=0
ok()   { printf '  [ OK ] %s\n' "$1"; PASS=$((PASS+1)); }
bad()  { printf '  [FALLA] %s\n' "$1"; FAIL=$((FAIL+1)); }
check(){ local d="$1"; shift; if "$@" >/dev/null 2>&1; then ok "$d"; else bad "$d"; fi; }

NODES=(lab-firewall lab-web lab-auth lab-fileserver lab-client1 lab-client2 lab-attacker lab-exfil lab-collector)

echo "1) Contenedores (${#NODES[@]} esperados)"
for n in "${NODES[@]}"; do
  [[ "$(docker inspect -f '{{.State.Running}}' "$n" 2>/dev/null)" == "true" ]] && ok "$n en ejecución" || bad "$n no está en ejecución"
done

echo "2) Redes internas (sin salida a Internet)"
for z in ext dmz lan srv mgmt; do
  net="anomalias-lab_${z}"
  [[ "$(docker network inspect -f '{{.Internal}}' "$net" 2>/dev/null)" == "true" ]] && ok "red ${z}: internal=true" || bad "red ${z}: no es interna"
done
# Prueba activa: ningún contenedor del laboratorio debe alcanzar Internet.
for n in lab-attacker lab-client1 lab-collector; do
  if docker exec "$n" python -c "import socket,sys; s=socket.socket(); s.settimeout(3); s.connect(('1.1.1.1',53))" >/dev/null 2>&1; then
    bad "$n alcanza Internet (1.1.1.1:53)"
  else
    ok "$n NO alcanza Internet"
  fi
done

echo "3) Firewall"
check "ruleset 'inet lab' cargado" docker exec lab-firewall nft list table inet lab
for s in ratelimit blocklist isolate; do
  check "conjunto ${s} con timeout" docker exec lab-firewall sh -c "nft list set inet lab ${s} | grep -q 'flags timeout'"
done
check "reenvío IP activo" docker exec lab-firewall sh -c '[ "$(cat /proc/sys/net/ipv4/ip_forward)" = 1 ]'

echo "4) Conectividad entre zonas a través del firewall"
check "cliente → servidor de autenticación (172.30.3.10)" docker exec lab-client1 python -c "import socket; socket.create_connection(('172.30.3.10',9000),3)" 
check "cliente → web (172.30.1.10)" docker exec lab-client1 python -c "import socket; socket.create_connection(('172.30.1.10',8080),3)"

echo "5) Captura y datos"
shopt -s nullglob
pcaps=(data/pcap/*.pcap*); flows=(data/flows/*)
(( ${#pcaps[@]} > 0 )) && ok "${#pcaps[@]} archivo(s) PCAP en data/pcap" || bad "sin PCAP en data/pcap (espera ~1 min tras make up)"
(( ${#flows[@]} > 0 )) && ok "flujos en data/flows" || bad "sin flujos en data/flows (el colector convierte cada minuto)"

echo
echo "Resultado: ${PASS} correctas, ${FAIL} fallidas"
exit $(( FAIL > 0 ))
