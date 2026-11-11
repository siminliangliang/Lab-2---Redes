#!/usr/bin/env python3
"""
Controlador del Lab 2 (Thrift, via simple_switch_CLI).

1. Instala las entradas de las tablas del switch:
     - l2_forward: MAC de hN -> puerto N
     - flow_stats: una entrada por flujo (IP origen, IP destino) entre los 4 hosts
2. Cada --interval segundos (default 5) lee y muestra por consola:
     - contadores globales por protocolo (paquetes y bytes), con el maximo tamano
       de paquete y los bytes del register para cruzar datos
     - contadores directos por flujo
3. Detecta flujos elefante: un flujo cuyos bytes superan --threshold se marca en
   la tabla y se registra en elefantes.log la primera vez que se detecta.

Uso:
    python3 controller.py [--threshold 1000000] [--interval 5] [--thrift-port 9090]
"""

import argparse
import re
import subprocess
import sys
import time

NUM_HOSTS = 4
PROTOS = ["TCP", "UDP", "ICMP", "OTROS"]

T_L2 = "MyIngress.l2_forward"
T_FLOW = "MyIngress.flow_stats"
C_FLOW = "MyIngress.flow_counter"
C_PROTO = "MyIngress.proto_counter"
R_BYTES = "MyIngress.proto_bytes"
R_MAXLEN = "MyIngress.max_pkt_len"


def host_ip(i):
    return "10.0.0.%d" % i


def host_mac(i):
    return "00:00:00:00:00:%02x" % i


def run_cli(commands, thrift_port, cli_bin):
    """Ejecuta una lista de comandos en simple_switch_CLI y devuelve su salida."""
    try:
        res = subprocess.run(
            [cli_bin, "--thrift-port", str(thrift_port)],
            input="\n".join(commands) + "\n",
            capture_output=True, text=True, timeout=30,
        )
    except FileNotFoundError:
        sys.exit("No se encontro '%s'. Usa --cli con la ruta de simple_switch_CLI." % cli_bin)
    out = res.stdout + res.stderr
    if "Could not connect" in out or "Connection refused" in out:
        sys.exit("No hay switch en el puerto Thrift %d. Levanta primero topology.py." % thrift_port)
    return out


def install_entries(thrift_port, cli_bin):
    """Limpia y llena las tablas. Devuelve {(src, dst): handle} de flow_stats."""
    cmds = [
        "table_clear " + T_L2,
        "table_clear " + T_FLOW,
        "counter_reset " + C_PROTO,
        "register_reset " + R_BYTES,
        "register_reset " + R_MAXLEN,
    ]
    for i in range(1, NUM_HOSTS + 1):
        cmds.append("table_add %s MyIngress.forward %s => %d" % (T_L2, host_mac(i), i))

    flows = []
    for s in range(1, NUM_HOSTS + 1):
        for d in range(1, NUM_HOSTS + 1):
            if s != d:
                flows.append((host_ip(s), host_ip(d)))
                cmds.append("table_add %s NoAction %s %s =>" % (T_FLOW, host_ip(s), host_ip(d)))

    out = run_cli(cmds, thrift_port, cli_bin)
    handles = [int(h) for h in re.findall(r"with handle (\d+)", out)]
    expected = NUM_HOSTS + len(flows)
    if len(handles) != expected:
        sys.exit("Se esperaban %d entradas nuevas y se obtuvieron %d.\nSalida del CLI:\n%s"
                 % (expected, len(handles), out))
    flow_handles = handles[NUM_HOSTS:]  # las primeras NUM_HOSTS son de l2_forward
    return dict(zip(flows, flow_handles))


def parse_counter_value(body):
    p = re.search(r"packets=(\d+)", body) or re.search(r"(\d+)\s*packets", body)
    b = re.search(r"bytes=(\d+)", body) or re.search(r"(\d+)\s*bytes", body)
    return (int(p.group(1)) if p else 0, int(b.group(1)) if b else 0)

def read_stats(flow_handles, thrift_port, cli_bin):
    """Lee contadores y registers. Devuelve (flujos, protos, bytes_reg, max_len)."""
    cmds = []
    for handle in flow_handles.values():
        cmds.append("counter_read %s %d" % (C_FLOW, handle))
    for i in range(len(PROTOS)):
        cmds.append("counter_read %s %d" % (C_PROTO, i))
    for i in range(len(PROTOS)):
        cmds.append("register_read %s %d" % (R_BYTES, i))
    for i in range(len(PROTOS)):
        cmds.append("register_read %s %d" % (R_MAXLEN, i))
    out = run_cli(cmds, thrift_port, cli_bin)

    flow_by_handle = {}
    proto_cnt = {}
    for name, idx, body in re.findall(r"(\S+)\[(\d+)\]=\s*(.*(?:bytes|packets).*)", out):
        value = parse_counter_value(body)
        if name.endswith("flow_counter"):
            flow_by_handle[int(idx)] = value
        elif name.endswith("proto_counter"):
            proto_cnt[int(idx)] = value

    regs = {}
    for name, idx, val in re.findall(r"(\S+)\[(\d+)\]=\s*(\d+)[ \t]*(?:\r?\n|$)", out):
        regs[(name.split(".")[-1], int(idx))] = int(val)

    flows = {key: flow_by_handle.get(h, (0, 0)) for key, h in flow_handles.items()}
    protos = [proto_cnt.get(i, (0, 0)) for i in range(len(PROTOS))]
    bytes_reg = [regs.get(("proto_bytes", i), 0) for i in range(len(PROTOS))]
    max_len = [regs.get(("max_pkt_len", i), 0) for i in range(len(PROTOS))]
    return flows, protos, bytes_reg, max_len


def print_stats(flows, protos, bytes_reg, max_len, threshold, elephants, show_all, log_path):
    print("\n=== Estadisticas %s | umbral elefante: %d bytes ===" %
          (time.strftime("%H:%M:%S"), threshold))

    print("\nPor protocolo")
    print("  %-8s %10s %12s %12s %14s" % ("Proto", "Paquetes", "Bytes", "Max pkt (B)", "Bytes (reg)"))
    for i, name in enumerate(PROTOS):
        pkts, byts = protos[i]
        check = "OK" if byts == bytes_reg[i] else "DIFIERE"
        print("  %-8s %10d %12d %12d %14d  %s" % (name, pkts, byts, max_len[i], bytes_reg[i], check))

    print("\nPor flujo (IP origen -> IP destino)")
    print("  %-26s %10s %12s  %s" % ("Flujo", "Paquetes", "Bytes", "Estado"))
    shown = 0
    for (src, dst), (pkts, byts) in sorted(flows.items()):
        if pkts == 0 and not show_all:
            continue
        is_elephant = byts > threshold
        if is_elephant and (src, dst) not in elephants:
            elephants.add((src, dst))
            msg = "%s FLUJO ELEFANTE %s -> %s: %d bytes (umbral %d)" % (time.strftime("%Y-%m-%d %H:%M:%S"), src, dst, byts, threshold)
            print("  [ALERTA] " + msg)
            with open(log_path, "a") as f:
                f.write(msg + "\n")
        state = "ELEFANTE" if is_elephant else ""
        print("  %-26s %10d %12d  %s" % ("%s -> %s" % (src, dst), pkts, byts, state))
        shown += 1
    if shown == 0:
        print("  (sin trafico todavia)")
    sys.stdout.flush()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--thrift-port", type=int, default=9090)
    ap.add_argument("--interval", type=float, default=5.0, help="segundos entre lecturas (default 5)")
    ap.add_argument("--threshold", type=int, default=1000000,
                    help="bytes a partir de los cuales un flujo es elefante (default 1000000)")
    ap.add_argument("--cli", default="simple_switch_CLI", help="binario de simple_switch_CLI")
    ap.add_argument("--all", action="store_true", help="mostrar tambien flujos sin trafico")
    ap.add_argument("--log", default="elefantes.log", help="archivo donde se registran los elefantes")
    args = ap.parse_args()

    print("Instalando entradas en el switch (puerto Thrift %d)..." % args.thrift_port)
    flow_handles = install_entries(args.thrift_port, args.cli)
    print("Listo: %d flujos monitoreados. Leyendo cada %.0f s. Ctrl+C para salir."
          % (len(flow_handles), args.interval))

    elephants = set()
    try:
        while True:
            flows, protos, bytes_reg, max_len = read_stats(flow_handles, args.thrift_port, args.cli)
            print_stats(flows, protos, bytes_reg, max_len, args.threshold,
                        elephants, args.all, args.log)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nControlador detenido.")


if __name__ == "__main__":
    main()
