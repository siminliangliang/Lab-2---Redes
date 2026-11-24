/* Lab 1 - Router IPv4 estático */

#include <core.p4>
#include <v1model.p4>


const bit<16> TYPE_IPV4 = 0x0800;
const bit<8>  PROTO_ICMP = 1;
const bit<8>  ICMP_TIME_EXCEEDED = 11;
const bit<32> ICMP_ERROR_LEN = 70;

typedef bit<9>  egressSpec_t;
typedef bit<48> macAddr_t;
typedef bit<32> ip4Addr_t;

// Headers
header ethernet_t {
    macAddr_t dstAddr;  // MAC del siguiente salto
    macAddr_t srcAddr;  // MAC de la interfaz de salida del router
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

/* Primeros 8 bytes luego del header IPv4 se reenvian, solo se agrega dentro del ICMP de error. */
header original_data8_t {
    bit<64> data;
}

/* Header ICMP Time Exceeded */
header icmp_t {
    bit<8>  icmpType;
    bit<8>  icmpCode;
    bit<16> checksum;
    bit<32> unused;
}

struct metadata {
    /* No se necesita para router estático */
}

struct headers {
    ethernet_t ethernet;
    ipv4_t     ipv4;
    icmp_t     icmp;        // valido en los ICMP que genera el router
    ipv4_t     original_ipv4;  // copia del IPv4 original, para el ICMP
    original_data8_t original_data8;
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
            default:   accept;      // ARP, IPv6 no se revisan
        }
    }

    state parse_ipv4 {
        packet.extract(hdr.ipv4);
        transition parse_original_data8;
    }
    // Extraer 8 bytes despues del encabezado ipv4 para ICMP
    state parse_original_data8 {
        packet.extract(hdr.original_data8);
        transition accept;
    }
}

// Verifica el checksum
control MyVerifyChecksum(inout headers hdr, inout metadata meta) {
    apply { }
}

// Ingress
control MyIngress(inout headers hdr,
                  inout metadata meta,
                  inout standard_metadata_t standard_metadata) {

    // Descarta el paquete
    action drop() {
        mark_to_drop(standard_metadata);
    }

    // Reenvía el paquete
    action ipv4_forward(macAddr_t srcMac, macAddr_t dstMac, egressSpec_t port) {
        standard_metadata.egress_spec = port;
        hdr.ethernet.srcAddr = srcMac;
        hdr.ethernet.dstAddr = dstMac;
        hdr.ipv4.ttl = hdr.ipv4.ttl - 1;  // disminuye ttl
    }

    // Convierte el paquete recibido en un ICMP Time Exceeded, se devuelve al origen

    action send_icmp_time_exceeded(macAddr_t routerMac, ip4Addr_t routerIp) {
        /* Guardar el IPv4 original para citarlo dentro del ICMP */
        hdr.original_ipv4 = hdr.ipv4;

        /* Reescribir el IPv4 externo como respuesta del router */
        hdr.ipv4.version        = 4;
        hdr.ipv4.ihl            = 5;
        hdr.ipv4.diffserv       = 0;
        hdr.ipv4.totalLen       = 56;   // 20 IP + 8 ICMP + 20 IP orig + 8
        hdr.ipv4.identification = 0;
        hdr.ipv4.flags          = 0;
        hdr.ipv4.fragOffset     = 0;
        hdr.ipv4.ttl            = 64;
        hdr.ipv4.protocol       = PROTO_ICMP;
        hdr.ipv4.srcAddr        = routerIp;
        hdr.ipv4.dstAddr        = hdr.original_ipv4.srcAddr;   // vuelve al origen

        hdr.icmp.setValid();
        hdr.icmp.icmpType = ICMP_TIME_EXCEEDED;
        hdr.icmp.icmpCode = 0;   // TTL agotado en transito
        hdr.icmp.unused   = 0;

        // De vuelta hacia donde se envió el paquete
        hdr.ethernet.dstAddr = hdr.ethernet.srcAddr;
        hdr.ethernet.srcAddr = routerMac;

        // Sale por el puerto de entrada
        standard_metadata.egress_spec = standard_metadata.ingress_port;
    }

    // Tabla de enrutamiento LPM
    table ipv4_lpm {
        key = {
            hdr.ipv4.dstAddr: lpm;  // buscar destino en tabla
        }
        actions = {
            ipv4_forward;
            drop;
        }
        size = 1024;
        default_action = drop();    // se descarta si no tiene ruta
    }

    // Generar ICMP de error con MAC e IP de la interfaz por la que se recibio
    table icmp_ttl_exceeded {
        key = {
            standard_metadata.ingress_port: exact;
        }
        actions = {
            send_icmp_time_exceeded;
            drop;
        }
        size = 16;
        default_action = drop();  // se descarta si el puerto esta sin configurar
    }

    apply {
        if (hdr.ipv4.isValid()) {  // verifica si es ipv4
            if (hdr.ipv4.ttl <= 1) {  // si TTL agotado
                // verificar si estan los 8 bytes originales y generar ICMP, si no descartar
                if (hdr.original_data8.isValid()) {
                    icmp_ttl_exceeded.apply();
                } else {
                    drop();
                }
            } else {
                ipv4_lpm.apply();
            }
        } else {
            drop();  // se descarta si no es IPv4
        }
    }
}

// Egress
control MyEgress(inout headers hdr,
                 inout metadata meta,
                 inout standard_metadata_t standard_metadata) {
    apply {
        if (hdr.icmp.isValid()) {
            truncate(ICMP_ERROR_LEN);  // limitar len del paquete a lo necesario
        }
    }
}

// Calcula el Checksum
control MyComputeChecksum(inout headers hdr, inout metadata meta) {
    apply {
        update_checksum(   // Checksum del IPv4
            hdr.ipv4.isValid(),
            { hdr.ipv4.version,
              hdr.ipv4.ihl,
              hdr.ipv4.diffserv,
              hdr.ipv4.totalLen,
              hdr.ipv4.identification,
              hdr.ipv4.flags,
              hdr.ipv4.fragOffset,
              hdr.ipv4.ttl,
              hdr.ipv4.protocol,
              hdr.ipv4.srcAddr,
              hdr.ipv4.dstAddr },
            hdr.ipv4.hdrChecksum,
            HashAlgorithm.csum16);

        update_checksum(   // Checksum del ICMP
            hdr.icmp.isValid(),
            { hdr.icmp.icmpType,
              hdr.icmp.icmpCode,
              hdr.icmp.unused,
              hdr.original_ipv4.version,
              hdr.original_ipv4.ihl,
              hdr.original_ipv4.diffserv,
              hdr.original_ipv4.totalLen,
              hdr.original_ipv4.identification,
              hdr.original_ipv4.flags,
              hdr.original_ipv4.fragOffset,
              hdr.original_ipv4.ttl,
              hdr.original_ipv4.protocol,
              hdr.original_ipv4.hdrChecksum,
              hdr.original_ipv4.srcAddr,
              hdr.original_ipv4.dstAddr,
              hdr.original_data8.data },
            hdr.icmp.checksum,
            HashAlgorithm.csum16);
    }
}

// Deparser, reconstruye el paquete
control MyDeparser(packet_out packet, in headers hdr) {
    apply {
        packet.emit(hdr.ethernet);
        packet.emit(hdr.ipv4);
        packet.emit(hdr.icmp);   // solo si se genero ICMP
        packet.emit(hdr.original_ipv4);
        packet.emit(hdr.original_data8);
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
