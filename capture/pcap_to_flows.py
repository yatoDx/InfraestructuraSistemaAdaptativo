"""Convierte capturas pcap (tcpdump en el firewall) en registros de flujo.

Alternativa ligera a Zeek: agrega paquetes por 5-tupla y por intervalos de 5 s
(timeout activo, como NetFlow) para que las transferencias largas se repartan en ventanas.
La dirección "hacia adelante" es la del cliente (el extremo con el puerto más alto).
"""
import sys
from pathlib import Path

import pandas as pd

ACTIVE_S = 5
COLS = ["ts", "dur", "src", "dst", "sport", "dport", "proto", "pkts_fwd", "bytes_fwd",
        "pkts_bwd", "bytes_bwd", "syn", "rst_bwd"]


def pcap_to_flows(path, active_s=ACTIVE_S):
    from scapy.all import IP, TCP, UDP, PcapReader

    flows = {}
    with PcapReader(str(path)) as reader:
        for pkt in reader:
            if IP not in pkt:
                continue
            ip = pkt[IP]
            if TCP in pkt:
                l4, proto = pkt[TCP], 6
            elif UDP in pkt:
                l4, proto = pkt[UDP], 17
            else:
                continue
            ts = float(pkt.time)
            sp, dp = int(l4.sport), int(l4.dport)
            client_side = sp > dp or (sp == dp and ip.src > ip.dst)
            bucket = int(ts // active_s)
            if client_side:
                key = (ip.src, ip.dst, sp, dp, proto, bucket)
            else:
                key = (ip.dst, ip.src, dp, sp, proto, bucket)
            r = flows.get(key)
            if r is None:
                r = flows[key] = {"ts": ts, "last": ts, "pf": 0, "bf": 0, "pb": 0, "bb": 0,
                                  "syn": 0, "rst_bwd": 0}
            r["last"] = ts
            n = int(ip.len)
            flag = int(l4.flags) if proto == 6 else 0
            if client_side:
                r["pf"] += 1
                r["bf"] += n
                if flag & 0x02 and not flag & 0x10:
                    r["syn"] += 1
            else:
                r["pb"] += 1
                r["bb"] += n
                if flag & 0x04:
                    r["rst_bwd"] += 1

    rows = [[v["ts"], v["last"] - v["ts"], k[0], k[1], k[2], k[3], k[4],
             v["pf"], v["bf"], v["pb"], v["bb"], v["syn"], v["rst_bwd"]]
            for k, v in flows.items()]
    return pd.DataFrame(rows, columns=COLS).sort_values("ts").reset_index(drop=True)


if __name__ == "__main__":
    from src.io_utils import write_table

    src = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else src.with_suffix("")
    print(write_table(pcap_to_flows(src), out))
