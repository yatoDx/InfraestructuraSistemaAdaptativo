#!/usr/bin/env bash
# Prepara una máquina virtual Ubuntu Server 22.04/24.04 para el laboratorio:
# Docker Engine + plugin Compose, herramientas básicas y entorno virtual de Python.
# Uso (desde la raíz del repositorio):  bash scripts/setup_ubuntu.sh
set -euo pipefail

if [[ "${EUID}" -eq 0 ]]; then
  echo "Ejecuta el script como usuario normal (usa sudo internamente)." >&2; exit 1
fi
. /etc/os-release
[[ "${ID}" == "ubuntu" ]] || { echo "Este script está pensado para Ubuntu (detectado: ${ID})." >&2; exit 1; }

echo "[1/5] Paquetes base"
sudo apt-get update -y
sudo apt-get install -y ca-certificates curl gnupg git make python3 python3-venv python3-pip tcpdump nftables

echo "[2/5] Docker Engine (repositorio oficial)"
if ! command -v docker >/dev/null 2>&1; then
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor --yes -o /etc/apt/keyrings/docker.gpg
  sudo chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update -y
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
else
  echo "    Docker ya está instalado: $(docker --version)"
fi

echo "[3/5] Permisos de Docker para el usuario ${USER}"
sudo systemctl enable --now docker
if ! id -nG "${USER}" | grep -qw docker; then
  sudo usermod -aG docker "${USER}"
  echo "    Usuario añadido al grupo docker: cierra sesión y vuelve a entrar (o usa 'newgrp docker')."
fi

echo "[4/5] Entorno virtual de Python (.venv)"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo "[5/5] Comprobación rápida"
docker --version
docker compose version
.venv/bin/python --version
echo
echo "Listo. Siguiente paso:  source .venv/bin/activate && make test && make up && make verify"
