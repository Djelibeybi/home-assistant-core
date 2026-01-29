"""Tests for the lifx integration select entity."""

from datetime import timedelta

import pytest

from homeassistant.components import lifx
from homeassistant.components.lifx.const import CONF_SERIAL, DOMAIN
from homeassistant.components.select import DOMAIN as SELECT_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, CONF_HOST, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

from . import (
    DEFAULT_ENTRY_TITLE,
    IP_ADDRESS,
    SERIAL,
    _mocked_infrared_bulb,
    _mocked_light_strip,
    _patch_config_flow_try_connect,
    _patch_device,
    _patch_discovery,
)

from tests.common import MockConfigEntry, async_fire_time_changed


async def test_theme_select(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    """Test selecting a theme."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    bulb = _mocked_light_strip()
    with (
        _patch_discovery(device=bulb),
        _patch_config_flow_try_connect(device=bulb),
        _patch_device(device=bulb),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

    entity_id = "select.my_bulb_theme"

    entity = entity_registry.async_get(entity_id)
    assert entity
    assert not entity.disabled

    await hass.services.async_call(
        SELECT_DOMAIN,
        "select_option",
        {ATTR_ENTITY_ID: entity_id, "option": "intense"},
        blocking=True,
    )

    bulb.apply_theme.assert_called_once()


async def test_infrared_brightness(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    """Test getting and setting infrared brightness."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    bulb = _mocked_infrared_bulb()
    with (
        _patch_discovery(device=bulb),
        _patch_config_flow_try_connect(device=bulb),
        _patch_device(device=bulb),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

    unique_id = f"{SERIAL}_infrared_brightness"
    entity_id = "select.my_bulb_infrared_brightness"

    entity = entity_registry.async_get(entity_id)
    assert entity
    assert not entity.disabled
    assert entity.unique_id == unique_id

    state = hass.states.get(entity_id)
    assert state.state == "100%"


@pytest.mark.usefixtures("mock_discovery")
async def test_set_infrared_brightness_25_percent(hass: HomeAssistant) -> None:
    """Test setting infrared brightness to 25%."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    bulb = _mocked_infrared_bulb()
    with (
        _patch_discovery(device=bulb),
        _patch_config_flow_try_connect(device=bulb),
        _patch_device(device=bulb),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

    entity_id = "select.my_bulb_infrared_brightness"

    await hass.services.async_call(
        SELECT_DOMAIN,
        "select_option",
        {ATTR_ENTITY_ID: entity_id, "option": "25%"},
        blocking=True,
    )

    bulb.set_infrared.assert_called_with(0.25)

    bulb.state.infrared = 0.25

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=30))
    await hass.async_block_till_done(wait_background_tasks=True)

    state = hass.states.get(entity_id)
    assert state.state == "25%"


@pytest.mark.usefixtures("mock_discovery")
async def test_set_infrared_brightness_50_percent(hass: HomeAssistant) -> None:
    """Test setting infrared brightness to 50%."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    bulb = _mocked_infrared_bulb()
    with (
        _patch_discovery(device=bulb),
        _patch_config_flow_try_connect(device=bulb),
        _patch_device(device=bulb),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

    entity_id = "select.my_bulb_infrared_brightness"

    await hass.services.async_call(
        SELECT_DOMAIN,
        "select_option",
        {ATTR_ENTITY_ID: entity_id, "option": "50%"},
        blocking=True,
    )

    bulb.set_infrared.assert_called_with(0.50)

    bulb.state.infrared = 0.50

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=30))
    await hass.async_block_till_done(wait_background_tasks=True)

    state = hass.states.get(entity_id)
    assert state.state == "50%"


@pytest.mark.usefixtures("mock_discovery")
async def test_set_infrared_brightness_100_percent(hass: HomeAssistant) -> None:
    """Test setting infrared brightness to 100%."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    bulb = _mocked_infrared_bulb()
    with (
        _patch_discovery(device=bulb),
        _patch_config_flow_try_connect(device=bulb),
        _patch_device(device=bulb),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

    entity_id = "select.my_bulb_infrared_brightness"

    await hass.services.async_call(
        SELECT_DOMAIN,
        "select_option",
        {ATTR_ENTITY_ID: entity_id, "option": "100%"},
        blocking=True,
    )

    bulb.set_infrared.assert_called_with(1.0)

    bulb.state.infrared = 1.0

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=30))
    await hass.async_block_till_done(wait_background_tasks=True)

    state = hass.states.get(entity_id)
    assert state.state == "100%"


@pytest.mark.usefixtures("mock_discovery")
async def test_disable_infrared(hass: HomeAssistant) -> None:
    """Test disabling infrared brightness."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    bulb = _mocked_infrared_bulb()
    with (
        _patch_discovery(device=bulb),
        _patch_config_flow_try_connect(device=bulb),
        _patch_device(device=bulb),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

    entity_id = "select.my_bulb_infrared_brightness"

    await hass.services.async_call(
        SELECT_DOMAIN,
        "select_option",
        {ATTR_ENTITY_ID: entity_id, "option": "Disabled"},
        blocking=True,
    )

    bulb.set_infrared.assert_called_with(0.0)

    bulb.state.infrared = 0.0

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=30))
    await hass.async_block_till_done(wait_background_tasks=True)

    state = hass.states.get(entity_id)
    assert state.state == "Disabled"


@pytest.mark.usefixtures("mock_discovery")
async def test_invalid_infrared_brightness(hass: HomeAssistant) -> None:
    """Test invalid infrared brightness returns unknown state."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    bulb = _mocked_infrared_bulb()
    with (
        _patch_discovery(device=bulb),
        _patch_config_flow_try_connect(device=bulb),
        _patch_device(device=bulb),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

    entity_id = "select.my_bulb_infrared_brightness"

    bulb.state.infrared = 0.123

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=30))
    await hass.async_block_till_done(wait_background_tasks=True)

    state = hass.states.get(entity_id)
    assert state.state == STATE_UNKNOWN
