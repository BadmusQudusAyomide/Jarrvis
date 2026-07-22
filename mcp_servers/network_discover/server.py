"""MCP server exposing `network_discover` and `port_scan` tools.

Thin MCP (stdio) wrapper around scan.py / port_scan.py's actual logic,
which is shared with Jarvis's native tools (app/tools/network_tools.py)
so there's one source of truth.

Run directly for local testing:
    python server.py

Communicates over stdio, per the MCP stdio transport.
"""
from __future__ import annotations

from typing import Optional

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

try:
    from .scan import scan_network  # imported as part of the mcp_servers package
    from .port_scan import DEFAULT_PORTS, port_scan as _port_scan
    from .os_fingerprint import os_fingerprint as _os_fingerprint
except ImportError:
    from scan import scan_network  # run directly: `python server.py`
    from port_scan import DEFAULT_PORTS, port_scan as _port_scan
    from os_fingerprint import os_fingerprint as _os_fingerprint

mcp = FastMCP("network-discover")


class Device(BaseModel):
    ip: str = Field(description="Device IPv4 address")
    mac: str = Field(description="Device MAC address")
    manufacturer: Optional[str] = Field(
        default=None, description="Vendor/manufacturer resolved from the MAC OUI, if available"
    )


class NetworkDiscoverResult(BaseModel):
    network: str = Field(description="CIDR range that was scanned")
    devices: list[Device]
    count: int


class PortResult(BaseModel):
    port: int
    state: str = Field(description="'open', 'closed', or 'filtered'")


class PortScanResult(BaseModel):
    ip: str
    results: list[PortResult]
    open_ports: list[int]


class OsFingerprintResult(BaseModel):
    ip: str
    ttl: Optional[int] = None
    guess: Optional[str] = Field(default=None, description="Best-guess OS family")
    estimated_hops: Optional[int] = None
    method: Optional[str] = Field(default=None, description="'icmp' or 'tcp' -- which probe got a response")
    note: Optional[str] = None


@mcp.tool()
def network_discover() -> NetworkDiscoverResult:
    """Discover devices on the local network via an ARP scan.

    Broadcasts ARP "who-has" requests across the host's local /subnet and
    collects replies. Returns each device's IP address, MAC address, and
    manufacturer (when resolvable from the MAC's OUI).

    Requires Npcap (Windows) or libpcap (Linux/macOS) to be installed, and
    typically needs to be run with administrator/root privileges to send
    raw ARP packets.
    """
    result = scan_network()
    return NetworkDiscoverResult(**result)


@mcp.tool()
def port_scan(ip: str, ports: Optional[list[int]] = None) -> PortScanResult:
    """SYN-scan common TCP ports on a device on your local network.

    Restricted to private/local IP addresses (RFC1918, loopback, link-local)
    -- this audits your own devices, not arbitrary internet hosts.

    Args:
        ip: The private IPv4 address to scan (e.g. a device from network_discover).
        ports: Ports to check. Defaults to a common set: 21,22,23,25,53,80,110,
            143,443,445,993,995,3389,8080.
    """
    result = _port_scan(ip, ports or DEFAULT_PORTS)
    return PortScanResult(**result)


@mcp.tool()
def os_fingerprint(ip: str) -> OsFingerprintResult:
    """Best-effort OS guess for a device on your local network.

    Sends an ICMP ping (falling back to a TCP SYN probe if ICMP is
    filtered) and buckets the observed IP TTL against common OS defaults
    (64 = Linux/Unix/macOS, 128 = Windows, 255 = many routers/embedded
    devices). This is a heuristic, not a certainty -- treat "guess" as a
    hint, not a fact. Restricted to private/local IP addresses.
    """
    result = _os_fingerprint(ip)
    return OsFingerprintResult(**result)


if __name__ == "__main__":
    mcp.run(transport="stdio")
