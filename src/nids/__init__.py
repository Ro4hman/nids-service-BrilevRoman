"""Пакет сервиса обнаружения сетевых вторжений (NIDS)."""

__version__ = "0.1.0"

PROTOCOLS = ["tcp", "udp", "icmp"]
SERVICES = ["dns", "ftp", "http", "https", "smtp", "ssh"]

FEATURES = [
    "src_port",
    "dst_port",
    "duration_ms",
    "bytes_in",
    "bytes_out",
    "packets",
    "proto_code",
    "service_code",
]


def encode(row: dict) -> list[float]:
    """Преобразует запись датасета (dict из csv.DictReader) в вектор признаков."""
    return [
        float(row["src_port"]),
        float(row["dst_port"]),
        float(row["duration_ms"]),
        float(row["bytes_in"]),
        float(row["bytes_out"]),
        float(row["packets"]),
        float(PROTOCOLS.index(row["protocol"])),
        float(SERVICES.index(row["service"])),
    ]
