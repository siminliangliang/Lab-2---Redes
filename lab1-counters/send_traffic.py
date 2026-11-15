
#!/usr/bin/env python3

"""
Genera trafico de prueba desde un host de Mininet usando Scapy.
Permite elegir el protocolo, la cantidad de paquetes y su tamano
para comparar los resultados con los contadores del switch.

Ejemplo:
    h1 python3 send_traffic.py --dst 10.0.0.2 --proto udp --count 100 --size 200
"""

import argparse
import sys

from scapy.all import (ICMP, IP, TCP, UDP, Ether, Raw, get_if_addr, get_if_hwaddr, get_if_list, sendp)


def pick_iface():
    # Buscar una interfaz de red que no sea loopback
    ifaces = [i for i in get_if_list() if i != "lo"]
    if not ifaces:
        sys.exit("No encontre una interfaz de red (ejecutalo dentro de un host de Mininet).")
    return ifaces[0]


def mac_for(ip):
    # Las MAC siguen el mismo formato definido en topology.py
    return "00:00:00:00:00:%02x" % int(ip.split(".")[-1])


def main():
    ap = argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dst", required=True, help="IP destino (10.0.0.N)")
    ap.add_argument("--proto", choices=["tcp", "udp", "icmp", "other"], default="udp")
    ap.add_argument("--count", type=int, default=10, help="cantidad de paquetes")
    ap.add_argument("--size", type=int, default=100, help="tamano de la trama en bytes (con Ethernet)")
    ap.add_argument("--inter", type=float, default=0.0, help="segundos entre paquetes")
    ap.add_argument("--dport", type=int, default=5001, help="puerto destino (tcp/udp)")
    ap.add_argument("--flags", default="R", help="flags TCP (default R: el receptor no responde con RST y no altera los contadores)")
    ap.add_argument("--iface", default=None, help="interfaz de salida (default: la primera no-lo)")
    args = ap.parse_args()

    # Obtener la interfaz y preparar la cabecera Ethernet
    iface = args.iface or pick_iface()
    src_ip = get_if_addr(iface)
    l2 = Ether(src=get_if_hwaddr(iface), dst=mac_for(args.dst))

    # Construir el paquete segun el protocolo seleccionado
    if args.proto == "tcp":
        l3 = IP(src=src_ip, dst=args.dst) / TCP(sport=40000, dport=args.dport, flags=args.flags)
    elif args.proto == "udp":
        l3 = IP(src=src_ip, dst=args.dst) / UDP(sport=40000, dport=args.dport)
    elif args.proto == "icmp":
        l3 = IP(src=src_ip, dst=args.dst) / ICMP()
    else:
        # Protocolo 253 para probar la categoria "otros"
        l3 = IP(src=src_ip, dst=args.dst, proto=253)

    # Completar con bytes vacios hasta alcanzar el tamano solicitado
    base = l2 / l3
    pad = args.size - len(base)
    if pad < 0:
        sys.exit("--size minimo para %s: %d bytes" % (args.proto, len(base)))

    pkt = base / Raw(b"\x00" * pad)
    assert len(pkt) == args.size

    # Enviar los paquetes directamente por Ethernet
    sendp(pkt, iface=iface, count=args.count, inter=args.inter, verbose=False)

    print("Enviados: %d paquetes %s de %d bytes  %s -> %s  (total %d bytes)" %
          (args.count, args.proto.upper(), args.size, src_ip, args.dst, args.count * args.size))
    print("Esperado en el flujo %s -> %s: paquetes=%d, bytes=%d" %
          (src_ip, args.dst, args.count, args.count * args.size))


if __name__ == "__main__":
    main()
