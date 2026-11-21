# Detección de anomalías en red empresarial simulada

Laboratorio reproducible: red simulada con Docker, tráfico normal y escenarios de ataque, captura en el firewall, detección (Z-Score, IQR, Isolation Forest, One-Class SVM), fusión con riesgo, explicación (SHAP), mitigación con nftables y alerta temprana.

## Topología (`infra/docker-compose.yml`)

| Zona | Red | Nodos |
|---|---|---|
| ext | 172.30.0.0/24 | exfil (.20) destino externo controlado |
| dmz | 172.30.1.0/24 | web (.10) |
| lan | 172.30.2.0/24 | client1 (.31), client2 (.32), attacker (.99) |
| srv | 172.30.3.0/24 | auth (.10), fileserver (.20) |
| mgmt | 172.30.4.0/24 | collector (.10) |

El firewall tiene la IP `.254` en cada zona y todo tráfico entre zonas pasa por él. Los nodos y todos los parámetros se definen en `config/lab.yaml` (ruta alternativa con la variable `LAB_CONFIG`); `src/config.py` solo trae valores por defecto.

## Máquina virtual (Ubuntu Server en VirtualBox)

Recomendado: Ubuntu Server 22.04/24.04, 4 vCPU, 8 GB de RAM, 40 GB de disco, adaptador NAT (solo para instalar paquetes).

```bash
git clone https://github.com/yatoDx/InfraestructuraSistemaAdaptativo.git && cd InfraestructuraSistemaAdaptativo
make setup            # Docker Engine + .venv con las dependencias
source .venv/bin/activate
make test             # 36 pruebas, sin Docker
make up && make verify
```

Guía completa paso a paso: `docs/guia-laboratorio/` (LaTeX y PDF).

## Uso con Docker

```bash
make up              # levanta toda la red (un solo comando)
make scan            # escaneo de puertos desde el atacante (nmap)
make brute           # fuerza bruta contra el servidor de autenticación
make exfil           # exfiltración sintética hacia el destino externo
make pipeline        # analiza lo capturado en data/
python -m src.run_pipeline --data data --live   # aplica bloqueos reales en el firewall
make dashboard       # tablero Streamlit (indicar la carpeta data/out)
make rules           # ver reglas y bloqueos activos
make down
```

Deja correr el tráfico normal al menos 20-30 minutos antes de lanzar escenarios (el primer 40 % de la captura se usa para entrenar con tráfico normal).

## Uso sin Docker (desarrollo)

```bash
pip install -r requirements.txt
make synth
make pipeline-synth
make dashboard
```

## Parámetros y diseño implementado (`config/lab.yaml`)

- Partición temporal: 40 % entrenamiento (solo normal) / 20 % validación / resto prueba (`--val-frac`).
- Umbral de alerta calibrado solo con la validación (máx. F1 si hay anomalías; si no, FPR objetivo), acotado a 30–70. `--no-calibrate` usa el umbral fijo de la configuración; `--val-frac 0 --no-calibrate` reproduce la partición 40/60 original.
- Respuesta escalonada: alerta ≥ 50, limitación de tasa ≥ 60, bloqueo ≥ 70 (TTL creciente con el riesgo, tope 900 s), aislamiento ≥ 85 (600 s). Conjuntos nftables `ratelimit`, `blocklist` e `isolate`, todos con *timeout*.
- Redes Docker `internal: true`: sin salida a Internet (`make verify` lo comprueba).
- Métricas adicionales: PR-AUC, FPR, MTTD, tasa de contención, acciones falsas y error del pronóstico frente a la línea base ingenua.

## Flujo de datos

`tcpdump` (firewall) → `data/pcap/` → colector (`capture/pcap_to_flows.py`) → `data/flows/` → `src/features` (ventanas de 10 s por origen) → `src/detectors` → `src/fusion_risk` → `src/explain` → `src/response` / `src/forecast` → `data/**/out/` (Parquet/CSV + `lab.db` SQLite).

Los escenarios escriben su verdad de terreno en `data/labels.jsonl` y solo aceptan objetivos dentro de `172.30.0.0/16`.

## Notas

- `capture/pcap_to_flows.py` reemplaza a Zeek con un extractor ligero; si prefieres Zeek, basta con producir flujos con las mismas columnas.
- La mitigación crea elementos con *timeout* en los conjuntos `inet lab ratelimit|blocklist|isolate`; la reversión es automática al vencer. Los servidores e infraestructura (`PROTECTED`) nunca se bloquean.
- El firewall usa política `accept` (modo monitoreo) salvo para los conjuntos de respuesta.
