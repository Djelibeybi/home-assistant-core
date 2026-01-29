"""Basic operation tests using lifx-emulator for protocol-level validation."""

from __future__ import annotations

import pytest

from homeassistant.components.lifx.const import CONF_SERIAL, DOMAIN
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ATTR_TRANSITION,
    DOMAIN as LIGHT_DOMAIN,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant

from . import async_refresh_entry, get_entry_light_entity_id

from tests.common import MockConfigEntry


@pytest.mark.emulator
async def test_color_bulb_turn_on(
    hass: HomeAssistant,
    emulator_server,
    emulator_device_config,
) -> None:
    """Test turning on a color bulb via emulator."""
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
async def test_color_bulb_turn_off(
    hass: HomeAssistant,
    emulator_server,
    emulator_device_config,
) -> None:
    """Test turning off a color bulb via emulator."""
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

    # Turn on first
    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_on",
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )
    await async_refresh_entry(hass, config_entry)

    state = hass.states.get(entity_id)
    assert state.state == STATE_ON

    # Turn off light
    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_off",
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )
    await async_refresh_entry(hass, config_entry)

    state = hass.states.get(entity_id)
    assert state.state == STATE_OFF


@pytest.mark.emulator
async def test_color_bulb_set_brightness(
    hass: HomeAssistant,
    emulator_server,
    emulator_device_config,
) -> None:
    """Test setting brightness on a color bulb via emulator."""
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

    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_on",
        {ATTR_ENTITY_ID: entity_id, ATTR_BRIGHTNESS: 128},
        blocking=True,
    )
    await async_refresh_entry(hass, config_entry)

    state = hass.states.get(entity_id)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_BRIGHTNESS] == 128


@pytest.mark.emulator
async def test_color_bulb_set_color_hs(
    hass: HomeAssistant,
    emulator_server,
    emulator_device_config,
) -> None:
    """Test setting HS color on a color bulb via emulator."""
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

    # Turn on with color (red)
    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_on",
        {ATTR_ENTITY_ID: entity_id, ATTR_HS_COLOR: [0, 100]},
        blocking=True,
    )
    await async_refresh_entry(hass, config_entry)

    state = hass.states.get(entity_id)
    assert state.state == STATE_ON
    hs_color = state.attributes[ATTR_HS_COLOR]
    assert abs(hs_color[0] - 0) < 1  # Hue
    assert abs(hs_color[1] - 100) < 1  # Saturation


@pytest.mark.emulator
async def test_color_bulb_set_color_temp(
    hass: HomeAssistant,
    emulator_server,
    emulator_device_config,
) -> None:
    """Test setting color temperature on a color bulb via emulator."""
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

    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_on",
        {ATTR_ENTITY_ID: entity_id, ATTR_COLOR_TEMP_KELVIN: 4000},
        blocking=True,
    )
    await async_refresh_entry(hass, config_entry)

    state = hass.states.get(entity_id)
    assert state.state == STATE_ON
    assert abs(state.attributes[ATTR_COLOR_TEMP_KELVIN] - 4000) < 50


@pytest.mark.emulator
async def test_color_bulb_transition(
    hass: HomeAssistant,
    emulator_server,
    emulator_device_config,
) -> None:
    """Test transition duration on a color bulb via emulator."""
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

    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_on",
        {ATTR_ENTITY_ID: entity_id, ATTR_BRIGHTNESS: 255, ATTR_TRANSITION: 2},
        blocking=True,
    )
    await async_refresh_entry(hass, config_entry)

    state = hass.states.get(entity_id)
    assert state.state == STATE_ON


@pytest.mark.emulator
async def test_color_bulb_attributes(
    hass: HomeAssistant,
    emulator_server,
    emulator_device_config,
) -> None:
    """Test that state attributes are correct for a color bulb."""
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
    state = hass.states.get(entity_id)
    assert state is not None

    # Verify friendly name
    assert state.attributes["friendly_name"] == "LIFX Color 000008"

    # Turn on and verify attributes
    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_on",
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )
    await async_refresh_entry(hass, config_entry)

    state = hass.states.get(entity_id)
    assert state.state == STATE_ON
    assert ATTR_BRIGHTNESS in state.attributes
    assert ATTR_HS_COLOR in state.attributes


@pytest.mark.emulator
async def test_color_bulb_multiple_operations(
    hass: HomeAssistant,
    emulator_server,
    emulator_device_config,
) -> None:
    """Test rapid sequential commands to a color bulb."""
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

    # Turn on
    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_on",
        {ATTR_ENTITY_ID: entity_id},
        blocking=True,
    )

    # Set brightness
    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_on",
        {ATTR_ENTITY_ID: entity_id, ATTR_BRIGHTNESS: 128},
        blocking=True,
    )

    # Set color
    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_on",
        {ATTR_ENTITY_ID: entity_id, ATTR_HS_COLOR: [120, 50]},
        blocking=True,
    )
    await async_refresh_entry(hass, config_entry)

    # Verify final state
    state = hass.states.get(entity_id)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_BRIGHTNESS] == 128
