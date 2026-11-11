#!/usr/bin/env python3
"""
Generador de trafico de prueba con Scapy (se ejecuta DENTRO de un host de Mininet).

Envia --count paquetes de un tamano EXACTO (--size bytes de trama, incluyendo
Ethernet) para poder comparar con los contadores del switch.

Ejemplos (en la consola de Mininet):
    h1 python3 send_traffic.py --dst 10.0.0.2 --proto udp  --count 100 --size 200
    h1 python3 send_traffic.py --dst 10.0.0.3 --proto tcp  --count 50  --size 100
    h1 python3 send_traffic.py --dst 10.0.0.4 --proto icmp --count 20  --size 98
    h1 python3 send_traffic.py --dst 10.0.0.2 --proto other --count 10 --size 80

Convencion de MAC: la MAC de 10.0.0.N es 00:00:00:00:00:0N (igual que topology.py).
"""

import argparse
import sys

from scapy.all import (ICMP, IP, TCP, UDP, Ether, Raw, get_if_addr, get_if_hwaddr,
                       get_if_list, sendp)


def pick_iface():
    ifaces = [i for i in get_if_list() if i != "lo"]
    if not ifaces:
        sys.exit("No encontre una interfaz de red (ejecutalo dentro de un host de Mininet).")
    return ifaces[0]


def mac_for(ip):
    return "00:00:00:00:00:%02x" % int(ip.split(".")[-1])


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dst", required=True, help="IP destino (10.0.0.N)")
    ap.add_argument("--proto", choices=["tcp", "udp", "icmp", "other"], default="udp")
    ap.add_argument("--count", type=int, default=10, help="cantidad de paquetes")
    ap.add_argument("--size", type=int, default=100, help="tamano de la trama en bytes (con Ethernet)")
    ap.add_argument("--inter", type=float, default=0.0, help="segundos entre paquetes")
    ap.add_argument("--dport", type=int, default=5001, help="puerto destino (tcp/udp)")
    ap.add_argument("--flags", default="R", help="flags TCP (default R: el receptor no responde con RST y no altera los contadores)")
    ap.add_argument("--iface", default=None, help="interfaz de salida (default: la primera no-lo)")
    args = ap.parse_args()

    iface = args.iface or pick_iface()
    src_ip = get_if_addr(iface)
    l2 = Ether(src=get_if_hwaddr(iface), dst=mac_for(args.dst))

    if args.proto == "tcp":
        l3 = IP(src=src_ip, dst=args.dst) / TCP(sport=40000, dport=args.dport, flags=args.flags)
    elif args.proto == "udp":
        l3 = IP(src=src_ip, dst=args.dst) / UDP(sport=40000, dport=args.dport)
    elif args.proto == "icmp":
        l3 = IP(src=src_ip, dst=args.dst) / ICMP()
    else:  # otro protocolo IPv4 (253: reservado para experimentacion)
        l3 = IP(src=src_ip, dst=args.dst, proto=253)

    base = l2 / l3
    pad = args.size - len(base)
    if pad < 0:
        sys.exit("--size minimo para %s: %d bytes" % (args.proto, len(base)))
    pkt = base / Raw(b"\x00" * pad)
    assert len(pkt) == args.size

    sendp(pkt, iface=iface, count=args.count, inter=args.inter, verbose=False)

    print("Enviados: %d paquetes %s de %d bytes  %s -> %s  (total %d bytes)" %
          (args.count, args.proto.upper(), args.size, src_ip, args.dst, args.count * args.size))
    print("Esperado en el flujo %s -> %s: paquetes=%d, bytes=%d" %
          (src_ip, args.dst, args.count, args.count * args.size))


if __name__ == "__main__":
    main()
