"""Advertises this machine on the clinic's local network as
<hostname>.local, using standard mDNS — the same mechanism a network
printer uses so it can be found by name instead of a raw IP. This is what
keeps other devices working even if the router hands this machine a
different address after a restart.

Best-effort by design: if it fails (unsupported network, zeroconf not
available, etc.) the app still runs fine at its plain IP address — mDNS
just makes the fixed name available on top of that. Windows, macOS and
modern Linux all resolve .local names out of the box; if a particular
router or older Windows machine does not, the fallback in the spec is a
router-level DHCP reservation.
"""
import socket


def get_lan_ip():
    """This machine's IP address on the clinic's local network. Used both to
    advertise the mDNS service below and (from Admin -> Connect a device) to
    show a numeric fallback address for devices that can't resolve
    .local names. Best-effort: falls back to loopback if there's no network
    at all, which is harmless since that only matters offline anyway."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def advertise_hostname(hostname: str, port: int):
    try:
        from zeroconf import ServiceInfo, Zeroconf

        ip = get_lan_ip()
        service_name = f"{hostname}._http._tcp.local."
        info = ServiceInfo(
            "_http._tcp.local.",
            service_name,
            addresses=[socket.inet_aton(ip)],
            port=port,
            server=f"{hostname}.local.",
            properties={"path": "/"},
        )
        zc = Zeroconf()
        zc.register_service(info)
        print(f"Advertising this machine as {hostname}.local ({ip}) on the local network.")
        return zc
    except Exception as e:  # noqa: BLE001 - never let mDNS trouble stop the app
        print(f"Could not advertise a local hostname (app still works by IP address): {e}")
        return None
