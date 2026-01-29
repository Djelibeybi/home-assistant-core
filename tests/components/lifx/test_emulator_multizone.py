"""Multizone/light strip tests using lifx-emulator."""

from __future__ import annotations

import pytest

from homeassistant.components.lifx.const import CONF_SERIAL, DOMAIN
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_HS_COLOR,
    DOMAIN as LIGHT_DOMAIN,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_ON
from homeassistant.core import HomeAssistant

from . import async_refresh_entry, get_entry_light_entity_id

from tests.common import MockConfigEntry


@pytest.mark.emulator
async def test_multizone_turn_on(
    hass: HomeAssistant,
    emulator_server,
    emulator_multizone_config,
) -> None:
    """Test turning on a multizone light strip via emulator."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=emulator_multizone_config,
        unique_id=emulator_multizone_config[CONF_SERIAL],
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
async def test_multizone_set_color(
    hass: HomeAssistant,
    emulator_server,
    emulator_multizone_config,
) -> None:
    """Test setting color on a multizone strip."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=emulator_multizone_config,
        unique_id=emulator_multizone_config[CONF_SERIAL],
        version=2,
    )
    config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    entity_id = get_entry_light_entity_id(hass, config_entry)

    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_on",
        {ATTR_ENTITY_ID: entity_id, ATTR_HS_COLOR: [240, 100]},
        blocking=True,
    )
    await async_refresh_entry(hass, config_entry)

    state = hass.states.get(entity_id)
    assert state.state == STATE_ON
    hs_color = state.attributes[ATTR_HS_COLOR]
    assert abs(hs_color[0] - 240) < 5  # Hue (blue)
    assert abs(hs_color[1] - 100) < 5  # Saturation


@pytest.mark.emulator
async def test_multizone_has_zones(
    hass: HomeAssistant,
    emulator_server,
    emulator_multizone_config,
) -> None:
    """Test that multizone device has multiple zones."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=emulator_multizone_config,
        unique_id=emulator_multizone_config[CONF_SERIAL],
        version=2,
    )
    config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    entity_id = get_entry_light_entity_id(hass, config_entry)

    state = hass.states.get(entity_id)
    assert state is not None
    assert "effect_move" in state.attributes["effect_list"]


@pytest.mark.emulator
async def test_multizone_brightness(
    hass: HomeAssistant,
    emulator_server,
    emulator_multizone_config,
) -> None:
    """Test brightness control on multizone strip."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=emulator_multizone_config,
        unique_id=emulator_multizone_config[CONF_SERIAL],
        version=2,
    )
    config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    entity_id = get_entry_light_entity_id(hass, config_entry)

    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_on",
        {ATTR_ENTITY_ID: entity_id, ATTR_BRIGHTNESS: 180},
        blocking=True,
    )
    await async_refresh_entry(hass, config_entry)

    state = hass.states.get(entity_id)
    assert state.state == STATE_ON
    assert abs(state.attributes[ATTR_BRIGHTNESS] - 180) <= 1
