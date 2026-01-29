"""LIFX device discovery."""

from __future__ import annotations

from lifx import Light, discover

from homeassistant import config_entries
from homeassistant.components import network
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import discovery_flow

from .const import (
    _LOGGER,
    CONF_SERIAL,
    DEVICE_RETRIES,
    DEVICE_TIMEOUT,
    DISCOVERY_TIMEOUT,
    DOMAIN,
)
from .util import normalize_serial


async def async_discover_devices(
    hass: HomeAssistant,
) -> list[dict[str, str | int]]:
    """Discover LIFX devices on all enabled networks."""
    discovered: list[dict[str, str | int]] = []
    existing_devices: dict[str, str] = {
        normalize_serial(entry.data[CONF_SERIAL]): str(entry.data.get(CONF_HOST, ""))
        for entry in hass.config_entries.async_entries(DOMAIN)
        if CONF_SERIAL in entry.data
    }
    broadcast_addrs = await network.async_get_ipv4_broadcast_addresses(hass)
    for address in broadcast_addrs:
        _LOGGER.debug("Discovering LIFX devices on %s", address)
        async for light in discover(
            timeout=DISCOVERY_TIMEOUT,
            broadcast_address=str(address),
            device_timeout=DEVICE_TIMEOUT,
            max_retries=DEVICE_RETRIES,
        ):
            if light is not None and isinstance(light, Light):
                serial = normalize_serial(light.serial)
                existing_host = existing_devices.get(serial)
                if existing_host and existing_host == light.ip:
                    continue
                if serial:
                    discovered.append(
                        {
                            CONF_HOST: light.ip,
                            CONF_PORT: light.port,
                            CONF_SERIAL: serial,
                        }
                    )
    return discovered


@callback
def async_trigger_discovery(
    hass: HomeAssistant,
    discovered: list[dict[str, str | int]],
) -> None:
    """Trigger config flows for discovered LIFX devices."""
    for device in discovered:
        async_init_discovery_flow(
            hass,
            host=str(device[CONF_HOST]),
            port=int(device[CONF_PORT]),
            serial=str(device[CONF_SERIAL]),
        )


@callback
def async_init_discovery_flow(
    hass: HomeAssistant, host: str, port: int, serial: str
) -> None:
    """Start a discovery flow for a LIFX device."""
    discovery_flow.async_create_flow(
        hass,
        DOMAIN,
        context={"source": config_entries.SOURCE_INTEGRATION_DISCOVERY},
        data={CONF_HOST: host, CONF_PORT: port, CONF_SERIAL: serial},
    )
