"""TCP SYN port-scan logic, shared by the MCP server and Jarvis's native tool.

Scoped to private/local IP ranges only (RFC1918, loopback, link-local) --
this is meant for auditing your own LAN devices, not as a general-purpose
internet port scanner.
"""
from __future__ import annotations

import contextlib
import sys
from typing import Optional, TypedDict

from scapy.all import IP, TCP, sr

try:
    from .guard import assert_private  # imported as part of the mcp_servers package
except ImportError:
    from guard import assert_private  # run directly: `python server.py`

SCAN_TIMEOUT_SECONDS = 2

DEFAULT_PORTS = [21, 22, 23, 25, 53, 80, 110, 143, 443, 445, 993, 995, 3389, 8080]

SYN = 0x02
ACK = 0x10
RST = 0x04


class PortResult(TypedDict):
    port: int
    state: str


def port_scan(ip: str, ports: Optional[list[int]] = None) -> dict:
    """SYN-scan `ports` on `ip` and classify each as open/closed/filtered."""
    assert_private(ip)
    ports = ports or DEFAULT_PORTS

    packets = [IP(dst=ip) / TCP(dport=p, flags="S") for p in ports]

    with contextlib.redirect_stdout(sys.stderr):
        answered, _unanswered = sr(packets, timeout=SCAN_TIMEOUT_SECONDS, verbose=False)

    responded: dict[int, str] = {}
    for sent, received in answered:
        port = sent[TCP].dport
        if not received.haslayer(TCP):
            responded[port] = "filtered"
            continue
        flags = received[TCP].flags
        if flags & (SYN | ACK) == (SYN | ACK):
            responded[port] = "open"
        elif flags & RST:
            responded[port] = "closed"
        else:
            responded[port] = "filtered"

    results: list[PortResult] = [
        {"port": p, "state": responded.get(p, "filtered")} for p in sorted(ports)
    ]
    open_ports = [r["port"] for r in results if r["state"] == "open"]

    return {"ip": ip, "results": results, "open_ports": open_ports}
