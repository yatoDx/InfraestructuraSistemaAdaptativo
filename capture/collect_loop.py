"""Colector: procesa periódicamente los pcap cerrados por el firewall y deja los flujos en /data/flows."""
import os
import time
from pathlib import Path

from capture.pcap_to_flows import pcap_to_flows
from src.io_utils import write_table

DATA = Path(os.environ.get("DATA_DIR", "/data"))
SETTLE_S = 90  # un pcap más viejo que esto ya no lo está escribiendo tcpdump


def processed(base):
    return base.with_suffix(".parquet").exists() or base.with_suffix(".csv").exists()


def main():
    pcap_dir, out_dir = DATA / "pcap", DATA / "flows"
    out_dir.mkdir(parents=True, exist_ok=True)
    print("colector activo, vigilando", pcap_dir, flush=True)
    while True:
        for p in sorted(pcap_dir.glob("fw_*.pcap")):
            base = out_dir / f"flows_{p.stem}"
            if processed(base) or time.time() - p.stat().st_mtime < SETTLE_S:
                continue
            try:
                df = pcap_to_flows(p)
                write_table(df, base)
                print(f"{p.name}: {len(df)} flujos", flush=True)
            except Exception as e:  # pcap truncado u otro problema: seguir con el siguiente
                print(f"{p.name}: error {e}", flush=True)
        time.sleep(30)


if __name__ == "__main__":
    main()
