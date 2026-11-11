# Lab 2: Contadores y estadísticas de tráfico (P4 / BMv2)

Switch P4 con contadores por flujo, contadores globales por protocolo y registers
para el tamaño de paquetes. Un controlador Python (Thrift) los lee cada 5 segundos
y detecta flujos elefante.

> **Estado:** código escrito sin poder compilarlo ni ejecutarlo. Es probable que
> haya que corregir errores de sintaxis o de comandos del CLI en la primera prueba.

## Archivos

| Archivo | Qué hace |
|---|---|
| `p4src/counters.p4` | Programa P4 (v1model): reenvío L2, `flow_stats` con contador directo, contador por protocolo, registers |
| `topology.py` | Mininet: 1 switch BMv2 + 4 hosts (`hN` = `10.0.0.N`, puerto `N`) |
| `controller.py` | Instala tablas, lee contadores cada 5 s, detecta flujos elefante |
| `send_traffic.py` | Genera tráfico con Scapy de tamaño exacto |
| `Makefile` | Compila el P4 a `build/counters.json` |

## Requisitos

`p4c` (`p4c-bm2-ss`), BMv2 (`simple_switch`, `simple_switch_CLI`), Mininet y Scapy.
La VM de `p4lang/tutorials` ya los trae.

## Cómo correrlo (3 terminales)

```bash
# Terminal 1: compilar y levantar la topología
make
sudo python3 topology.py

# Terminal 2: controlador (umbral de elefante en bytes)
python3 controller.py --threshold 1000000

# Terminal 1 (consola de Mininet): generar tráfico
mininet> h1 ping -c 3 h2
mininet> h1 python3 send_traffic.py --dst 10.0.0.2 --proto udp --count 100 --size 200
```

El controlador reinstala las tablas y pone los contadores en cero cada vez que arranca.
Los comandos del CLI que usa son `table_add`, `table_clear`, `counter_read`,
`counter_reset`, `register_read` y `register_reset`.

## Verificar la exactitud de los contadores

El tráfico de respuesta del kernel (RST de TCP, ICMP de puerto inalcanzable, ping)
también pasa por el switch y se cuenta. Para pruebas exactas, silencia al receptor
(ejemplo con h2 como destino):

```
mininet> h2 iptables -A INPUT -p udp -j DROP
mininet> h2 iptables -A INPUT -p 253 -j DROP
mininet> h2 sysctl -w net.ipv4.icmp_echo_ignore_all=1
```

Después reinicia el controlador (pone todo en cero) y envía, por ejemplo:

```
mininet> h1 python3 send_traffic.py --dst 10.0.0.2 --proto udp  --count 100 --size 200
mininet> h1 python3 send_traffic.py --dst 10.0.0.2 --proto tcp  --count 50  --size 100
mininet> h1 python3 send_traffic.py --dst 10.0.0.2 --proto icmp --count 20  --size 98
mininet> h1 python3 send_traffic.py --dst 10.0.0.2 --proto other --count 10 --size 80
```

Esperado en el flujo `10.0.0.1 -> 10.0.0.2`: 180 paquetes y 100·200 + 50·100 + 20·98 + 10·80 = 27 760 bytes.
Por protocolo: UDP 100 paquetes / 20 000 B, TCP 50 / 5 000 B, ICMP 20 / 1 960 B, OTROS 10 / 800 B.
La columna "Bytes (reg)" del controlador debe coincidir con "Bytes" (muestra `OK`).

## Flujos elefante

`--threshold` define los bytes a partir de los cuales un flujo se marca como `ELEFANTE`
en la tabla y se registra una vez en `elefantes.log`. Prueba con iperf:

```
mininet> h2 iperf -u -s &
mininet> h1 iperf -u -c 10.0.0.2 -b 10M -t 10
```

(Para iperf, quita antes las reglas `iptables` de h2.)

## Notas

- Los hosts usan ARP estático e IPv6 apagado, para que no aparezca tráfico ajeno a la prueba.
- Los contadores cuentan en ingress, aun si el paquete luego se descarta (MAC desconocida).
- Los bytes incluyen la cabecera Ethernet.
- Si `simple_switch` no arranca, revisa `/tmp/p4s.s1.log`.
