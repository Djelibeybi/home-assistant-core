"""Error handling tests using lifx-emulator."""

from __future__ import annotations

import asyncio

import pytest

from homeassistant.components.lifx.const import CONF_SERIAL, DOMAIN
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from . import get_entry_light_entity_id

from tests.common import MockConfigEntry


@pytest.mark.emulator
async def test_device_offline(
    hass: HomeAssistant,
    emulator_server,
    emulator_device_config,
) -> None:
    """Test handling when device is offline."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=emulator_device_config,
        unique_id=emulator_device_config[CONF_SERIAL],
        version=2,
    )
    config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    entity_id = get_entry_light_entity_id(hass, config_entry)

    # Stop emulator to simulate device offline
    await emulator_server.stop()
    await asyncio.sleep(0.2)

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            LIGHT_DOMAIN,
            "turn_on",
            {ATTR_ENTITY_ID: entity_id},
            blocking=True,
        )


@pytest.mark.emulator
async def test_connection_refused(
    hass: HomeAssistant,
) -> None:
    """Test handling when connection is refused."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "127.0.0.2",
            CONF_SERIAL: "d073d5999999",
        },
        unique_id="d073d5999999",
        version=2,
    )
    config_entry.add_to_hass(hass)

    result = await hass.config_entries.async_setup(config_entry.entry_id)
    assert result is False
