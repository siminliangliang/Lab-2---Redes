#!/usr/bin/env python3
"""
Pruebas del Lab 1 Router IPv4 en P4

Levanta la red de topology.py y ejecuta 4 pruebas:
  1. Conectividad con ping entre los 4 hosts.
  2. TTL y MAC, envío de un paquete TTL=64 con Scapy y se captura en el destino 
                para verificar TTL decrementado, MACs reescritas y checksum.
  3. TTL agotado, con un paquete TTL=1 llega al primer router pero no sale.
  4. Sin ruta, con un paquete a 10.0.9.9 llega al router pero no sale.

Uso desde cualquier carpeta:
    sudo <python del entorno P4> tests/router_tests.py | tee tests/results.txt

Rol segun el primer argumento:
  sin argumentos: se ejecutan las pruebas
  --sniff : corre dentro de un host/router y captura 1 paquete (Scapy)
  --send  : corre dentro de un host y envía 1 paquete (Scapy)
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

PY = sys.executable
SELF = os.path.abspath(__file__)
UDP_PORT = 5555    # puerto UDP de los paquetes de prueba
SNIFF_TIMEOUT = 5  # segundos de espera entre cada captura


# ROL 1 y 2: código que se ejecuta dentro de los hosts con Scapy
def role_sniff(iface, bpf, out, timeout):
    """Captura 1 paquete en 'iface' y escribe resumen en archivo out.
    """
    from scapy.all import IP, Ether, sniff
    pkts = sniff(iface=iface, filter=bpf, count=1, timeout=int(timeout))
    if not pkts:
        line = "NONE"
    else:
        p = pkts[0]
        ip = p[IP]
        shown = ip.chksum
        recalc = IP(bytes(ip))
        del recalc.chksum   # Scapy lo recalcula al serializar
        ok = IP(bytes(recalc)).chksum == shown  # verifica si checksum recibido es valido
        line = "ttl=%d smac=%s dmac=%s chk=%s" % (
            ip.ttl, p[Ether].src, p[Ether].dst, "OK" if ok else "BAD")
    with open(out + ".tmp", "w") as f:          # escritura atómica
        f.write(line)
    os.rename(out + ".tmp", out)


def role_send(iface, smac, dmac, sip, dip, ttl):
    """Envía 1 paquete UDP con el TTL indicado, directo al MAC del gateway."""
    from scapy.all import IP, UDP, Ether, sendp
    pkt = (Ether(src=smac, dst=dmac) /
           IP(src=sip, dst=dip, ttl=int(ttl)) /
           UDP(sport=4444, dport=UDP_PORT) / b"p4lab")
    sendp(pkt, iface=iface, verbose=False)


# ROL 3: ejecucion de pruebas
def start_sniffer(node, tag, iface, dst_ip):
    """Lanza una captura dentro de node y devuelve el archivo."""
    out = "/tmp/p4lab_%s.txt" % tag
    node.cmd("rm -f %s" % out)
    bpf = "udp and dst port %d and dst host %s" % (UDP_PORT, dst_ip)
    node.cmd('%s %s --sniff %s "%s" %s %d > /dev/null 2>&1 &'
             % (PY, SELF, iface, bpf, out, SNIFF_TIMEOUT))
    return out

# Al terminar el sniffer, devuelve el resumen
def read_result(out):
    end = time.time() + SNIFF_TIMEOUT + 6
    while time.time() < end:
        if os.path.exists(out):
            return open(out).read().strip()
        time.sleep(0.3)
    return "ERROR (sin respuesta del sniffer)"

# Envía un paquete desde origen hacia destino con ttl y captura en sniffers
def probe(net, src, dst_ip, ttl, sniffers):
    from topology import HOSTS, host_mac, router_mac
    h = net.get(src)
    cfg = HOSTS[src]
    outs = {}
    for i, (nodename, iface) in enumerate(sniffers):
        outs[(nodename, iface)] = start_sniffer(net.get(nodename),
                                                "%s_%d" % (src, i), iface, dst_ip)
    time.sleep(2)                                # Scapy tarda en arrancar
    h.cmd("%s %s --send %s-eth0 %s %s %s %s %d" % (
        PY, SELF, src, host_mac(src), router_mac(cfg["router"], cfg["port"]),
        cfg["ip"], dst_ip, ttl))
    return {k: read_result(v) for k, v in outs.items()}


class Report:
    """Cuenta PASS/FAIL e imprime cada verificación."""
    def __init__(self):
        self.fails = 0

    def check(self, ok, text):
        print("  [%s] %s" % ("PASS" if ok else "FAIL", text))
        if not ok:
            self.fails += 1


# Prueba 1: ping entre todos los hosts
def test_ping(net, rep):
    from topology import HOSTS
    print("\n== Prueba 1: ping entre todos los hosts")
    for a in HOSTS:
        for b in HOSTS:
            if a == b:
                continue
            out = net.get(a).cmd("ping -c 1 -W 2 %s" % HOSTS[b]["ip"])
            rep.check(" 1 received" in out,
                      "%s -> %s (%s)" % (a, b, HOSTS[b]["ip"]))



# Prueba 2: verifica decremento de TTL, MAC reescrita y checksum

# host origen, host destino, num routers por los que pasa
TTL_CASES = [("h1", "h2", 2), ("h1", "h4", 3), ("h2", "h3", 2), ("h3", "h4", 1)]

def test_ttl_mac(net, rep):
    from topology import HOSTS, host_mac, router_mac
    print("\n== Prueba 2: decremento TTL, MAC reescrita y checksum (enviado TTL=64)")
    for src, dst, hops in TTL_CASES:
        d = HOSTS[dst]
        res = probe(net, src, d["ip"], 64, [(dst, "%s-eth0" % dst)])
        line = res[(dst, "%s-eth0" % dst)]
        print("  %s -> %s (%d routers): capturado en %s -> %s" % (src, dst, hops, dst, line))
        if line.startswith("ttl="):
            f = dict(x.split("=") for x in line.split())
            rep.check(int(f["ttl"]) == 64 - hops,
                      "TTL llegó %s, esperado %d" % (f["ttl"], 64 - hops))
            rep.check(f["smac"] == router_mac(d["router"], d["port"]),
                      "MAC origen = router %s (%s)" % (d["router"], f["smac"]))
            rep.check(f["dmac"] == host_mac(dst), "MAC destino = %s (%s)" % (dst, f["dmac"]))
            rep.check(f["chk"] == "OK", "checksum IPv4 válido")
        else:
            rep.check(False, "el paquete no llegó a %s" % dst)


# Prueba 3: si TTL = 1 se descarta
def test_ttl_expired(net, rep):
    from topology import HOSTS
    print("\n== Prueba 3: Descartar TTL=1 en r1")
    res = probe(net, "h1", HOSTS["h4"]["ip"], 1,
                [("r1", "r1-eth1"), ("h4", "h4-eth0")])
    rep.check(res[("r1", "r1-eth1")].startswith("ttl=1"),
              "el paquete TTL=1 llegó a r1 (%s)" % res[("r1", "r1-eth1")])
    rep.check(res[("h4", "h4-eth0")] == "NONE", "no llegó a h4 (descartado)")


# Prueba 4: descarta paquete sin ruta (default drop)
NO_ROUTE_IP = "10.0.9.9"  # ninguna tabla tiene ruta para 10.0.9.0/24

def test_noRoute(net, rep):
    print("\n== Prueba 4: Descartar destino (%s) sin ruta" % NO_ROUTE_IP)
    res = probe(net, "h1", NO_ROUTE_IP, 64,
                [("r1", "r1-eth1"), ("r1", "r1-eth2")])
    rep.check(res[("r1", "r1-eth1")].startswith("ttl=64"),
              "el paquete llegó a r1 por r1-eth1 (%s)" % res[("r1", "r1-eth1")])
    rep.check(res[("r1", "r1-eth2")] == "NONE",
              "r1 no lo reenvió por r1-eth2 (default drop)")
    out = net.get("h1").cmd("ping -c 2 -W 1 %s" % NO_ROUTE_IP)
    rep.check("100% packet loss" in out, "ping a %s: 100%% de pérdida" % NO_ROUTE_IP)


def main():
    from mininet.log import setLogLevel
    from topology import build_network
    setLogLevel("warning")
    net = build_network()
    rep = Report()
    try:
        test_ping(net, rep)
        test_ttl_mac(net, rep)
        test_ttl_expired(net, rep)
        test_noRoute(net, rep)
    finally:
        net.stop()
    print("\n== RESULTADO: %s ==" % ("TODO OK" if rep.fails == 0
                                    else "%d verificación(es) FALLARON" % rep.fails))
    sys.exit(0 if rep.fails == 0 else 1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--sniff":
        role_sniff(*sys.argv[2:6])
    elif len(sys.argv) > 1 and sys.argv[1] == "--send":
        role_send(*sys.argv[2:8])
    else:
        main()