
/* Lab 2 - Contadores y estadisticas de trafico */

#include <core.p4>
#include <v1model.p4>

const bit<16> TYPE_IPV4  = 0x0800;
const bit<8>  PROTO_ICMP = 1;
const bit<8>  PROTO_TCP  = 6;
const bit<8>  PROTO_UDP  = 17;

// Indices para identificar cada protocolo
const bit<32> IDX_TCP   = 0;
const bit<32> IDX_UDP   = 1;
const bit<32> IDX_ICMP  = 2;
const bit<32> IDX_OTHER = 3;

typedef bit<9>  egressSpec_t;
typedef bit<48> macAddr_t;
typedef bit<32> ip4Addr_t;

// Headers

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
}

struct headers {
    ethernet_t ethernet;
    ipv4_t     ipv4;
}

// Parser

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

// Verificacion de checksum

control MyVerifyChecksum(inout headers hdr, inout metadata meta) {
    apply { }
}

// Ingress

control MyIngress(inout headers hdr,
                  inout metadata meta,
                  inout standard_metadata_t standard_metadata) {

    // Contador de paquetes y bytes por flujo
    direct_counter(CounterType.packets_and_bytes) flow_counter;

    // Contador de paquetes y bytes por protocolo
    counter(4, CounterType.packets_and_bytes) proto_counter;

    // Registros para los bytes acumulados y el paquete mas grande
    register<bit<64>>(4) proto_bytes;
    register<bit<32>>(4) max_pkt_len;

    action drop() {
        mark_to_drop(standard_metadata);
    }

    action forward(egressSpec_t port) {
        standard_metadata.egress_spec = port;
    }

    // Reenvio segun la MAC destino
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

    // Identifica los flujos por IP origen y destino
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

        // Determinar el protocolo del paquete
        if (hdr.ipv4.isValid()) {
            if (hdr.ipv4.protocol == PROTO_TCP) {
                idx = IDX_TCP;
            } else if (hdr.ipv4.protocol == PROTO_UDP) {
                idx = IDX_UDP;
            } else if (hdr.ipv4.protocol == PROTO_ICMP) {
                idx = IDX_ICMP;
            }
        }

        // Actualizar contador del protocolo
        proto_counter.count(idx);

        // Acumular los bytes recibidos
        proto_bytes.read(acc, idx);
        acc = acc + (bit<64>) standard_metadata.packet_length;
        proto_bytes.write(idx, acc);

        // Guardar el mayor tamano de paquete
        max_pkt_len.read(mx, idx);
        if (standard_metadata.packet_length > mx) {
            max_pkt_len.write(idx, standard_metadata.packet_length);
        }

        // Contar el flujo si es IPv4
        if (hdr.ipv4.isValid()) {
            flow_stats.apply();
        }

        // Reenviar segun la tabla MAC
        l2_forward.apply();
    }
}

// Egress

control MyEgress(inout headers hdr,
                 inout metadata meta,
                 inout standard_metadata_t standard_metadata) {
    apply { }
}

// Calculo de checksum

control MyComputeChecksum(inout headers hdr, inout metadata meta) {
    apply { }
}

// Deparser

control MyDeparser(packet_out packet, in headers hdr) {
    apply {
        packet.emit(hdr.ethernet);
        packet.emit(hdr.ipv4);
    }
}

// Switch

V1Switch(
    MyParser(),
    MyVerifyChecksum(),
    MyIngress(),
    MyEgress(),
    MyComputeChecksum(),
    MyDeparser()
) main;
