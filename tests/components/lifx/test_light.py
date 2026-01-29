"""Tests for the LIFX integration light platform."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

from lifx import HSBK, LifxTimeoutError
import pytest

from homeassistant.components import lifx
from homeassistant.components.lifx import DOMAIN
from homeassistant.components.lifx.const import CONF_SERIAL
from homeassistant.components.lifx.light import ATTR_INFRARED
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_MODE,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_EFFECT,
    ATTR_HS_COLOR,
    ATTR_RGB_COLOR,
    ATTR_SUPPORTED_COLOR_MODES,
    ATTR_TRANSITION,
    ATTR_XY_COLOR,
    DOMAIN as LIGHT_DOMAIN,
    SERVICE_TURN_ON,
    ColorMode,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_HOST,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

from . import (
    DEFAULT_ENTRY_TITLE,
    IP_ADDRESS,
    MAC_ADDRESS,
    SERIAL,
    SERIAL_FORMATTED,
    _mocked_brightness_bulb,
    _mocked_bulb,
    _mocked_bulb_new_firmware,
    _mocked_clean_bulb,
    _mocked_infrared_bulb,
    _mocked_light_strip,
    _mocked_white_bulb,
    _patch_config_flow_try_connect,
    _patch_device,
    _patch_discovery,
)

from tests.common import MockConfigEntry, async_fire_time_changed


@pytest.fixture(autouse=True)
def patch_lifx_state_settle_delay():
    """Set asyncio.sleep for state settles to zero."""
    with patch("homeassistant.components.lifx.light.LIFX_STATE_SETTLE_DELAY", 0):
        yield


async def test_light_unique_id(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test a light unique id."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    light = _mocked_bulb()
    with (
        _patch_discovery(device=light),
        _patch_config_flow_try_connect(device=light),
        _patch_device(device=light),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

    entity_id = "light.my_bulb"
    assert entity_registry.async_get(entity_id).unique_id == SERIAL

    device = device_registry.async_get_device(
        connections={(dr.CONNECTION_NETWORK_MAC, SERIAL_FORMATTED)}
    )
    assert device.identifiers == {(DOMAIN, SERIAL)}


async def test_light_unique_id_new_firmware(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test a light unique id with newer firmware."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    light = _mocked_bulb_new_firmware()
    with (
        _patch_discovery(device=light),
        _patch_config_flow_try_connect(device=light),
        _patch_device(device=light),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

    entity_id = "light.my_bulb"
    assert entity_registry.async_get(entity_id).unique_id == SERIAL
    device = device_registry.async_get_device(
        connections={(dr.CONNECTION_NETWORK_MAC, MAC_ADDRESS)},
    )
    assert device.identifiers == {(DOMAIN, SERIAL)}


async def test_color_light_with_temp(
    hass: HomeAssistant, mock_effect_conductor
) -> None:
    """Test a color light with temp."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    light = _mocked_bulb()
    light.state.power = 65535
    light.state.color = HSBK(hue=360, saturation=1.0, brightness=1.0, kelvin=9000)

    with (
        _patch_discovery(device=light),
        _patch_config_flow_try_connect(device=light),
        _patch_device(device=light),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

        entity_id = "light.my_bulb"

        state = hass.states.get(entity_id)
        assert state.state == STATE_ON
        attributes = state.attributes
        assert attributes[ATTR_BRIGHTNESS] == 255
        assert attributes[ATTR_COLOR_MODE] == ColorMode.HS
        assert attributes[ATTR_SUPPORTED_COLOR_MODES] == [
            ColorMode.COLOR_TEMP,
            ColorMode.HS,
        ]
        assert attributes[ATTR_HS_COLOR] == (360.0, 100.0)
        assert attributes[ATTR_RGB_COLOR] == (255, 0, 0)
        assert attributes[ATTR_XY_COLOR] == (0.701, 0.299)

        # Simulate a state update where the light is now at color temp
        light.state.color = HSBK(
            hue=175.7, saturation=0.0, brightness=0.49, kelvin=6000
        )

        await hass.services.async_call(
            LIGHT_DOMAIN, "turn_on", {ATTR_ENTITY_ID: entity_id}, blocking=True
        )
        light.set_power.assert_called()
        assert light.set_power.call_args[0][0] is True
        light.set_power.reset_mock()

        # Trigger coordinator refresh to pick up new mock state
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=30))
        await hass.async_block_till_done(wait_background_tasks=True)

        state = hass.states.get(entity_id)
        assert state.state == STATE_ON
        attributes = state.attributes
        assert attributes[ATTR_BRIGHTNESS] == 125
        assert attributes[ATTR_COLOR_MODE] == ColorMode.COLOR_TEMP
        assert attributes[ATTR_SUPPORTED_COLOR_MODES] == [
            ColorMode.COLOR_TEMP,
            ColorMode.HS,
        ]
        assert attributes[ATTR_COLOR_TEMP_KELVIN] == 6000

        # Reset to full color for remaining tests
        light.state.color = HSBK(hue=360, saturation=1.0, brightness=1.0, kelvin=9000)

        await hass.services.async_call(
            LIGHT_DOMAIN, "turn_off", {ATTR_ENTITY_ID: entity_id}, blocking=True
        )
        light.set_power.assert_called()
        assert light.set_power.call_args[0][0] is False
        light.set_power.reset_mock()

        await hass.services.async_call(
            LIGHT_DOMAIN, "turn_on", {ATTR_ENTITY_ID: entity_id}, blocking=True
        )
        light.set_power.assert_called()
        assert light.set_power.call_args[0][0] is True
        light.set_power.reset_mock()

        # Turn on with brightness
        await hass.services.async_call(
            LIGHT_DOMAIN,
            "turn_on",
            {ATTR_ENTITY_ID: entity_id, ATTR_BRIGHTNESS: 100},
            blocking=True,
        )
        light.set_color.assert_called()
        color_arg = light.set_color.call_args[0][0]
        assert color_arg.brightness == pytest.approx(100 / 255, abs=0.01)
        light.set_color.reset_mock()

        # Turn on with HS color
        await hass.services.async_call(
            LIGHT_DOMAIN,
            "turn_on",
            {ATTR_ENTITY_ID: entity_id, ATTR_HS_COLOR: (10, 30)},
            blocking=True,
        )
        light.set_color.assert_called()
        color_arg = light.set_color.call_args[0][0]
        assert color_arg.hue == pytest.approx(10, abs=1)
        assert color_arg.saturation == pytest.approx(0.30, abs=0.01)
        light.set_color.reset_mock()

        # Turn on with RGB color
        await hass.services.async_call(
            LIGHT_DOMAIN,
            "turn_on",
            {ATTR_ENTITY_ID: entity_id, ATTR_RGB_COLOR: (255, 30, 80)},
            blocking=True,
        )
        light.set_color.assert_called()
        color_arg = light.set_color.call_args[0][0]
        # RGB (255, 30, 80) -> HS approx (346.7, 88.2)
        assert color_arg.hue == pytest.approx(346.7, abs=1)
        assert color_arg.saturation == pytest.approx(0.882, abs=0.02)
        light.set_color.reset_mock()

        # Turn on with XY color
        await hass.services.async_call(
            LIGHT_DOMAIN,
            "turn_on",
            {ATTR_ENTITY_ID: entity_id, ATTR_XY_COLOR: (0.46, 0.376)},
            blocking=True,
        )
        light.set_color.assert_called()
        color_arg = light.set_color.call_args[0][0]
        assert color_arg.hue == pytest.approx(27.2, abs=2)
        assert color_arg.saturation == pytest.approx(0.467, abs=0.02)
        light.set_color.reset_mock()

        # Turn on with effect
        await hass.services.async_call(
            LIGHT_DOMAIN,
            "turn_on",
            {ATTR_ENTITY_ID: entity_id, ATTR_EFFECT: "effect_stop"},
            blocking=True,
        )
        assert len(mock_effect_conductor.stop.mock_calls) >= 1


async def test_white_bulb(hass: HomeAssistant) -> None:
    """Test a white bulb."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    light = _mocked_white_bulb()
    light.state.power = 65535
    light.state.color = HSBK(hue=175.7, saturation=0.0, brightness=0.49, kelvin=6000)

    with (
        _patch_discovery(device=light),
        _patch_config_flow_try_connect(device=light),
        _patch_device(device=light),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

        entity_id = "light.my_bulb"

        state = hass.states.get(entity_id)
        assert state.state == STATE_ON
        attributes = state.attributes
        assert attributes[ATTR_BRIGHTNESS] == 125
        assert attributes[ATTR_COLOR_MODE] == ColorMode.COLOR_TEMP
        assert attributes[ATTR_SUPPORTED_COLOR_MODES] == [
            ColorMode.COLOR_TEMP,
        ]
        assert attributes[ATTR_COLOR_TEMP_KELVIN] == 6000

        # Turn off
        await hass.services.async_call(
            LIGHT_DOMAIN, "turn_off", {ATTR_ENTITY_ID: entity_id}, blocking=True
        )
        light.set_power.assert_called()
        assert light.set_power.call_args[0][0] is False
        light.set_power.reset_mock()

        # Turn on
        await hass.services.async_call(
            LIGHT_DOMAIN, "turn_on", {ATTR_ENTITY_ID: entity_id}, blocking=True
        )
        light.set_power.assert_called()
        assert light.set_power.call_args[0][0] is True
        light.set_power.reset_mock()

        # Turn on with brightness
        await hass.services.async_call(
            LIGHT_DOMAIN,
            "turn_on",
            {ATTR_ENTITY_ID: entity_id, ATTR_BRIGHTNESS: 100},
            blocking=True,
        )
        light.set_color.assert_called()
        color_arg = light.set_color.call_args[0][0]
        assert color_arg.brightness == pytest.approx(100 / 255, abs=0.01)
        assert color_arg.kelvin == 6000
        light.set_color.reset_mock()

        # Turn on with color temp
        await hass.services.async_call(
            LIGHT_DOMAIN,
            "turn_on",
            {ATTR_ENTITY_ID: entity_id, ATTR_COLOR_TEMP_KELVIN: 2500},
            blocking=True,
        )
        light.set_color.assert_called()
        color_arg = light.set_color.call_args[0][0]
        assert color_arg.saturation == pytest.approx(0, abs=0.01)
        assert color_arg.kelvin == 2500
        light.set_color.reset_mock()


async def test_brightness_bulb(hass: HomeAssistant) -> None:
    """Test a brightness only bulb."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    light = _mocked_brightness_bulb()
    light.state.power = 65535
    light.state.color = HSBK(hue=175.7, saturation=0.0, brightness=0.49, kelvin=2700)

    with (
        _patch_discovery(device=light),
        _patch_config_flow_try_connect(device=light),
        _patch_device(device=light),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

        entity_id = "light.my_bulb"

        state = hass.states.get(entity_id)
        assert state.state == STATE_ON
        attributes = state.attributes
        assert attributes[ATTR_BRIGHTNESS] == 125
        assert attributes[ATTR_COLOR_MODE] == ColorMode.BRIGHTNESS
        assert attributes[ATTR_SUPPORTED_COLOR_MODES] == [
            ColorMode.BRIGHTNESS,
        ]

        # Turn off
        await hass.services.async_call(
            LIGHT_DOMAIN, "turn_off", {ATTR_ENTITY_ID: entity_id}, blocking=True
        )
        light.set_power.assert_called()
        assert light.set_power.call_args[0][0] is False
        light.set_power.reset_mock()

        # Turn on
        await hass.services.async_call(
            LIGHT_DOMAIN, "turn_on", {ATTR_ENTITY_ID: entity_id}, blocking=True
        )
        light.set_power.assert_called()
        assert light.set_power.call_args[0][0] is True
        light.set_power.reset_mock()

        # Turn on with brightness
        await hass.services.async_call(
            LIGHT_DOMAIN,
            "turn_on",
            {ATTR_ENTITY_ID: entity_id, ATTR_BRIGHTNESS: 100},
            blocking=True,
        )
        light.set_color.assert_called()
        color_arg = light.set_color.call_args[0][0]
        assert color_arg.brightness == pytest.approx(100 / 255, abs=0.01)
        light.set_color.reset_mock()


async def test_transitions_brightness_only(hass: HomeAssistant) -> None:
    """Test transitions with a brightness only device."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    light = _mocked_brightness_bulb()
    light.state.power = 65535
    light.state.color = HSBK(hue=175.7, saturation=0.0, brightness=0.49, kelvin=2700)

    with (
        _patch_discovery(device=light),
        _patch_config_flow_try_connect(device=light),
        _patch_device(device=light),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

        entity_id = "light.my_bulb"

        state = hass.states.get(entity_id)
        assert state.state == STATE_ON
        attributes = state.attributes
        assert attributes[ATTR_BRIGHTNESS] == 125
        assert attributes[ATTR_COLOR_MODE] == ColorMode.BRIGHTNESS
        assert attributes[ATTR_SUPPORTED_COLOR_MODES] == [
            ColorMode.BRIGHTNESS,
        ]

        # Turn off
        await hass.services.async_call(
            LIGHT_DOMAIN, "turn_off", {ATTR_ENTITY_ID: entity_id}, blocking=True
        )
        light.set_power.assert_called()
        assert light.set_power.call_args[0][0] is False
        light.set_power.reset_mock()
        light.state.power = 0

        # Refresh coordinator so entity knows the light is off
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=30))
        await hass.async_block_till_done(wait_background_tasks=True)

        # Turn on with transition and brightness (light is off)
        await hass.services.async_call(
            LIGHT_DOMAIN,
            "turn_on",
            {ATTR_ENTITY_ID: entity_id, ATTR_TRANSITION: 5, ATTR_BRIGHTNESS: 100},
            blocking=True,
        )
        # When off, set_color is called first, then set_power with duration
        light.set_color.assert_called()
        light.set_power.assert_called()
        assert light.set_power.call_args[0][0] is True
        assert light.set_power.call_args[0][1] == 5
        light.set_power.reset_mock()
        light.set_color.reset_mock()

        light.state.power = 0

        # Refresh coordinator so entity knows the light is off
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=30))
        await hass.async_block_till_done(wait_background_tasks=True)

        # Turn on with transition and higher brightness (light is still off)
        await hass.services.async_call(
            LIGHT_DOMAIN,
            "turn_on",
            {ATTR_ENTITY_ID: entity_id, ATTR_TRANSITION: 5, ATTR_BRIGHTNESS: 200},
            blocking=True,
        )
        light.set_color.assert_called()
        light.set_power.assert_called()
        assert light.set_power.call_args[0][0] is True
        light.set_power.reset_mock()
        light.set_color.reset_mock()

        await hass.async_block_till_done()
        light.refresh_state.reset_mock()

        # Ensure we force an update after the transition
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=5))
        await hass.async_block_till_done()
        assert light.refresh_state.call_count >= 1


async def test_transitions_color_bulb(hass: HomeAssistant) -> None:
    """Test transitions with a color bulb."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    light = _mocked_bulb_new_firmware()
    light.state.power = 65535
    light.state.color = HSBK(hue=175.7, saturation=0.0, brightness=0.49, kelvin=6000)

    with (
        _patch_discovery(device=light),
        _patch_config_flow_try_connect(device=light),
        _patch_device(device=light),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

        entity_id = "light.my_bulb"

        state = hass.states.get(entity_id)
        assert state.state == STATE_ON
        attributes = state.attributes
        assert attributes[ATTR_BRIGHTNESS] == 125
        assert attributes[ATTR_COLOR_MODE] == ColorMode.COLOR_TEMP

        # Turn off
        await hass.services.async_call(
            LIGHT_DOMAIN, "turn_off", {ATTR_ENTITY_ID: entity_id}, blocking=True
        )
        light.set_power.assert_called()
        assert light.set_power.call_args[0][0] is False
        light.set_power.reset_mock()
        light.state.power = 0

        # Turn off with transition (already off - duration should be 0)
        await hass.services.async_call(
            LIGHT_DOMAIN,
            "turn_off",
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_TRANSITION: 5,
            },
            blocking=True,
        )
        light.set_power.assert_called()
        assert light.set_power.call_args[0][0] is False
        light.set_power.reset_mock()
        light.set_color.reset_mock()

        # Turn on with RGB, transition, and brightness (light is off)
        await hass.services.async_call(
            LIGHT_DOMAIN,
            "turn_on",
            {
                ATTR_RGB_COLOR: (255, 5, 10),
                ATTR_ENTITY_ID: entity_id,
                ATTR_TRANSITION: 5,
                ATTR_BRIGHTNESS: 100,
            },
            blocking=True,
        )
        light.set_color.assert_called()
        color_arg = light.set_color.call_args[0][0]
        # RGB (255, 5, 10) -> HS approx (358.8, 98.0)
        assert color_arg.hue == pytest.approx(358.8, abs=2)
        assert color_arg.saturation == pytest.approx(0.98, abs=0.02)
        assert color_arg.brightness == pytest.approx(100 / 255, abs=0.01)

        light.set_power.assert_called()
        assert light.set_power.call_args[0][0] is True
        light.set_power.reset_mock()
        light.set_color.reset_mock()

        # Set power on to test on->on transitions
        light.state.power = 12800

        # Turn on with RGB, transition, and brightness (light is on)
        await hass.services.async_call(
            LIGHT_DOMAIN,
            "turn_on",
            {
                ATTR_RGB_COLOR: (5, 5, 10),
                ATTR_ENTITY_ID: entity_id,
                ATTR_TRANSITION: 5,
                ATTR_BRIGHTNESS: 200,
            },
            blocking=True,
        )
        light.set_color.assert_called()
        color_arg = light.set_color.call_args[0][0]
        # RGB (5, 5, 10) -> HS approx (240, 50)
        assert color_arg.hue == pytest.approx(240, abs=2)
        assert color_arg.saturation == pytest.approx(0.50, abs=0.02)
        assert color_arg.brightness == pytest.approx(200 / 255, abs=0.01)
        # Duration should be passed
        assert (
            light.set_color.call_args[0][1] == 5
            or light.set_color.call_args[1].get("duration") == 5
        )
        light.set_power.reset_mock()
        light.set_color.reset_mock()

        await hass.async_block_till_done()
        light.refresh_state.reset_mock()

        # Ensure we force an update after the transition
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=5))
        await hass.async_block_till_done()
        assert light.refresh_state.call_count >= 1

        light.set_power.reset_mock()
        light.set_color.reset_mock()

        # Turn off with transition (light is on)
        await hass.services.async_call(
            LIGHT_DOMAIN,
            "turn_off",
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_TRANSITION: 5,
            },
            blocking=True,
        )
        light.set_power.assert_called()
        assert light.set_power.call_args[0][0] is False
        light.set_power.reset_mock()
        light.set_color.reset_mock()


async def test_color_bulb_is_actually_off(hass: HomeAssistant) -> None:
    """Test setting a color when we think a bulb is on but its actually off."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    light = _mocked_bulb_new_firmware()
    light.state.power = 65535
    light.state.color = HSBK(hue=175.7, saturation=0.0, brightness=0.49, kelvin=6000)

    with (
        _patch_discovery(device=light),
        _patch_config_flow_try_connect(device=light),
        _patch_device(device=light),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

        entity_id = "light.my_bulb"

        state = hass.states.get(entity_id)
        assert state.state == STATE_ON

        # Simulate the device actually being off when we try to set color:
        # the set_color call will update power to 0 (simulating the device
        # reporting off after the command).
        async def set_color_and_power_off(*args, **kwargs):
            light.state.power = 0

        light.set_color = AsyncMock(side_effect=set_color_and_power_off)

        await hass.services.async_call(
            LIGHT_DOMAIN,
            "turn_on",
            {
                ATTR_RGB_COLOR: (100, 100, 100),
                ATTR_ENTITY_ID: entity_id,
                ATTR_BRIGHTNESS: 100,
            },
            blocking=True,
        )
        light.set_color.assert_called()
        color_arg = light.set_color.call_args[0][0]
        # RGB (100, 100, 100) -> HS (0, 0), brightness=100/255
        assert color_arg.saturation == pytest.approx(0.0, abs=0.01)
        assert color_arg.brightness == pytest.approx(100 / 255, abs=0.01)
        # set_power should have been called (for power_on=True)
        assert light.set_power.call_count >= 1


async def test_white_light_fails(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    """Test we handle failure to power on off."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    light = _mocked_white_bulb()
    entity_id = "light.my_bulb"

    # Make set_power fail
    light.set_power = AsyncMock(side_effect=LifxTimeoutError("timeout"))

    with _patch_discovery(device=light), _patch_device(device=light):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()
        assert entity_registry.async_get(entity_id).unique_id == SERIAL
        assert hass.states.get(entity_id).state == STATE_OFF

        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                LIGHT_DOMAIN,
                "turn_on",
                {ATTR_ENTITY_ID: entity_id},
                blocking=True,
            )
        light.set_power.assert_called()
        assert light.set_power.call_args[0][0] is True
        light.set_power.reset_mock()

        # Now make set_power work but set_color fail
        light.set_power = AsyncMock()
        light.set_color = AsyncMock(side_effect=LifxTimeoutError("timeout"))

        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                LIGHT_DOMAIN,
                "turn_on",
                {ATTR_ENTITY_ID: entity_id, ATTR_COLOR_TEMP_KELVIN: 6000},
                blocking=True,
            )
        light.set_color.assert_called()
        color_arg = light.set_color.call_args[0][0]
        assert color_arg.kelvin == 6000
        assert color_arg.saturation == pytest.approx(0.0, abs=0.01)
        light.set_color.reset_mock()


async def test_config_zoned_light_strip_fails(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    """Test we handle failure to update zones."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    light = _mocked_light_strip()
    entity_id = "light.my_bulb"

    # Make refresh_state fail on the second call (first succeeds during setup)
    call_count = 0

    async def refresh_state_failing():
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            raise LifxTimeoutError("timeout")

    light.refresh_state = AsyncMock(side_effect=refresh_state_failing)

    with (
        _patch_discovery(device=light),
        _patch_device(device=light),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()
        assert entity_registry.async_get(entity_id).unique_id == SERIAL
        assert hass.states.get(entity_id).state == STATE_OFF

        # Coordinator retries DEVICE_UNAVAILABLE_RETRIES (3) times before
        # marking unavailable. After the 4th failure, _update_attempts exceeds
        # the retry count and raises UpdateFailed. But on the next update cycle
        # attempts reset to 0, so we check state after exactly 4 failures.
        for _ in range(4):
            async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=30))
            await hass.async_block_till_done(wait_background_tasks=True)
        assert hass.states.get(entity_id).state == STATE_UNAVAILABLE


async def test_legacy_zoned_light_strip(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    """Test a legacy zoned light strip with zone refresh."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    light = _mocked_light_strip()
    entity_id = "light.my_bulb"

    # Track refresh_state calls
    refresh_call_count = 0

    async def refresh_state_tracking():
        nonlocal refresh_call_count
        refresh_call_count += 1

    light.refresh_state = AsyncMock(side_effect=refresh_state_tracking)

    with (
        _patch_discovery(device=light),
        _patch_device(device=light),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()
        assert entity_registry.async_get(entity_id).unique_id == SERIAL
        assert hass.states.get(entity_id).state == STATE_OFF
        initial_refresh_count = refresh_call_count

        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=30))
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).state == STATE_OFF
        # Verify that refresh was called at least once more after the time change
        assert refresh_call_count > initial_refresh_count


async def test_light_strip_zones_not_populated_yet(hass: HomeAssistant) -> None:
    """Test a light strip where zones are not populated initially."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    light = _mocked_light_strip()
    light.state.power = 65535
    # Initially zones are not populated
    light.state.zones = []
    light.state.zone_count = 0
    light.state.color = HSBK(hue=360, saturation=1.0, brightness=1.0, kelvin=9000)

    # After first refresh, zones get populated
    async def populate_zones():
        light.state.zones = [
            HSBK(hue=0, saturation=0, brightness=1.0, kelvin=3500)
        ] * 16
        light.state.zone_count = 16

    light.refresh_state = AsyncMock(side_effect=populate_zones)

    with (
        _patch_discovery(device=light),
        _patch_config_flow_try_connect(device=light),
        _patch_device(device=light),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

        entity_id = "light.my_bulb"

        # Verify refresh_state was called
        assert light.refresh_state.call_count >= 1

        state = hass.states.get(entity_id)
        assert state.state == STATE_ON
        attributes = state.attributes
        assert attributes[ATTR_BRIGHTNESS] == 255
        assert attributes[ATTR_COLOR_MODE] == ColorMode.HS
        assert attributes[ATTR_SUPPORTED_COLOR_MODES] == [
            ColorMode.COLOR_TEMP,
            ColorMode.HS,
        ]

        # Turn on
        await hass.services.async_call(
            LIGHT_DOMAIN,
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: entity_id},
            blocking=True,
        )
        light.set_power.assert_called()
        assert light.set_power.call_args[0][0] is True
        light.set_power.reset_mock()

        # After a coordinator update, the state should still be on
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=30))
        await hass.async_block_till_done()
        state = hass.states.get(entity_id)
        assert state.state == STATE_ON


async def test_software_effect_shown_in_attributes(
    hass: HomeAssistant, mock_effect_conductor
) -> None:
    """Test that a running software effect is reflected in entity attributes."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    light = _mocked_bulb()
    light.state.power = 65535
    light.state.color = HSBK(hue=360, saturation=1.0, brightness=1.0, kelvin=9000)

    with (
        _patch_discovery(device=light),
        _patch_config_flow_try_connect(device=light),
        _patch_device(device=light),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

        entity_id = "light.my_bulb"
        state = hass.states.get(entity_id)
        assert state.state == STATE_ON
        # No effect initially
        assert state.attributes.get(ATTR_EFFECT) is None

        # Configure mock conductor to report a running effect
        mock_sw_effect = AsyncMock()
        mock_sw_effect.name = "colorloop"
        mock_effect_conductor.effect.return_value = mock_sw_effect

        # Trigger a coordinator update to pick up the effect
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=30))
        await hass.async_block_till_done(wait_background_tasks=True)

        state = hass.states.get(entity_id)
        assert state.attributes[ATTR_EFFECT] == "effect_colorloop"


async def test_infrared_light_set_state(hass: HomeAssistant) -> None:
    """Test setting infrared brightness via set_state service."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    light = _mocked_infrared_bulb()
    light.state.power = 65535
    light.state.color = HSBK(hue=180, saturation=0.5, brightness=0.5, kelvin=3500)

    with (
        _patch_discovery(device=light),
        _patch_config_flow_try_connect(device=light),
        _patch_device(device=light),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

        entity_id = "light.my_bulb"
        state = hass.states.get(entity_id)
        assert state.state == STATE_ON

        # Set state with infrared value via the set_state service
        await hass.services.async_call(
            DOMAIN,
            "set_state",
            {ATTR_ENTITY_ID: entity_id, ATTR_INFRARED: 128},
            blocking=True,
        )
        light.set_infrared.assert_called()


async def test_clean_bulb_hev_cycle(hass: HomeAssistant) -> None:
    """Test setting HEV cycle state on a clean bulb."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    light = _mocked_clean_bulb()
    light.state.power = 65535
    light.state.color = HSBK(hue=180, saturation=0.5, brightness=0.5, kelvin=3500)

    with (
        _patch_discovery(device=light),
        _patch_config_flow_try_connect(device=light),
        _patch_device(device=light),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

        entity_id = "light.my_bulb"
        state = hass.states.get(entity_id)
        assert state.state == STATE_ON

        # Set HEV cycle state via the service
        await hass.services.async_call(
            DOMAIN,
            "set_hev_cycle_state",
            {ATTR_ENTITY_ID: entity_id, "power": True, "duration": 3600},
            blocking=True,
        )
        light.set_hev_cycle.assert_called_with(True, 3600)
