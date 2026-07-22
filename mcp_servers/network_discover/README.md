# network-discover MCP server

Local MCP (stdio) server exposing one tool, `network_discover`, which
ARP-scans the local /subnet and returns each responding device's IP, MAC,
and manufacturer as structured JSON.

Implemented with [Scapy](https://scapy.net/) — no external CLI scanner
required.

## Setup

```bash
pip install -r ../../requirements.txt   # installs `mcp`, `scapy`
```

### Windows: install Npcap

Scapy needs a packet-capture driver to send/receive raw ARP frames.

1. Download and run the installer from https://npcap.com/#download
2. During install, check **"Install Npcap in WinPcap API-compatible Mode"**
3. No further config needed — Scapy auto-detects it.

### Linux / macOS

libpcap is usually preinstalled. If not: `sudo apt install libpcap-dev`
(Debian/Ubuntu) or `brew install libpcap` (macOS).

### Privileges

Sending raw ARP packets needs elevated privileges:
- **Windows**: run the MCP server (or your terminal) as Administrator.
- **Linux/macOS**: run with `sudo`, or grant the capability once:
  ```bash
  sudo setcap cap_net_raw+ep $(which python3)
  ```

## Run standalone (for testing)

```bash
python server.py
```

It communicates over stdio, so it's meant to be launched by an MCP client,
not used interactively.

## Register with Claude Code

```bash
claude mcp add network-discover -- python "mcp_servers/network_discover/server.py"
```

Or add directly to `.mcp.json`:

```json
{
  "mcpServers": {
    "network-discover": {
      "command": "python",
      "args": ["mcp_servers/network_discover/server.py"]
    }
  }
}
```

## Example output

```json
{
  "network": "192.168.1.0/24",
  "devices": [
    {"ip": "192.168.1.1", "mac": "aa:bb:cc:dd:ee:ff", "manufacturer": "Netgear"},
    {"ip": "192.168.1.42", "mac": "11:22:33:44:55:66", "manufacturer": null}
  ],
  "count": 2,
  "warning": null
}
```
