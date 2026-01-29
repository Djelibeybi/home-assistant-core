"""Test LIFX diagnostics."""

from homeassistant.components import lifx
from homeassistant.components.lifx.const import CONF_SERIAL
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from . import (
    DEFAULT_ENTRY_TITLE,
    IP_ADDRESS,
    SERIAL,
    _mocked_bulb,
    _mocked_ceiling,
    _mocked_clean_bulb,
    _mocked_infrared_bulb,
    _mocked_light_strip,
    _mocked_tile,
    _patch_config_flow_try_connect,
    _patch_device,
    _patch_discovery,
)

from tests.common import MockConfigEntry
from tests.components.diagnostics import get_diagnostics_for_config_entry
from tests.typing import ClientSessionGenerator

BASE_DIAGNOSTICS = {
    "firmware": "3.0",
    "serial": "**REDACTED**",
    "model": "LIFX A19",
    "capabilities": {
        "has_color": True,
        "has_multizone": False,
        "has_matrix": False,
        "has_infrared": False,
        "has_hev": False,
    },
    "color": {
        "hue": 0,
        "saturation": 0,
        "brightness": 0.5,
        "kelvin": 3500,
    },
    "power": 0,
}


def _make_config_entry() -> MockConfigEntry:
    """Create a mock config entry for LIFX."""
    return MockConfigEntry(
        domain=lifx.DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )


async def _setup_and_get_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    config_entry: MockConfigEntry,
    bulb: object,
) -> dict:
    """Set up the integration and return diagnostics."""
    config_entry.add_to_hass(hass)
    with (
        _patch_discovery(device=bulb),
        _patch_config_flow_try_connect(device=bulb),
        _patch_device(device=bulb),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

    return await get_diagnostics_for_config_entry(hass, hass_client, config_entry)


async def test_bulb_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
) -> None:
    """Test diagnostics for a standard color bulb."""
    config_entry = _make_config_entry()
    bulb = _mocked_bulb()
    diag = await _setup_and_get_diagnostics(hass, hass_client, config_entry, bulb)
    assert diag == {
        "entry": {
            "title": DEFAULT_ENTRY_TITLE,
            "data": {"host": "**REDACTED**", "serial": "**REDACTED**"},
        },
        "data": BASE_DIAGNOSTICS,
    }


async def test_clean_bulb_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
) -> None:
    """Test diagnostics for a LIFX Clean (HEV) bulb."""
    config_entry = _make_config_entry()
    bulb = _mocked_clean_bulb()
    diag = await _setup_and_get_diagnostics(hass, hass_client, config_entry, bulb)
    assert diag == {
        "entry": {
            "title": DEFAULT_ENTRY_TITLE,
            "data": {"host": "**REDACTED**", "serial": "**REDACTED**"},
        },
        "data": {
            **BASE_DIAGNOSTICS,
            "capabilities": {
                **BASE_DIAGNOSTICS["capabilities"],
                "has_hev": True,
            },
            "hev": {
                "cycle": {
                    "remaining": 30,
                },
            },
        },
    }


async def test_infrared_bulb_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
) -> None:
    """Test diagnostics for a LIFX infrared bulb."""
    config_entry = _make_config_entry()
    bulb = _mocked_infrared_bulb()
    diag = await _setup_and_get_diagnostics(hass, hass_client, config_entry, bulb)
    assert diag == {
        "entry": {
            "title": DEFAULT_ENTRY_TITLE,
            "data": {"host": "**REDACTED**", "serial": "**REDACTED**"},
        },
        "data": {
            **BASE_DIAGNOSTICS,
            "capabilities": {
                **BASE_DIAGNOSTICS["capabilities"],
                "has_infrared": True,
            },
            "infrared": {"brightness": 1.0},
        },
    }


async def test_multizone_bulb_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
) -> None:
    """Test diagnostics for a LIFX multizone light strip."""
    config_entry = _make_config_entry()
    bulb = _mocked_light_strip()
    diag = await _setup_and_get_diagnostics(hass, hass_client, config_entry, bulb)
    zone_color = {
        "hue": 0,
        "saturation": 0,
        "brightness": 0.5,
        "kelvin": 3500,
    }
    assert diag == {
        "entry": {
            "title": DEFAULT_ENTRY_TITLE,
            "data": {"host": "**REDACTED**", "serial": "**REDACTED**"},
        },
        "data": {
            **BASE_DIAGNOSTICS,
            "capabilities": {
                **BASE_DIAGNOSTICS["capabilities"],
                "has_multizone": True,
            },
            "zones": {
                "count": 3,
                "colors": [zone_color, zone_color, zone_color],
            },
        },
    }


async def test_tile_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
) -> None:
    """Test diagnostics for a LIFX Tile (matrix) light."""
    config_entry = _make_config_entry()
    bulb = _mocked_tile()
    diag = await _setup_and_get_diagnostics(hass, hass_client, config_entry, bulb)
    assert diag == {
        "entry": {
            "title": DEFAULT_ENTRY_TITLE,
            "data": {"host": "**REDACTED**", "serial": "**REDACTED**"},
        },
        "data": {
            **BASE_DIAGNOSTICS,
            "capabilities": {
                **BASE_DIAGNOSTICS["capabilities"],
                "has_matrix": True,
            },
            "matrix": {
                "effect": "OFF",
                "tile_count": 5,
            },
        },
    }


async def test_ceiling_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
) -> None:
    """Test diagnostics for a LIFX Ceiling (matrix) light."""
    config_entry = _make_config_entry()
    bulb = _mocked_ceiling()
    diag = await _setup_and_get_diagnostics(hass, hass_client, config_entry, bulb)
    assert diag == {
        "entry": {
            "title": DEFAULT_ENTRY_TITLE,
            "data": {"host": "**REDACTED**", "serial": "**REDACTED**"},
        },
        "data": {
            **BASE_DIAGNOSTICS,
            "model": "LIFX Ceiling",
            "capabilities": {
                **BASE_DIAGNOSTICS["capabilities"],
                "has_matrix": True,
            },
            "matrix": {
                "effect": "OFF",
                "tile_count": 1,
            },
        },
    }
