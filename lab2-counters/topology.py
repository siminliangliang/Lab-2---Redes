#!/usr/bin/env python3
"""
Topologia del Lab 2: 1 switch P4 (BMv2 simple_switch) + 4 hosts.

    h1 (10.0.0.1) --p1--+
    h2 (10.0.0.2) --p2--+-- s1 (BMv2, thrift 9090)
    h3 (10.0.0.3) --p3--+
    h4 (10.0.0.4) --p4--+

Convencion: el host hN tiene IP 10.0.0.N, MAC 00:00:00:00:00:0N y esta conectado
al puerto N del switch. El controlador (controller.py) usa esa misma convencion
para llenar la tabla l2_forward.

Uso (requiere root):
    sudo python3 topology.py [--json build/counters.json] [--bmv2 simple_switch]
"""

import argparse
import os
import socket
import sys
import time

from mininet.cli import CLI
from mininet.log import info, setLogLevel
from mininet.net import Mininet
from mininet.node import Switch

NUM_HOSTS = 4
THRIFT_PORT = 9090


def wait_for_port(port, timeout=15.0):
    """Espera hasta que el puerto Thrift del switch acepte conexiones."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        try:
            s.connect(("127.0.0.1", port))
            s.close()
            return True
        except OSError:
            s.close()
            time.sleep(0.3)
    return False


class P4Switch(Switch):
    """Switch BMv2 (simple_switch) lanzado como proceso dentro de Mininet."""

    def __init__(self, name, sw_path="simple_switch", json_path=None,
                 thrift_port=THRIFT_PORT, **kwargs):
        Switch.__init__(self, name, **kwargs)
        self.sw_path = sw_path
        self.json_path = json_path
        self.thrift_port = thrift_port
        self.log_file = "/tmp/p4s.%s.log" % name

    def start(self, controllers):
        info("Iniciando %s (log: %s)\n" % (self.name, self.log_file))
        args = [self.sw_path]
        # Los puertos de Mininet: lo es el puerto 0 (tiene IP); el resto sin IP son datos.
        for port, intf in self.intfs.items():
            if not intf.IP():
                args.extend(["-i", "%d@%s" % (port, intf.name)])
                self.cmd("sysctl -w net.ipv6.conf.%s.disable_ipv6=1" % intf.name)
        args.extend(["--thrift-port", str(self.thrift_port)])
        args.append("--log-console")  # util para depurar: ver el log en self.log_file
        args.append(self.json_path)        

        self.cmd(" ".join(args) + " > " + self.log_file + " 2>&1 &")
        if not wait_for_port(self.thrift_port):
            raise RuntimeError("%s no levanto. Revisa %s" % (self.sw_path, self.log_file))

    def stop(self):
        self.cmd("kill %" + os.path.basename(self.sw_path))
        self.cmd("wait")
        self.deleteIntfs()

    def attach(self, intf):
        pass

    def detach(self, intf):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", default="build/counters.json", help="programa P4 compilado (default: build/counters.json)")
    parser.add_argument("--bmv2", default="simple_switch", help="binario de BMv2 (default: simple_switch)")
    parser.add_argument("--quiet", action="store_true",
                        help="modo prueba exacta: los hosts no responden (UDP, proto 253, ping)")
    args = parser.parse_args()


    if os.geteuid() != 0:
        sys.exit("Ejecuta con sudo: sudo python3 topology.py")
    if not os.path.exists(args.json):
        sys.exit("No existe %s. Compila primero con: make" % args.json)

    setLogLevel("info")
    net = Mininet(controller=None, autoSetMacs=False, autoStaticArp=False)

    s1 = net.addSwitch("s1", cls=P4Switch, sw_path=args.bmv2,json_path=args.json, thrift_port=THRIFT_PORT)

    hosts = []
    for i in range(1, NUM_HOSTS + 1):
        h = net.addHost("h%d" % i, ip="10.0.0.%d/24" % i, mac="00:00:00:00:00:%02x" % i)
        net.addLink(h, s1)  # el host i queda en el puerto i del switch
        hosts.append(h)

    net.start()

    # ARP estatico: el switch no reenvia ARP/broadcast, asi que cada host ya conoce
    # la MAC de los demas. Tambien se apaga IPv6 para que no genere trafico "otros".
    for h in hosts:
        for j in range(1, NUM_HOSTS + 1):
            if h.name != "h%d" % j:
                h.setARP("10.0.0.%d" % j, "00:00:00:00:00:%02x" % j)
        h.cmd("sysctl -w net.ipv6.conf.all.disable_ipv6=1")
        h.cmd("sysctl -w net.ipv6.conf.default.disable_ipv6=1")
        h.cmd("sysctl -w net.ipv6.conf.lo.disable_ipv6=1")
        if args.quiet:
            h.cmd("iptables -A INPUT -p udp -j DROP")
            h.cmd("iptables -A INPUT -p 253 -j DROP")
            h.cmd("sysctl -w net.ipv4.icmp_echo_ignore_all=1")


    info("\nTopologia lista. En otra terminal ejecuta: python3 controller.py\n")
    info("Ejemplos en esta consola:  h1 ping -c 3 h2   |   h1 python3 send_traffic.py --help\n\n")
    CLI(net)
    net.stop()


if __name__ == "__main__":
    main()
