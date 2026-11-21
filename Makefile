COMPOSE = docker compose -f infra/docker-compose.yml

.PHONY: setup test verify up down status scan brute exfil rules flows synth pipeline pipeline-synth dashboard

setup:         ## Prepara una VM Ubuntu (Docker + entorno virtual de Python)
	bash scripts/setup_ubuntu.sh

test:          ## Pruebas unitarias y de integración (no requieren Docker)
	python -m pytest -q

verify:        ## Verifica contenedores, aislamiento de Internet, firewall y captura
	bash scripts/verify_lab.sh

up:            ## Levanta toda la red simulada
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

status:
	$(COMPOSE) ps

scan:          ## Escenario: escaneo de puertos desde el nodo atacante
	docker exec lab-attacker python -m generators.scenarios portscan

brute:         ## Escenario: fuerza bruta contra el servidor de autenticación
	docker exec lab-attacker python -m generators.scenarios bruteforce

exfil:         ## Escenario: exfiltración hacia el destino externo controlado
	docker exec lab-attacker python -m generators.scenarios exfil

rules:         ## Reglas y bloqueos activos en el firewall
	docker exec lab-firewall nft list ruleset

synth:         ## Datos sintéticos (sin Docker)
	python -m generators.synth_flows --out data/synthetic

pipeline:      ## Analiza la captura real del laboratorio
	python -m src.run_pipeline --data data

pipeline-synth:
	python -m src.run_pipeline --data data/synthetic

dashboard:
	streamlit run dashboard/app.py
