"""Diagnostics support for the LIFX integration."""

from __future__ import annotations

from typing import Any

from homeassistant.const import CONF_HOST, CONF_IP_ADDRESS, CONF_MAC
from homeassistant.core import HomeAssistant
from homeassistant.helpers.redact import async_redact_data

from .const import CONF_LABEL, CONF_SERIAL
from .coordinator import LIFXConfigEntry

TO_REDACT = [CONF_LABEL, CONF_HOST, CONF_IP_ADDRESS, CONF_MAC, CONF_SERIAL]


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: LIFXConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "entry": {
            "title": entry.title,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
        },
        "data": async_redact_data(await coordinator.diagnostics(), TO_REDACT),
    }
