# Informe de instalación, ejecución y validación

## 1. Descripción del proyecto

El proyecto implementa un laboratorio reproducible para la detección de anomalías en una red empresarial simulada. La solución utiliza Docker para crear varias zonas de red, generar tráfico normal y ejecutar escenarios de ataque controlados. El tráfico se captura en un firewall, se transforma en flujos de red y posteriormente se analiza mediante detectores estadísticos y de aprendizaje automático.

El flujo general del sistema es:

```text
Docker y firewall
        ↓
Capturas PCAP en data/pcap/
        ↓
Colector y extracción de flujos
        ↓
Flujos en data/flows/
        ↓
Ventanas de 10 segundos por origen
        ↓
Detectores de anomalías
        ↓
Fusión de riesgo y explicación
        ↓
Bloqueo temporal, alertas y dashboard
```

El proyecto contiene las siguientes áreas principales:

- `infra/`: definición de la red Docker, firewall, nodos y colector.
- `generators/`: tráfico normal y escenarios de escaneo, fuerza bruta y exfiltración.
- `capture/`: transformación de capturas PCAP a flujos.
- `src/`: características, detectores, fusión de riesgo, explicaciones, respuesta, almacenamiento y pipeline.
- `dashboard/`: tablero de visualización con Streamlit.
- `Makefile`: comandos simplificados para operar el laboratorio.
- `README.md`: documentación resumida de uso.

## 2. Topología de red

La red está dividida en cinco zonas Docker. Cada zona utiliza una subred independiente:

| Zona | Subred | Componentes principales |
|---|---|---|
| `ext` | `172.30.0.0/24` | Destino externo controlado para exfiltración |
| `dmz` | `172.30.1.0/24` | Servidor web |
| `lan` | `172.30.2.0/24` | Clientes y atacante |
| `srv` | `172.30.3.0/24` | Servidor de autenticación y servidor de archivos |
| `mgmt` | `172.30.4.0/24` | Colector |

El firewall utiliza la dirección `.254` en cada zona:

- `172.30.0.254`
- `172.30.1.254`
- `172.30.2.254`
- `172.30.3.254`
- `172.30.4.254`

Los nodos principales tienen las siguientes direcciones:

| Contenedor | Dirección |
|---|---|
| `lab-web` | `172.30.1.10` |
| `lab-client1` | `172.30.2.31` |
| `lab-client2` | `172.30.2.32` |
| `lab-attacker` | `172.30.2.99` |
| `lab-auth` | `172.30.3.10` |
| `lab-fileserver` | `172.30.3.20` |
| `lab-exfil` | `172.30.0.20` |
| `lab-collector` | `172.30.4.10` |

Todo el tráfico entre zonas se enruta a través del firewall. Los escenarios comprueban que sus objetivos estén dentro del rango controlado `172.30.0.0/16`.

## 3. Requisitos

### 3.1. Software necesario

En Windows se requiere:

1. Docker Desktop con soporte para contenedores Linux.
2. Python 3.10 o superior para ejecutar el pipeline y el dashboard fuera de Docker.
3. PowerShell.
4. `make`, únicamente si se desean utilizar directamente los comandos del `Makefile`.

`make` no es obligatorio en Windows. Los comandos equivalentes con Docker Compose pueden ejecutarse directamente desde PowerShell.

### 3.2. Ubicación del proyecto

Abrir PowerShell o terminal preferida la raíz del proyecto:

## 4. Preparación inicial

Crear las carpetas donde se almacenarán las capturas y los flujos:

```powershell
New-Item -ItemType Directory -Force data, data\pcap, data\flows | Out-Null
```

La carpeta `data/` se utiliza como volumen compartido entre el equipo anfitrión y los contenedores.

## 5. Validación de la configuración Docker

Antes de iniciar los contenedores, validar el archivo Compose:

```powershell
docker compose -f infra\docker-compose.yml config
```

Si el comando termina sin errores, la configuración YAML y la interpolación de servicios son válidas.

La definición se encuentra en [`infra/docker-compose.yml`](./infra/docker-compose.yml).

## 6. Construcción y levantamiento del laboratorio

Ejecutar:

```powershell
docker compose -f infra\docker-compose.yml up -d --build
```

Este comando:

- Construye las imágenes del firewall, los nodos y el colector.
- Crea las cinco redes Docker.
- Inicia los nueve contenedores.
- Activa el reenvío IP en el firewall.
- Inicializa las reglas `nftables`.
- Inicia `tcpdump` para capturar tráfico.
- Inicia el colector de flujos.

Si se dispone de `make`, el comando equivalente es:

```powershell
make up
```

## 7. Comprobación del estado de los contenedores

Consultar el estado:

```powershell
docker compose -f infra\docker-compose.yml ps
```

Todos los servicios deberían aparecer activos, preferiblemente con estado `Up`.

También se pueden consultar los logs del firewall:

```powershell
docker logs -f lab-firewall
```

Y los logs del colector:

```powershell
docker logs -f lab-collector
```

Los logs permiten detectar errores de inicio, problemas de permisos, fallos de red o problemas al procesar capturas.

## 8. Generación de tráfico normal

Una vez iniciada la red, dejar los contenedores ejecutándose entre 20 y 30 minutos. Durante ese tiempo los clientes y el atacante generan tráfico normal.

Este período es importante porque el pipeline utiliza una parte inicial de la captura como referencia de comportamiento normal. Las capturas deben aparecer en:

```text
data\pcap\
```

El colector transforma las capturas y genera flujos en:

```text
data\flows\
```

No se deben ejecutar los escenarios de ataque inmediatamente después de iniciar Docker si se desea reproducir la metodología descrita.

## 9. Ejecución de los escenarios controlados

Los escenarios se ejecutan desde el contenedor atacante.

### 9.1. Escaneo de puertos

```powershell
docker exec lab-attacker python -m generators.scenarios portscan
```

Equivalente con `make`:

```powershell
make scan
```

### 9.2. Fuerza bruta

```powershell
docker exec lab-attacker python -m generators.scenarios bruteforce
```

Equivalente con `make`:

```powershell
make brute
```

### 9.3. Exfiltración

```powershell
docker exec lab-attacker python -m generators.scenarios exfil
```

Equivalente con `make`:

```powershell
make exfil
```

Los escenarios guardan la verdad de terreno en:

```text
data\labels.jsonl
```

Este archivo permite comparar posteriormente las detecciones con los eventos realmente ejecutados.

## 10. Instalación de dependencias de Python

Crear y activar un entorno virtual desde la raíz del proyecto:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Instalar las dependencias:

```powershell
python -m pip install -r requirements.txt
```

El archivo [`requirements.txt`](./requirements.txt) incluye, entre otras, las siguientes bibliotecas:

- `pandas` y `numpy` para manipulación numérica.
- `scikit-learn` para los detectores de aprendizaje automático.
- `shap` para explicaciones.
- `pyarrow` para archivos Parquet.
- `scapy` para procesamiento de red.
- `streamlit` para el dashboard.

## 11. Ejecución del pipeline

Después de generar y recolectar los datos, ejecutar:

```powershell
python -m src.run_pipeline --data data
```

Equivalente con `make`:

```powershell
make pipeline
```

El pipeline realiza las siguientes etapas:

1. Lee los flujos capturados.
2. Construye ventanas temporales de 10 segundos por origen.
3. Calcula las características de cada ventana.
4. Ejecuta los detectores estadísticos y de aprendizaje automático.
5. Fusiona las señales en un riesgo conjunto.
6. Considera la criticidad de los activos.
7. Genera explicaciones de las detecciones.
8. Produce alertas tempranas cuando corresponde.
9. Aplica bloqueos temporales si se utiliza el modo de respuesta.
10. Guarda resultados en archivos de salida y en una base SQLite.

Los resultados se almacenan dentro de `data/`, incluyendo los directorios de salida y el archivo `lab.db` cuando corresponda.

Para habilitar la aplicación de bloqueos reales en el firewall:

```powershell
python -m src.run_pipeline --data data --live
```

El mecanismo de respuesta utiliza el conjunto `inet lab blocklist` de `nftables`. Los elementos tienen tiempo de expiración y se eliminan automáticamente. Los servidores y componentes protegidos no deben bloquearse.

## 12. Ejecución con datos sintéticos

Para validar el pipeline sin levantar Docker:

```powershell
python -m generators.synth_flows --out data\synthetic
python -m src.run_pipeline --data data\synthetic
```

Equivalente con `make`:

```powershell
make synth
make pipeline-synth
```

Esta alternativa sirve para comprobar la lógica de detección y el formato de salida, pero no sustituye la validación del laboratorio Docker. Las métricas obtenidas con datos sintéticos no deben presentarse como resultados de la red real.

## 13. Visualización en el dashboard

Con el entorno virtual activado, iniciar Streamlit:

```powershell
streamlit run dashboard\app.py
```

Equivalente con `make`:

```powershell
make dashboard
```

Abrir en el navegador la dirección indicada por Streamlit, normalmente:

```text
http://localhost:8501
```

El dashboard permite revisar las detecciones y los resultados guardados por el pipeline.

## 14. Consulta de reglas del firewall

Para consultar las reglas y bloqueos activos:

```powershell
docker exec lab-firewall nft list ruleset
```

Equivalente con `make`:

```powershell
make rules
```

La política general del firewall es `accept` para mantener el laboratorio en modo de monitoreo. Las excepciones de bloqueo se aplican mediante el conjunto temporal de `nftables`.

## 15. Detención del laboratorio

Para detener y eliminar los contenedores y redes creados por Compose:

```powershell
docker compose -f infra\docker-compose.yml down
```

Equivalente con `make`:

```powershell
make down
```

La carpeta `data/` no se elimina automáticamente, por lo que las capturas y resultados permanecen disponibles para su análisis.

## 16. Secuencia completa recomendada

La ejecución recomendada, en orden, es:

```powershell
cd C:\Users\yatoG\Downloads\proyecto\proyecto
New-Item -ItemType Directory -Force data, data\pcap, data\flows | Out-Null
docker compose -f infra\docker-compose.yml config
docker compose -f infra\docker-compose.yml up -d --build
docker compose -f infra\docker-compose.yml ps
```

Después:

1. Dejar correr el tráfico normal durante 20–30 minutos.
2. Ejecutar el escaneo de puertos.
3. Ejecutar la fuerza bruta.
4. Ejecutar la exfiltración.
5. Esperar a que el colector procese los PCAP.
6. Activar el entorno virtual.
7. Ejecutar el pipeline.
8. Revisar los archivos de salida y `data\labels.jsonl`.
9. Abrir el dashboard.
10. Consultar las reglas del firewall si se ejecutó el modo `--live`.
11. Detener el laboratorio con `docker compose ... down`.

## 17. Verificaciones y criterios de éxito

La instalación puede considerarse funcional cuando:

- `docker compose ... config` termina sin errores.
- Los nueve contenedores aparecen activos.
- Se crean archivos `.pcap` en `data\pcap\`.
- Se crean flujos en `data\flows\`.
- Los escenarios terminan sin errores y generan `data\labels.jsonl`.
- El pipeline finaliza y genera resultados.
- El dashboard inicia y puede abrirse en `http://localhost:8501`.
- Las reglas de `nftables` se consultan correctamente.

## 18. Problemas frecuentes

### Docker Desktop no está iniciado

Iniciar Docker Desktop y repetir:

```powershell
docker info
```

Si Docker funciona, el comando debe devolver información del motor.

### Un contenedor termina inmediatamente

Consultar sus logs:

```powershell
docker logs lab-firewall
docker logs lab-collector
```

También revisar el estado completo:

```powershell
docker compose -f infra\docker-compose.yml ps -a
```

### No se generan capturas

Comprobar que el firewall esté activo, que `tcpdump` se haya iniciado y que exista la carpeta `data\pcap\` en el equipo anfitrión.

### No se generan flujos

Revisar los logs del colector y confirmar que existan archivos en `data\pcap\`. El colector depende de que el firewall produzca capturas válidas.

### PowerShell impide activar el entorno virtual

Si la política de ejecución lo impide, abrir PowerShell y ejecutar, según las políticas del equipo:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Después volver a activar:

```powershell
.\.venv\Scripts\Activate.ps1
```

### No se reconoce `make`

Usar los comandos equivalentes de Docker y Python descritos en este informe. En Windows no es necesario instalar `make` para operar el laboratorio.

## 19. Alcance de la validación

La configuración del proyecto y el archivo Compose están preparados para ejecutar el laboratorio, pero el arranque efectivo de los contenedores, el enrutamiento entre redes y la captura de tráfico deben verificarse en el equipo donde se realice la práctica.

Las métricas obtenidas con el generador sintético sirven como referencia del funcionamiento del pipeline. No deben citarse como resultados experimentales de la red Docker. Para obtener resultados del laboratorio real es necesario ejecutar toda la secuencia, conservar los datos generados y analizar las salidas producidas por el pipeline.

## 20. Conclusión

El proyecto puede levantarse en Windows utilizando Docker Desktop y PowerShell. El procedimiento completo consiste en validar el Compose, construir la red, mantener tráfico normal durante el período de entrenamiento, ejecutar los escenarios controlados, procesar las capturas con el pipeline y revisar los resultados mediante el dashboard.

El repositorio del proyecto está disponible en:

https://github.com/yatoDx/InfraestructuraSistemaAdaptativo

El punto de entrada principal para la operación Docker es:

```powershell
docker compose -f infra\docker-compose.yml up -d --build
```

Y el punto de entrada para el análisis es:

```powershell
python -m src.run_pipeline --data data
```
