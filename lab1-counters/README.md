
# Lab 2: Contadores y estadísticas de tráfico (P4 / BMv2)

Este laboratorio implementa un switch P4 que permite recopilar estadísticas de tráfico mediante contadores por flujo, contadores globales por protocolo y registros para almacenar información sobre el tamaño de los paquetes.

Se utiliza un controlador en Python que se comunica con el switch mediante Thrift para consultar las estadísticas cada 5 segundos y detectar flujos elefante.

## Archivos

| Archivo | Descripción |
|---|---|
| `p4src/counters.p4` | Programa P4 que implementa el reenvío L2, los contadores por flujo y protocolo, y los registros de tamaño de paquetes. |
| `topology.py` | Crea la topología en Mininet con un switch BMv2 y cuatro hosts. |
| `controller.py` | Configura las tablas del switch, consulta los contadores y detecta flujos elefante. |
| `send_traffic.py` | Genera tráfico TCP, UDP, ICMP y otros protocolos utilizando Scapy. |
| `Makefile` | Compila el programa P4 y genera `build/counters.json`. |

## Requisitos

Para ejecutar el laboratorio se necesita:

- Compilador P4 (`p4c-bm2-ss`).
- BMv2 (`simple_switch` y `simple_switch_CLI`).
- Mininet.
- Python 3.
- Scapy.

Se puede utilizar la máquina virtual de P4 Tutorials, que incluye las herramientas necesarias.

## Topología

La red está formada por un switch P4 y cuatro hosts conectados directamente.

```text
h1 (10.0.0.1) --- p1 --+
h2 (10.0.0.2) --- p2 --+
                       +--- s1 (BMv2)
h3 (10.0.0.3) --- p3 --+
h4 (10.0.0.4) --- p4 --+
```

Cada host tiene una IP `10.0.0.N`, una MAC `00:00:00:00:00:0N` y está conectado al puerto N del switch.

El controlador utiliza estas direcciones para configurar la tabla de reenvío L2.

## Cómo ejecutarlo

### 1. Compilar el programa P4

Desde la carpeta del laboratorio:

```bash
make
```

Esto genera el archivo `build/counters.json`, que será utilizado por BMv2.

### 2. Iniciar la topología

```bash
sudo python3 topology.py
```

Se abrirá la consola de Mininet con los cuatro hosts y el switch.

### 3. Ejecutar el controlador

En otra terminal:

```bash
python3 controller.py --threshold 1000000
```

El controlador instala las entradas de las tablas y consulta los contadores cada 5 segundos.

El parámetro `--threshold` indica la cantidad de bytes que debe superar un flujo para considerarse elefante.

También se puede cambiar el intervalo de lectura:

```bash
python3 controller.py --threshold 1000000 --interval 5
```

### 4. Generar tráfico

Desde la consola de Mininet se pueden enviar paquetes de distintos protocolos.

Tráfico UDP:

```bash
h1 python3 send_traffic.py --dst 10.0.0.2 --proto udp --count 100 --size 200
```

Tráfico TCP:

```bash
h1 python3 send_traffic.py --dst 10.0.0.2 --proto tcp --count 50 --size 100
```

Tráfico ICMP:

```bash
h1 python3 send_traffic.py --dst 10.0.0.2 --proto icmp --count 20 --size 98
```

Otros protocolos:

```bash
h1 python3 send_traffic.py --dst 10.0.0.2 --proto other --count 10 --size 80
```

Para la categoría "otros" se utiliza el protocolo IPv4 número 253, reservado para experimentación.

## Contadores y estadísticas

El switch recopila las siguientes estadísticas:

- **Contadores por protocolo:** cantidad de paquetes y bytes TCP, UDP, ICMP y otros.
- **Contadores por flujo:** paquetes y bytes según la IP de origen y destino.
- **Registro `proto_bytes`:** bytes acumulados por protocolo.
- **Registro `max_pkt_len`:** tamaño del paquete más grande observado para cada protocolo.

El controlador muestra estos valores en consola y compara los bytes del contador global con los del registro `proto_bytes`.

Cuando ambos valores coinciden, muestra `OK`. En caso contrario, muestra `DIFIERE`.

## Verificación de los contadores

Las respuestas generadas por los hosts también pueden pasar por el switch y alterar los resultados.

Para realizar pruebas con menos tráfico adicional se puede iniciar la topología utilizando:

```bash
sudo python3 topology.py --quiet
```

Este modo bloquea las respuestas UDP, del protocolo 253 y las respuestas a solicitudes ICMP echo.

También se puede configurar manualmente el host receptor desde Mininet:

```bash
h2 iptables -A INPUT -p udp -j DROP
h2 iptables -A INPUT -p 253 -j DROP
h2 sysctl -w net.ipv4.icmp_echo_ignore_all=1
```

Después de configurar el entorno, se puede reiniciar el controlador para limpiar los contadores y ejecutar las pruebas.

### Resultados esperados

Enviando desde h1 hacia h2:

| Protocolo | Paquetes | Tamaño | Bytes |
|---|---:|---:|---:|
| UDP | 100 | 200 B | 20 000 |
| TCP | 50 | 100 B | 5 000 |
| ICMP | 20 | 98 B | 1 960 |
| Otros | 10 | 80 B | 800 |
| **Total** | **180** | | **27 760** |

Para el flujo `10.0.0.1 -> 10.0.0.2` se esperan 180 paquetes y 27 760 bytes, siempre que no se genere tráfico adicional en ese sentido.

Los bytes incluyen la cabecera Ethernet.

## Detección de flujos elefante

Un flujo se considera elefante cuando la cantidad de bytes acumulados supera el umbral definido en el controlador.

Cuando esto sucede:

- Se muestra una alerta en consola.
- El flujo aparece con el estado `ELEFANTE`.
- Se registra la primera detección en `elefantes.log`.

Por ejemplo, para utilizar un umbral de 10 000 bytes:

```bash
python3 controller.py --threshold 10000
```

También se puede generar tráfico con iperf para probar la detección.

En Mininet, iniciar el servidor UDP en h2:

```bash
h2 iperf -u -s &
```

Generar tráfico desde h1:

```bash
h1 iperf -u -c 10.0.0.2 -b 10M -t 10
```

Para esta prueba se debe utilizar la topología sin `--quiet` y sin las reglas de iptables que bloquean UDP en el receptor.

## Notas

- Se utiliza ARP estático porque el switch no tiene configurado el reenvío de tráfico broadcast.
- IPv6 se desactiva para evitar tráfico adicional durante las pruebas.
- Los contadores se actualizan en ingress, por lo que también contabilizan paquetes que después son descartados.
- Los contadores por flujo utilizan las direcciones IP de origen y destino.
- El controlador limpia las tablas y reinicia los contadores globales y registros al comenzar.
- Si BMv2 no inicia correctamente, se puede revisar el archivo `/tmp/p4s.s1.log`.
- Para detener el controlador se utiliza `Ctrl+C`.
