"""Core ARP-scan logic, shared by the MCP server and Jarvis's native tool.

Scans the local /subnet with an ARP request broadcast (via Scapy) and
returns each responding device's IP, MAC, and manufacturer (resolved from
the MAC's OUI). Requires Npcap (Windows) or libpcap (Linux/macOS), and
typically needs to run elevated to send raw packets.
"""
from __future__ import annotations

import contextlib
import ipaddress
import os
import sys
from typing import Optional, TypedDict

import psutil
from scapy.all import ARP, Ether, conf, srp

# Scapy occasionally logs informational text (e.g. non-ASCII vendor names
# while resolving routes) straight to stdout. Under the MCP stdio transport,
# stdout is the JSON-RPC channel, so any stray write there corrupts the
# protocol -- and on Windows' default console codepage it can also raise
# UnicodeEncodeError. Silence Scapy's own verbosity and redirect anything
# else it writes to stderr.
conf.verb = 0
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

SCAN_TIMEOUT_SECONDS = 3


class Device(TypedDict):
    ip: str
    mac: str
    manufacturer: Optional[str]


def local_subnet() -> str:
    """Best-effort discovery of this host's local IPv4 /subnet as CIDR."""
    stats = psutil.net_if_stats()
    for name, addrs in psutil.net_if_addrs().items():
        if name not in stats or not stats[name].isup:
            continue
        for addr in addrs:
            if addr.family.name != "AF_INET":
                continue
            ip = addr.address
            if ip.startswith("127.") or ip.startswith("169.254."):
                continue
            if not addr.netmask:
                continue
            network = ipaddress.ip_network(f"{ip}/{addr.netmask}", strict=False)
            return str(network)

    raise RuntimeError("Could not determine a local IPv4 subnet to scan.")


def lookup_manufacturer(mac: str) -> Optional[str]:
    vendor = conf.manufdb._get_manuf(mac)
    if not vendor or vendor.lower() == mac.lower():
        return None
    return vendor


def scan_network(network: Optional[str] = None) -> dict:
    """Run the ARP scan and return {network, devices, count}.

    Raises RuntimeError with an actionable message on missing subnet,
    missing packet driver, or insufficient privileges.
    """
    network = network or local_subnet()

    try:
        with contextlib.redirect_stdout(sys.stderr):
            answered, _unanswered = srp(
                Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=network),
                timeout=SCAN_TIMEOUT_SECONDS,
                verbose=False,
            )
    except PermissionError as exc:
        raise RuntimeError(
            "Sending raw ARP packets requires elevated privileges. "
            "Run as Administrator (Windows) or root/sudo (Linux/macOS)."
        ) from exc
    except OSError as exc:
        raise RuntimeError(
            f"Failed to send ARP packets: {exc}. Is Npcap (Windows) or libpcap "
            "(Linux/macOS) installed?"
        ) from exc

    devices: list[Device] = [
        {
            "ip": received.psrc,
            "mac": received.hwsrc,
            "manufacturer": lookup_manufacturer(received.hwsrc),
        }
        for _sent, received in answered
    ]

    return {"network": network, "devices": devices, "count": len(devices)}
