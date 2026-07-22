import logging

from app.tools.base import BaseTool, ToolParameter, ToolSchema
from mcp_servers.network_discover.os_fingerprint import os_fingerprint
from mcp_servers.network_discover.port_scan import DEFAULT_PORTS, port_scan
from mcp_servers.network_discover.scan import scan_network

logger = logging.getLogger(__name__)


class NetworkDiscoverTool(BaseTool):
    """Tool to scan the local network and list connected devices."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="network_discover",
            description=(
                "Scans the local network (ARP scan) and returns every responding device's "
                "IP address, MAC address, and manufacturer (when resolvable from the MAC's "
                "OUI). Requires Npcap/libpcap and typically admin/root privileges."
            ),
            parameters=[],
            return_type="dict"
        )

    def execute(self, **kwargs) -> dict:
        try:
            return scan_network()
        except Exception as e:
            logger.error(f"NetworkDiscoverTool failed: {str(e)}")
            raise


class PortScanTool(BaseTool):
    """Tool to SYN-scan common TCP ports on a device on the local network."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="port_scan",
            description=(
                "SYN-scans common TCP ports on a device on your local network and reports "
                "which are open/closed/filtered. Restricted to private/local IP addresses "
                "(your own devices only, not arbitrary internet hosts). "
                f"Default ports checked: {DEFAULT_PORTS}."
            ),
            parameters=[
                ToolParameter(
                    name="ip",
                    type="string",
                    description="The private IPv4 address to scan, e.g. a device IP from network_discover",
                    required=True,
                ),
                ToolParameter(
                    name="ports",
                    type="list",
                    items_type="integer",
                    description="Specific ports to check instead of the default common set",
                    required=False,
                ),
            ],
            return_type="dict"
        )

    def execute(self, **kwargs) -> dict:
        try:
            return port_scan(kwargs["ip"], kwargs.get("ports"))
        except Exception as e:
            logger.error(f"PortScanTool failed: {str(e)}")
            raise


class OsFingerprintTool(BaseTool):
    """Tool to guess a device's OS family from its network response."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="os_fingerprint",
            description=(
                "Best-effort OS guess for a device on your local network, based on the "
                "TTL of its ICMP/TCP response (64=Linux/Unix/macOS, 128=Windows, "
                "255=many routers/embedded devices). A heuristic hint, not a certainty. "
                "Restricted to private/local IP addresses."
            ),
            parameters=[
                ToolParameter(
                    name="ip",
                    type="string",
                    description="The private IPv4 address to fingerprint, e.g. a device IP from network_discover",
                    required=True,
                ),
            ],
            return_type="dict"
        )

    def execute(self, **kwargs) -> dict:
        try:
            return os_fingerprint(kwargs["ip"])
        except Exception as e:
            logger.error(f"OsFingerprintTool failed: {str(e)}")
            raise
