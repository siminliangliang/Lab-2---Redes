"""
Topología del Lab 1 con 3 routers P4 y 4 hosts, cada uno en su propia subred.

Uso: sudo python3 topology.py
"""
import os
import socket
import subprocess
import sys
import time

from mininet.cli import CLI
from mininet.log import info, setLogLevel
from mininet.net import Mininet
from mininet.node import Switch

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
P4_JSON = os.path.join(BASE_DIR, "build", "router.json")
LOG_DIR = os.path.join(BASE_DIR, "logs")


ROUTERS = ["r1", "r2", "r3"]

# Cada host tiene IP, gateway, router al que se conecta y puerto del router
HOSTS = {
    "h1": {"ip": "10.0.1.1", "gw": "10.0.1.254", "router": "r1", "port": 1},
    "h2": {"ip": "10.0.2.2", "gw": "10.0.2.254", "router": "r2", "port": 1},
    "h3": {"ip": "10.0.3.3", "gw": "10.0.3.254", "router": "r3", "port": 1},
    "h4": {"ip": "10.0.4.4", "gw": "10.0.4.254", "router": "r3", "port": 2},
}

# Enlaces entre routers: de router A en puerto X a router B en puerto X
ROUTER_LINKS = [ ("r1", 2, "r2", 2),
                ("r2", 3, "r3", 3), ]


# Genera MAC de la interfaz port del router
def router_mac(router, port):
    return "00:00:00:%02x:%02x:00" % (int(router[1:]), port)


# Genera MAC del host
def host_mac(host):
    n = int(host[1:])
    return "00:00:00:00:%02x:%02x" % (n, n)


class P4Router(Switch):
    # Switch BMv2 que ejecuta router.p4 en Mininet
    def __init__(self, name, json_path, device_id, thrift_port, **params):
        Switch.__init__(self, name, **params)
        self.json_path = json_path
        self.device_id = device_id
        self.thrift_port = thrift_port

    def start(self, controllers):
        # interfaz de red de Linux de cada puerto de P4
        args = ["simple_switch",
                "--device-id", str(self.device_id),  # id del switch
                "--thrift-port", str(self.thrift_port),
                "--log-console"]
        for port, intf in self.intfs.items():
            if intf.name != "lo":
                args += ["-i", "%d@%s" % (port, intf.name)]
        args.append(self.json_path)
        log = os.path.join(LOG_DIR, "%s.log" % self.name)
        info("Iniciando %s (thrift %d)\n" % (self.name, self.thrift_port))
        # Guardar la salida en un archivo de log
        self.cmd(" ".join(args) + " > " + log + " 2>&1 &")

    # Al cerrar la red, mata el proceso asociado a ese puerto
    def stop(self, deleteIntfs=True):
        self.cmd('pkill -f "thrift-port %d"' % self.thrift_port)
        Switch.stop(self, deleteIntfs)


# Espera a que el switch acepte conexiones en su puerto thrift
def wait_port(port, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
            return True
        except OSError:
            time.sleep(0.3)  # intenta abrir una conexion cada 0.3s
    return False


# Carga las rutas LPM del router desde control plane
def load_routes(router, thrift_port):
    # Busca archivo commands.txt del router
    routes = os.path.join(BASE_DIR, "%s-commands.txt" % router)
    if not os.path.exists(routes):
        info("AVISO: no existe %s, %s descartará todo\n"
             % (os.path.basename(routes), router))
        return
    if not wait_port(thrift_port):  # Espera a que el switch acepte conexion
        info("ERROR: %s no respondió en el puerto %d\n" % (router, thrift_port))
        return
    with open(routes) as f:  # carga las rutas
        subprocess.run(["simple_switch_CLI", "--thrift-port", str(thrift_port)],
                       stdin=f, stdout=subprocess.DEVNULL)
    info("Rutas cargadas en %s\n" % router)


# Construye y arranca la red completa y devuelve objeto Mininet
def build_network():
    if os.geteuid() != 0:
        sys.exit("Uso: sudo python3 topology.py.")
    if not os.path.exists(P4_JSON):
        sys.exit("No existe %s. Compila router.p4." % P4_JSON)
    os.makedirs(LOG_DIR, exist_ok=True)

    net = Mininet(controller=None)   # sin controlador OpenFlow

    # Crea los 3 routers P4
    for r in ROUTERS:
        n = int(r[1:])
        net.addSwitch(r, cls=P4Router, json_path=P4_JSON,
                      device_id=n, thrift_port=9090 + n)

    # Crea 4 hosts, conectados a su router por un puerto fijo
    for h, cfg in HOSTS.items():
        net.addHost(h, ip=cfg["ip"] + "/24", mac=host_mac(h))
        net.addLink(h, cfg["router"], port2=cfg["port"])

    # Enlaces entre routers
    for a, pa, b, pb in ROUTER_LINKS:
        net.addLink(a, b, port1=pa, port2=pb)

    net.start()

    # Configuracion de los hosts
    for h, cfg in HOSTS.items():
        host = net.get(h)
        # Sin offloading para checksums correctos
        host.cmd("ethtool -K %s-eth0 rx off tx off sg off" % h)
        # Sin IPv6 para evitar trafico extra
        host.cmd("sysctl -w net.ipv6.conf.all.disable_ipv6=1")
        # Todo lo que no sea de su subred va al router (gateway)
        host.cmd("ip route add default via %s" % cfg["gw"])
        # Host recibe la MAC de su gateway
        host.setARP(cfg["gw"], router_mac(cfg["router"], cfg["port"]))

    # Cargar las rutas en cada router desde control plane
    for r in ROUTERS:
        load_routes(r, 9090 + int(r[1:]))

    return net

def main():

    net = build_network()
    info("\n Red lista. Prueba con: pingall\n")
    CLI(net)
    net.stop()  # cerrar todo


if __name__ == "__main__":
    setLogLevel("info")
    main()