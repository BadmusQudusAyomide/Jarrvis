"""Lightweight OS fingerprinting via TTL heuristics, shared by the MCP
server and Jarvis's native tool.

Scoped to private/local IP ranges only, same as port_scan.py -- this is
for identifying your own devices, not arbitrary hosts.

This is a heuristic, not a fingerprint database (like nmap's -O): it
buckets the observed IP TTL against the handful of common OS defaults
(64 = Linux/Unix/macOS, 128 = Windows, 255 = many routers/embedded
devices) and reports the estimated hop count to that default. On a
single-hop LAN the estimate is usually exact; treat it as a best guess,
not a certainty.
"""
from __future__ import annotations

import contextlib
import sys
from typing import Optional

from scapy.all import ICMP, IP, TCP, sr1

try:
    from .guard import assert_private  # imported as part of the mcp_servers package
except ImportError:
    from guard import assert_private  # run directly: `python server.py`

PROBE_TIMEOUT_SECONDS = 2
FALLBACK_TCP_PORT = 80

# (ttl_ceiling, os_guess) -- observed TTL is bucketed against the closest
# common default at or above it.
_TTL_BUCKETS = [
    (64, "Linux/Unix (or macOS)"),
    (128, "Windows"),
    (255, "Network device (router/switch/embedded OS)"),
]


def _guess_os_from_ttl(ttl: int) -> tuple[str, int]:
    for ceiling, label in _TTL_BUCKETS:
        if ttl <= ceiling:
            return label, ceiling - ttl
    return "Unknown", -1


def os_fingerprint(ip: str) -> dict:
    """Best-effort OS guess for `ip` based on observed IP TTL."""
    assert_private(ip)

    with contextlib.redirect_stdout(sys.stderr):
        resp = sr1(IP(dst=ip) / ICMP(), timeout=PROBE_TIMEOUT_SECONDS, verbose=False)
        method = "icmp"
        if resp is None:
            resp = sr1(
                IP(dst=ip) / TCP(dport=FALLBACK_TCP_PORT, flags="S"),
                timeout=PROBE_TIMEOUT_SECONDS,
                verbose=False,
            )
            method = "tcp"

    if resp is None:
        return {
            "ip": ip,
            "ttl": None,
            "guess": None,
            "estimated_hops": None,
            "method": None,
            "note": "No response to ICMP or TCP probes (device may be off, unreachable, or filtering probes).",
        }

    ttl = resp.ttl
    guess, hops = _guess_os_from_ttl(ttl)

    return {
        "ip": ip,
        "ttl": ttl,
        "guess": guess,
        "estimated_hops": hops,
        "method": method,
        "note": None,
    }
