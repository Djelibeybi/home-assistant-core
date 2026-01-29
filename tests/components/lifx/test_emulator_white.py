"""White/color temperature bulb tests using lifx-emulator."""

from __future__ import annotations

import pytest

from homeassistant.components.lifx.const import CONF_SERIAL, DOMAIN
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_SUPPORTED_COLOR_MODES,
    DOMAIN as LIGHT_DOMAIN,
    ColorMode,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_ON
from homeassistant.core import HomeAssistant

from . import async_refresh_entry, get_entry_light_entity_id

from tests.common import MockConfigEntry


@pytest.mark.emulator
async def test_white_bulb_turn_on(
    hass: HomeAssistant,
    emulator_server,
    emulator_white_config,
) -> None:
    """Test turning on a white bulb via emulator."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=emulator_white_config,
        unique_id=emulator_white_config[CONF_SERIAL],
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
async def test_white_bulb_color_modes(
    hass: HomeAssistant,
    emulator_server,
    emulator_white_config,
) -> None:
    """Test that white bulb only supports color temperature mode."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=emulator_white_config,
        unique_id=emulator_white_config[CONF_SERIAL],
        version=2,
    )
    config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    entity_id = get_entry_light_entity_id(hass, config_entry)

    state = hass.states.get(entity_id)

    supported_modes = state.attributes[ATTR_SUPPORTED_COLOR_MODES]
    assert ColorMode.COLOR_TEMP in supported_modes
    assert ColorMode.HS not in supported_modes


@pytest.mark.emulator
async def test_white_bulb_set_color_temp(
    hass: HomeAssistant,
    emulator_server,
    emulator_white_config,
) -> None:
    """Test setting color temperature on a white bulb."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=emulator_white_config,
        unique_id=emulator_white_config[CONF_SERIAL],
        version=2,
    )
    config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    entity_id = get_entry_light_entity_id(hass, config_entry)

    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_on",
        {ATTR_ENTITY_ID: entity_id, ATTR_COLOR_TEMP_KELVIN: 3500},
        blocking=True,
    )
    await async_refresh_entry(hass, config_entry)

    state = hass.states.get(entity_id)
    assert state.state == STATE_ON
    assert abs(state.attributes[ATTR_COLOR_TEMP_KELVIN] - 3500) < 50


@pytest.mark.emulator
async def test_white_bulb_brightness(
    hass: HomeAssistant,
    emulator_server,
    emulator_white_config,
) -> None:
    """Test brightness control on a white bulb."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=emulator_white_config,
        unique_id=emulator_white_config[CONF_SERIAL],
        version=2,
    )
    config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    entity_id = get_entry_light_entity_id(hass, config_entry)

    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_on",
        {ATTR_ENTITY_ID: entity_id, ATTR_BRIGHTNESS: 200},
        blocking=True,
    )
    await async_refresh_entry(hass, config_entry)

    state = hass.states.get(entity_id)
    assert state.state == STATE_ON
    assert abs(state.attributes[ATTR_BRIGHTNESS] - 200) <= 1
