/* -*- P4_16 -*- */
/*
 * Lab 2: Contadores y estadisticas de trafico (BMv2, arquitectura v1model)
 *
 * Funcionalidad:
 *   - Reenvio L2 por MAC destino (tabla l2_forward, llenada por el controlador).
 *   - Contadores directos por flujo (IP origen + IP destino): tabla flow_stats.
 *   - Contadores globales por protocolo: TCP, UDP, ICMP, otros.
 *   - Registro del tamano de paquetes con registers:
 *       proto_bytes -> bytes acumulados por protocolo (para cruzar con el contador)
 *       max_pkt_len -> paquete mas grande visto por protocolo
 *
 * Nota: los contadores se actualizan en ingress, antes de decidir el reenvio,
 * por lo que tambien cuentan paquetes que luego se descartan.
 */

#include <core.p4>
#include <v1model.p4>

const bit<16> TYPE_IPV4  = 0x0800;
const bit<8>  PROTO_ICMP = 1;
const bit<8>  PROTO_TCP  = 6;
const bit<8>  PROTO_UDP  = 17;

/* Indices de los contadores/registros globales por protocolo */
const bit<32> IDX_TCP   = 0;
const bit<32> IDX_UDP   = 1;
const bit<32> IDX_ICMP  = 2;
const bit<32> IDX_OTHER = 3;

typedef bit<9>  egressSpec_t;
typedef bit<48> macAddr_t;
typedef bit<32> ip4Addr_t;

/*************************************************************************
 *********************** H E A D E R S  **********************************
 *************************************************************************/

header ethernet_t {
    macAddr_t dstAddr;
    macAddr_t srcAddr;
    bit<16>   etherType;
}

header ipv4_t {
    bit<4>    version;
    bit<4>    ihl;
    bit<8>    diffserv;
    bit<16>   totalLen;
    bit<16>   identification;
    bit<3>    flags;
    bit<13>   fragOffset;
    bit<8>    ttl;
    bit<8>    protocol;
    bit<16>   hdrChecksum;
    ip4Addr_t srcAddr;
    ip4Addr_t dstAddr;
}

struct metadata {
    /* vacio */
}

struct headers {
    ethernet_t ethernet;
    ipv4_t     ipv4;
}

/*************************************************************************
 *********************** P A R S E R  ************************************
 *************************************************************************/

parser MyParser(packet_in packet,
                out headers hdr,
                inout metadata meta,
                inout standard_metadata_t standard_metadata) {

    state start {
        transition parse_ethernet;
    }

    state parse_ethernet {
        packet.extract(hdr.ethernet);
        transition select(hdr.ethernet.etherType) {
            TYPE_IPV4: parse_ipv4;
            default:   accept;
        }
    }

    state parse_ipv4 {
        packet.extract(hdr.ipv4);
        transition accept;
    }
}

/*************************************************************************
 ************   C H E C K S U M    V E R I F I C A T I O N   *************
 *************************************************************************/

control MyVerifyChecksum(inout headers hdr, inout metadata meta) {
    apply { }
}

/*************************************************************************
 ************** I N G R E S S   P R O C E S S I N G   ********************
 *************************************************************************/

control MyIngress(inout headers hdr,
                  inout metadata meta,
                  inout standard_metadata_t standard_metadata) {

    /* Contador directo: se asocia a la tabla flow_stats (un contador por entrada) */
    direct_counter(CounterType.packets_and_bytes) flow_counter;

    /* Contador global por protocolo: 4 posiciones (TCP, UDP, ICMP, otros) */
    counter(4, CounterType.packets_and_bytes) proto_counter;

    /* Registers para el tamano de paquetes */
    register<bit<64>>(4) proto_bytes;   /* bytes acumulados por protocolo */
    register<bit<32>>(4) max_pkt_len;   /* paquete mas grande por protocolo */

    action drop() {
        mark_to_drop(standard_metadata);
    }

    action forward(egressSpec_t port) {
        standard_metadata.egress_spec = port;
    }

    /* Reenvio L2 por MAC destino. Lo que no coincide se descarta. */
    table l2_forward {
        key = {
            hdr.ethernet.dstAddr: exact;
        }
        actions = {
            forward;
            drop;
        }
        size = 16;
        default_action = drop();
    }

    /* Un flujo = (IP origen, IP destino). El controlador agrega una entrada por flujo
     * y lee su contador directo usando el handle de la entrada. */
    table flow_stats {
        key = {
            hdr.ipv4.srcAddr: exact;
            hdr.ipv4.dstAddr: exact;
        }
        actions = {
            NoAction;
        }
        counters = flow_counter;
        size = 64;
        default_action = NoAction();
    }

    apply {
        bit<32> idx = IDX_OTHER;
        bit<64> acc;
        bit<32> mx;

        /* 1. Clasificar por protocolo (todo lo que no es TCP/UDP/ICMP, incluido
         *    el trafico no IPv4, cae en "otros") */
        if (hdr.ipv4.isValid()) {
            if (hdr.ipv4.protocol == PROTO_TCP) {
                idx = IDX_TCP;
            } else if (hdr.ipv4.protocol == PROTO_UDP) {
                idx = IDX_UDP;
            } else if (hdr.ipv4.protocol == PROTO_ICMP) {
                idx = IDX_ICMP;
            }
        }

        /* 2. Contador global por protocolo */
        proto_counter.count(idx);

        /* 3. Tamano de paquetes en registers (packet_length incluye Ethernet) */
        proto_bytes.read(acc, idx);
        acc = acc + (bit<64>) standard_metadata.packet_length;
        proto_bytes.write(idx, acc);

        max_pkt_len.read(mx, idx);
        if (standard_metadata.packet_length > mx) {
            max_pkt_len.write(idx, standard_metadata.packet_length);
        }

        /* 4. Contador directo por flujo (solo paquetes IPv4) */
        if (hdr.ipv4.isValid()) {
            flow_stats.apply();
        }

        /* 5. Reenvio */
        l2_forward.apply();
    }
}

/*************************************************************************
 ****************  E G R E S S   P R O C E S S I N G   *******************
 *************************************************************************/

control MyEgress(inout headers hdr,
                 inout metadata meta,
                 inout standard_metadata_t standard_metadata) {
    apply { }
}

/*************************************************************************
 *************   C H E C K S U M    C O M P U T A T I O N   **************
 *************************************************************************/

control MyComputeChecksum(inout headers hdr, inout metadata meta) {
    apply { }
}

/*************************************************************************
 ***********************  D E P A R S E R  *******************************
 *************************************************************************/

control MyDeparser(packet_out packet, in headers hdr) {
    apply {
        packet.emit(hdr.ethernet);
        packet.emit(hdr.ipv4);
    }
}

/*************************************************************************
 ***********************  S W I T C H  ***********************************
 *************************************************************************/

V1Switch(
    MyParser(),
    MyVerifyChecksum(),
    MyIngress(),
    MyEgress(),
    MyComputeChecksum(),
    MyDeparser()
) main;
