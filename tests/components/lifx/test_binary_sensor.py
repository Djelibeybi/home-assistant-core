"""Test the LIFX binary sensor platform."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from homeassistant.components import lifx
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.lifx.const import CONF_SERIAL
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    CONF_HOST,
    STATE_OFF,
    STATE_ON,
    STATE_UNKNOWN,
    EntityCategory,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

from . import (
    DEFAULT_ENTRY_TITLE,
    IP_ADDRESS,
    SERIAL,
    _mocked_clean_bulb,
    _patch_config_flow_try_connect,
    _patch_device,
    _patch_discovery,
)

from tests.common import MockConfigEntry, async_fire_time_changed


@pytest.mark.usefixtures("mock_discovery")
async def test_hev_cycle_state(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    """Test HEV cycle state binary sensor."""
    config_entry = MockConfigEntry(
        domain=lifx.DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    bulb = _mocked_clean_bulb()
    with (
        _patch_discovery(device=bulb),
        _patch_config_flow_try_connect(device=bulb),
        _patch_device(device=bulb),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

    entity_id = "binary_sensor.my_bulb_clean_cycle"

    state = hass.states.get(entity_id)
    assert state
    assert state.state == STATE_ON
    assert state.attributes.get(ATTR_DEVICE_CLASS) == BinarySensorDeviceClass.RUNNING

    entry = entity_registry.async_get(entity_id)
    assert entry
    assert entry.unique_id == f"{SERIAL}_hev_cycle_state"
    assert entry.entity_category == EntityCategory.DIAGNOSTIC

    # Simulate HEV cycle finishing: remaining becomes 0
    bulb.state.hev_cycle.remaining_s = 0

    with (
        _patch_discovery(device=bulb),
        _patch_config_flow_try_connect(device=bulb),
        _patch_device(device=bulb),
    ):
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=30))
        await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(entity_id).state == STATE_OFF

    # Simulate state no longer being HevLightState (isinstance check fails)
    # Use spec=None so isinstance(state, HevLightState) returns False,
    # but provide enough attributes so other entities don't crash.
    mock_state = MagicMock()
    mock_state.power = 65535
    mock_state.color = bulb.state.color
    mock_state.host_firmware = bulb.state.host_firmware
    mock_state.group = bulb.state.group
    mock_state.capabilities = bulb.state.capabilities
    bulb.state = mock_state

    with (
        _patch_discovery(device=bulb),
        _patch_config_flow_try_connect(device=bulb),
        _patch_device(device=bulb),
    ):
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=30))
        await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(entity_id).state == STATE_UNKNOWN
