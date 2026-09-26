"""Wake-on-LAN, so a TV that is off the network can be turned on."""

import re
import socket

from homeassistant.core import HomeAssistant

MAC = re.compile(r"^[0-9a-f]{2}([:-]?)[0-9a-f]{2}(\1[0-9a-f]{2}){4}$", re.IGNORECASE)


def valid_mac(mac: str) -> bool:
    return bool(MAC.match(mac.strip()))


def magic_packet(mac: str) -> bytes:
    digits = re.sub(r"[^0-9a-fA-F]", "", mac)
    if len(digits) != 12:
        raise ValueError(f"Not a MAC address: {mac}")
    return bytes.fromhex("FF" * 6 + digits * 16)


def _send(packet: bytes) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, ("255.255.255.255", 9))


async def async_wake(hass: HomeAssistant, mac: str) -> None:
    await hass.async_add_executor_job(_send, magic_packet(mac))
