"""Tests for the LIFX button platform."""

from unittest.mock import patch

import pytest

from homeassistant.components import lifx
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN
from homeassistant.components.lifx.const import CONF_SERIAL, DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from . import (
    DEFAULT_ENTRY_TITLE,
    IP_ADDRESS,
    SERIAL,
    _mocked_bulb,
    _patch_config_flow_try_connect,
    _patch_device,
    _patch_discovery,
)

from tests.common import MockConfigEntry


@pytest.fixture(autouse=True)
def mock_identify_delay():
    """Patch the identify delay to zero for tests."""
    with patch("homeassistant.components.lifx.coordinator.IDENTIFY_DELAY", 0):
        yield


async def test_button_restart(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    """Test that a bulb can be restarted."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    bulb = _mocked_bulb()
    with (
        _patch_discovery(device=bulb),
        _patch_config_flow_try_connect(device=bulb),
        _patch_device(device=bulb),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

    unique_id = f"{SERIAL}_restart"
    entity_id = "button.my_bulb_restart"

    entity = entity_registry.async_get(entity_id)
    assert entity
    assert not entity.disabled
    assert entity.unique_id == unique_id

    await hass.services.async_call(
        BUTTON_DOMAIN, "press", {ATTR_ENTITY_ID: entity_id}, blocking=True
    )

    bulb.set_reboot.assert_called_once()


async def test_button_identify_when_off(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    """Test that identify flashes a bulb that is off."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    bulb = _mocked_bulb()
    with (
        _patch_discovery(device=bulb),
        _patch_config_flow_try_connect(device=bulb),
        _patch_device(device=bulb),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

    unique_id = f"{SERIAL}_identify"
    entity_id = "button.my_bulb_identify"

    entity = entity_registry.async_get(entity_id)
    assert entity
    assert not entity.disabled
    assert entity.unique_id == unique_id

    # Light is off (power=0 by default), so identify should turn on, flash, turn off
    await hass.services.async_call(
        BUTTON_DOMAIN, "press", {ATTR_ENTITY_ID: entity_id}, blocking=True
    )

    # When off: set_power(True), set_waveform(...), sleep, set_power(False)
    assert bulb.set_power.call_count == 2
    bulb.set_waveform.assert_called_once()


async def test_button_identify_when_on(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    """Test that identify only flashes a bulb that is already on."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    bulb = _mocked_bulb()
    # Set the light as on
    bulb.state.power = 65535
    with (
        _patch_discovery(device=bulb),
        _patch_config_flow_try_connect(device=bulb),
        _patch_device(device=bulb),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

    entity_id = "button.my_bulb_identify"

    await hass.services.async_call(
        BUTTON_DOMAIN, "press", {ATTR_ENTITY_ID: entity_id}, blocking=True
    )

    # When on: only set_waveform is called, no set_power calls
    bulb.set_waveform.assert_called_once()
    bulb.set_power.assert_not_called()
