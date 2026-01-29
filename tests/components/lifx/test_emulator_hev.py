"""HEV (Clean) bulb tests using lifx-emulator."""

from __future__ import annotations

import pytest

from homeassistant.components.lifx.const import CONF_SERIAL, DOMAIN
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import async_refresh_entry, get_entry_light_entity_id

from tests.common import MockConfigEntry


@pytest.mark.emulator
async def test_hev_bulb_turn_on(
    hass: HomeAssistant,
    emulator_server,
    emulator_hev_config,
) -> None:
    """Test turning on an HEV bulb via emulator."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=emulator_hev_config,
        unique_id=emulator_hev_config[CONF_SERIAL],
        version=2,
    )
    config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    entity_id = get_entry_light_entity_id(hass, config_entry)

    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_on",
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )
    await async_refresh_entry(hass, config_entry)

    state = hass.states.get(entity_id)
    assert state.state == STATE_ON


@pytest.mark.emulator
async def test_hev_bulb_has_button_entities(
    hass: HomeAssistant,
    emulator_server,
    emulator_hev_config,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test that HEV bulb creates button entities for HEV cycle control."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=emulator_hev_config,
        unique_id=emulator_hev_config[CONF_SERIAL],
        version=2,
    )
    config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    entries = er.async_entries_for_config_entry(entity_registry, config_entry.entry_id)

    button_entities = [e for e in entries if e.domain == "button"]
    assert len(button_entities) > 0, "HEV bulb should have button entities"


@pytest.mark.emulator
async def test_hev_bulb_normal_light_operation(
    hass: HomeAssistant,
    emulator_server,
    emulator_hev_config,
) -> None:
    """Test that HEV bulb works as a normal light."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=emulator_hev_config,
        unique_id=emulator_hev_config[CONF_SERIAL],
        version=2,
    )
    config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    entity_id = get_entry_light_entity_id(hass, config_entry)

    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_on",
        {ATTR_ENTITY_ID: entity_id, "brightness": 150},
        blocking=True,
    )
    await async_refresh_entry(hass, config_entry)

    state = hass.states.get(entity_id)
    assert state.state == STATE_ON
    assert state.attributes["brightness"] == 150
