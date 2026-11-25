 **Universidad de Costa Rica — Escuela de Ciencias de la Computación e Informática**
**CI-0121 Redes de comunicación de datos - II Semestre 2026 — Grupo 04**
**Docente:** Maeva Muñoz Meléndez
 
**Estudiantes:**
- Si Min Liang Liang (C4G500)
- Valeria Vindas Gutiérrez (C18603)
Este repositorio contiene el informe de investigación y dos implementaciones en P4 sobre BMv2 y Mininet:
 
| Carpeta | Contenido |
|---|---|
| [`lab1-router/`](lab1-router/) | Router IPv4 estático con tres routers P4 y cuatro hosts. |
| [`lab2-counters/`](lab2-counters/) | Contadores y estadísticas de tráfico con un controlador en Python. |
| [`informe/`](informe/) | Informe de investigación (`Informe.pdf`). |
 
**Video demostrativo:** ``
 
## Estructura del repositorio
 
```text
.
├── README.md
├── informe/
│   └── informe.pdf
├── lab1-router/
│   ├── Makefile
│   ├── topology.py
│   ├── r1-commands.txt
│   ├── r2-commands.txt
│   ├── r3-commands.txt
│   ├── p4src/
│   │   └── router.p4
│   └── tests/
│       ├── router_tests.py
│       └── results.txt
└── lab2-counters/
    ├── Makefile
    ├── topology.py
    ├── controller.py
    ├── send_traffic.py
    └── p4src/
        └── counters.p4
```
 
Las carpetas `build/` y `logs/` se generan al compilar y ejecutar, y no forman parte del repositorio.
 
## Requisitos
 
- Compilador P4 (`p4c-bm2-ss`).
- BMv2 (`simple_switch` y `simple_switch_CLI`).
- Mininet.
- Python 3 y Scapy.
Se utilizó la máquina virtual de P4 Tutorials (Ubuntu), que incluye estas herramientas. En esa VM los scripts de Mininet se ejecutan con el Python del entorno virtual, que es el que tiene Scapy y las librerías de P4:
 
```text
/home/p4/src/p4dev-python-venv/bin/python3
```
 
Todos los comandos de este documento se ejecutan dentro de la VM.
 
---
 
# Lab 1: Router IPv4 estático
 
Este laboratorio implementa un router IPv4 que reenvía paquetes por medio de una tabla de rutas estáticas con LPM (Longest Prefix Match). Además, reescribe las direcciones MAC y decrementa el TTL de los paquetes en cada salto. Cuando el TTL se agota, genera un mensaje ICMP Time Exceeded. Los paquetes sin una ruta correspondiente son descartados.
 
## Funcionalidades
 
- Procesamiento de encabezados Ethernet e IPv4.
- Enrutamiento mediante una tabla LPM configurada desde el control plane.
- Decremento del TTL y descarte de paquetes con TTL agotado.
- Reescritura de las direcciones MAC de origen y destino al reenviar paquetes.
- Descarte de paquetes cuando no existe una ruta.
- Generación de mensajes ICMP Time Exceeded cuando se agota el TTL.
- Recálculo de los checksums IPv4 e ICMP.
**Limitaciones:** no se implementa procesamiento de IPv6 ni respuesta ARP en los routers. Se utilizan entradas ARP estáticas configuradas en los hosts.
 
## Archivos
 
| Archivo | Descripción |
|---|---|
| `p4src/router.p4` | Programa P4 del router: parsing, reenvío, manejo de TTL e ICMP Time Exceeded. |
| `topology.py` | Creación y configuración de la topología en Mininet. |
| `r1-commands.txt`, `r2-commands.txt`, `r3-commands.txt` | Rutas estáticas de cada router. |
| `tests/router_tests.py` | Pruebas automáticas de las funcionalidades del router. |
| `tests/results.txt` | Salida de la última ejecución de `make test`. Es la evidencia de las pruebas. |
| `Makefile` | Atajos para compilar, levantar la topología, probar y limpiar. |
 
## Topología
 
La topología es lineal: tres routers P4 (r1, r2 y r3) y cuatro hosts (h1, h2, h3 y h4), cada uno en su propia subred.
 
- **h1** se conecta a **r1**, por el puerto 1.
- **h2** se conecta a **r2**, por el puerto 1.
- **h3** y **h4** se conectan a **r3**, por los puertos 1 y 2.
- Los routers se enlazan en línea: **r1–r2** (r1:2 – r2:2) y **r2–r3** (r2:3 – r3:3).
| Host | IP | Gateway | Router |
|---|---|---|---|
| h1 | 10.0.1.1/24 | 10.0.1.254 | r1 |
| h2 | 10.0.2.2/24 | 10.0.2.254 | r2 |
| h3 | 10.0.3.3/24 | 10.0.3.254 | r3 |
| h4 | 10.0.4.4/24 | 10.0.4.254 | r3 |
 
### Direcciones MAC
 
- **Host:** `00:00:00:00:<n>:<n>`, donde `n` es el número del host (por ejemplo, h1 es `00:00:00:00:01:01`).
- **Interfaz de router:** `00:00:00:<router>:<puerto>:00` (por ejemplo, r2 puerto 3 es `00:00:00:02:03:00`).
| Router | Puerto 1 | Puerto 2 | Puerto 3 |
|---|---|---|---|
| r1 | `00:00:00:01:01:00` (h1) | `00:00:00:01:02:00` (r2) | — |
| r2 | `00:00:00:02:01:00` (h2) | `00:00:00:02:02:00` (r1) | `00:00:00:02:03:00` (r3) |
| r3 | `00:00:00:03:01:00` (h3) | `00:00:00:03:02:00` (h4) | `00:00:00:03:03:00` (r2) |
 
Cada host tiene una entrada ARP estática que asocia su gateway con la MAC de la interfaz del router por la que sale.
 
## Cómo ejecutarlo
 
Todos los comandos se ejecutan desde la carpeta `lab1-router/`.
 
| Comando | Qué hace |
|---|---|
| `make compile` | Compila `p4src/router.p4` y genera `build/router.json`. |
| `make topology` | Levanta la red (cargando las rutas de `r1-commands.txt`, `r2-commands.txt` y `r3-commands.txt`) y abre el prompt `mininet>`. |
| `make test` | Ejecuta las pruebas y guarda la salida en `tests/results.txt`. |
| `make clean` | Limpia Mininet. |
 
Orden recomendado:
 
```bash
cd lab1-router
make compile
make topology
```
 
En el prompt `mininet>` se puede probar `pingall` o `h1 ping -c 2 h4`. Se sale con `exit`. Después, para correr las pruebas automáticas:
 
```bash
make test
```
 
Si una ejecución anterior terminó con error, ejecutar `make clean` antes de volver a empezar.
 
## Pruebas y resultados
 
### Conectividad
 
Con la topología abierta, `pingall` confirma que todos los hosts se comunican a través de los tres routers.
 
```text
mininet> pingall
*** Ping: testing ping reachability
h1 -> h2 h3 h4
h2 -> h1 h3 h4
h3 -> h1 h2 h4
h4 -> h1 h2 h3
*** Results: 0% dropped (12/12 received)
```
 
### Pruebas automáticas
 
`make test` ejecuta cinco pruebas y, si todas pasan, termina con `RESULTADO: TODO OK`. La salida completa queda en `tests/results.txt`.
 
| Prueba | Qué se verifica | Resultado esperado |
|---|---|---|
| 1. Ping | 12 pares de hosts. | Todos responden. |
| 2. TTL, MAC y checksum | Paquete con TTL=64 capturado con Scapy en el destino. | El TTL baja 1 por cada salto (h1 → h4 llega con 61), la MAC origen es la del último router, la MAC destino es la del host y el checksum es válido. |
| 3. TTL agotado | Paquete con TTL=1. | Llega a r1 y no se reenvía a h4. |
| 4. Paquete sin ruta | Paquete a 10.0.9.9 (ruta inexistente). | Llega a r1 pero no sale hacia r2; el ping tiene 100 % de pérdida. |
| 5. ICMP Time Exceeded | Paquetes de h1 a h4 con TTL 1, 2 y 3. | h1 recibe un ICMP tipo 11 desde el router donde se agotó el TTL (10.0.1.254, 10.0.12.2 y 10.0.23.2). |
 
---
 
# Lab 2: Contadores y estadísticas de tráfico
 
Este laboratorio implementa un switch P4 que recopila estadísticas de tráfico mediante contadores por flujo, contadores globales por protocolo y registros con información sobre el tamaño de los paquetes. Un controlador en Python se comunica con el switch por Thrift (`simple_switch_CLI`), consulta las estadísticas cada 5 segundos y detecta flujos elefante.
 
## Archivos
 
| Archivo | Descripción |
|---|---|
| `p4src/counters.p4` | Programa P4: reenvío L2, contadores por flujo y protocolo, y registros de tamaño de paquetes. |
| `topology.py` | Topología en Mininet con un switch BMv2 y cuatro hosts. |
| `controller.py` | Configura las tablas, consulta los contadores y detecta flujos elefante. |
| `send_traffic.py` | Genera tráfico TCP, UDP, ICMP y de otros protocolos con Scapy. |
| `Makefile` | Compila el programa P4 y genera `build/counters.json`. |
 
## Topología
 
Un switch P4 y cuatro hosts conectados directamente.
 
```text
h1 (10.0.0.1) --- p1 --+
h2 (10.0.0.2) --- p2 --+
                       +--- s1 (BMv2)
h3 (10.0.0.3) --- p3 --+
h4 (10.0.0.4) --- p4 --+
```
 
Cada host tiene la IP `10.0.0.N`, la MAC `00:00:00:00:00:0N` y está conectado al puerto `N` del switch. El controlador usa estas direcciones para configurar la tabla de reenvío L2.
 
## Cómo ejecutarlo
 
Se necesitan dos terminales dentro de la VM, ambas en la carpeta `lab2-counters/`.
 
**1. Compilar el programa P4** (genera `build/counters.json`):
 
```bash
cd lab2-counters
make
```
 
**2. Iniciar la topología** (terminal 1):
 
```bash
sudo $(which python3) topology.py
```
 
Se abre la consola de Mininet con los cuatro hosts y el switch.
 
**3. Ejecutar el controlador** (terminal 2):
 
```bash
python3 controller.py --threshold 1000000
```
 
El controlador instala las entradas de las tablas y consulta los contadores cada 5 segundos. El parámetro `--threshold` es la cantidad de bytes a partir de la cual un flujo se considera elefante. El intervalo también se puede cambiar:
 
```bash
python3 controller.py --threshold 1000000 --interval 5
```
 
**4. Generar tráfico** (desde la consola de Mininet). Los hosts deben usar el Python del entorno virtual, que tiene Scapy:
 
```bash
mininet> h1 /home/p4/src/p4dev-python-venv/bin/python3 send_traffic.py --dst 10.0.0.2 --proto udp --count 100 --size 200
mininet> h1 /home/p4/src/p4dev-python-venv/bin/python3 send_traffic.py --dst 10.0.0.2 --proto tcp --count 50 --size 100
mininet> h1 /home/p4/src/p4dev-python-venv/bin/python3 send_traffic.py --dst 10.0.0.2 --proto icmp --count 20 --size 98
mininet> h1 /home/p4/src/p4dev-python-venv/bin/python3 send_traffic.py --dst 10.0.0.2 --proto other --count 10 --size 80
```
 
Para la categoría "otros" se usa el protocolo IPv4 número 253, reservado para experimentación.
 
## Qué mide el switch
 
- **Contadores por protocolo:** paquetes y bytes de TCP, UDP, ICMP y otros.
- **Contadores por flujo:** paquetes y bytes por par de IP origen y destino.
- **Registro `proto_bytes`:** bytes acumulados por protocolo.
- **Registro `max_pkt_len`:** tamaño del paquete más grande observado por protocolo.
El controlador muestra estos valores en consola y compara los bytes del contador global con los del registro `proto_bytes`: si coinciden muestra `OK`, y si no, `DIFIERE`.
 
## Verificación de los contadores
 
Las respuestas de los hosts también pasan por el switch y pueden alterar los resultados. Para pruebas con el mínimo de tráfico adicional, la topología se inicia en modo silencioso:
 
```bash
sudo $(which python3) topology.py --quiet
```
 
Este modo bloquea las respuestas UDP, las del protocolo 253 y las respuestas ICMP echo. Después se reinicia el controlador para limpiar los contadores y se ejecuta el tráfico.
 
### Resultados esperados
 
Enviando desde h1 hacia h2 con los comandos de arriba:
 
| Protocolo | Paquetes | Tamaño | Bytes |
|---|---:|---:|---:|
| UDP | 100 | 200 B | 20 000 |
| TCP | 50 | 100 B | 5 000 |
| ICMP | 20 | 98 B | 1 960 |
| Otros | 10 | 80 B | 800 |
| **Total** | **180** | | **27 760** |
 
Para el flujo `10.0.0.1 -> 10.0.0.2` se esperan 180 paquetes y 27 760 bytes, siempre que no se genere tráfico adicional en ese sentido. Los bytes incluyen la cabecera Ethernet.
 
## Detección de flujos elefante
 
Un flujo es elefante cuando sus bytes acumulados superan el umbral del controlador. Cuando esto sucede se muestra una alerta en consola, el flujo aparece con el estado `ELEFANTE` y la primera detección se registra en `elefantes.log`.
 
Por ejemplo, con un umbral de 10 000 bytes:
 
```bash
python3 controller.py --threshold 10000
```
 
También se puede probar con iperf. En la consola de Mininet, se inicia el servidor UDP en h2 y se genera tráfico desde h1:
 
```bash
mininet> h2 iperf -u -s &
mininet> h1 iperf -u -c 10.0.0.2 -b 10M -t 10
```
 
Para esta prueba hay que usar la topología **sin** `--quiet`, ya que el modo silencioso bloquea las respuestas UDP del receptor.
 
## Notas
 
- Se usa ARP estático porque el switch no reenvía tráfico broadcast.
- IPv6 se desactiva para evitar tráfico adicional durante las pruebas.
- Los contadores se leen por Thrift y no por P4Runtime. Esto se discute en la sección 3.3 del informe.
---
 
# Informe
 
El informe de investigación está en [`informe/informe.pdf`](informe/informe.pdf). Cubre la evolución del plano de datos, el lenguaje P4, P4Runtime y el plano de control, y casos de uso (INT, balanceo de carga, seguridad y producción).
 