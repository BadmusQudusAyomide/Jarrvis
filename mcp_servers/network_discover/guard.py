"""Shared safety guard: restrict active-probing tools to private/local IPs.

Used by port_scan.py, os_fingerprint.py, and any future tool that sends
probes to a specific host -- keeps this MCP server scoped to auditing your
own network, not arbitrary internet hosts.
"""
from __future__ import annotations

import ipaddress


def assert_private(ip: str) -> None:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError as exc:
        raise ValueError(f"'{ip}' is not a valid IP address") from exc

    if not (addr.is_private or addr.is_loopback or addr.is_link_local):
        raise ValueError(
            f"Refusing to probe {ip}: only private/local addresses are allowed "
            "(this tool is for auditing your own network, not arbitrary hosts)."
        )
