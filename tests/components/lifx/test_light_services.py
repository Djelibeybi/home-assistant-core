"""Tests for the LIFX integration light service calls."""

from __future__ import annotations

from unittest.mock import patch

from lifx import HSBK
import pytest

from homeassistant.components.lifx.const import (
    ATTR_INFRARED,
    ATTR_POWER,
    CONF_SERIAL,
    DOMAIN,
)
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_BRIGHTNESS_PCT,
    ATTR_BRIGHTNESS_STEP,
    ATTR_BRIGHTNESS_STEP_PCT,
    ATTR_COLOR_MODE,
    ATTR_COLOR_NAME,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGB_COLOR,
    ATTR_XY_COLOR,
    DOMAIN as LIGHT_DOMAIN,
    ColorMode,
)
from homeassistant.const import ATTR_ENTITY_ID, CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from . import (
    DEFAULT_ENTRY_TITLE,
    SERIAL,
    _mocked_bulb,
    _mocked_clean_bulb,
    _mocked_infrared_bulb,
    _patch_device,
    _patch_discovery,
)

from tests.common import MockConfigEntry


@pytest.fixture(autouse=True)
def patch_lifx_state_settle_delay():
    """Set asyncio.sleep for state settles to zero."""
    with patch("homeassistant.components.lifx.light.LIFX_STATE_SETTLE_DELAY", 0):
        yield


async def test_lifx_set_state_brightness(hass: HomeAssistant) -> None:
    """Test lifx.set_state works with brightness_step and brightness_step_pct."""
    light = _mocked_bulb()
    light.state.power = 65535
    light.state.color = HSBK(hue=0, saturation=0, brightness=0.5, kelvin=3500)

    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: "127.0.0.1", CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    entry.add_to_hass(hass)

    with (
        _patch_device(light),
        _patch_discovery(light),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        entity_id = "light.my_bulb"

        # brightness_step should adjust brightness relative to current
        await hass.services.async_call(
            DOMAIN,
            "set_state",
            {ATTR_ENTITY_ID: entity_id, ATTR_BRIGHTNESS_STEP: 128},
            blocking=True,
        )

        light.set_color.assert_called_once()
        color_arg = light.set_color.call_args[0][0]
        assert color_arg.brightness == pytest.approx(1.0, abs=0.02)
        assert color_arg.kelvin == 3500
        light.set_color.reset_mock()

        # brightness_step_pct should adjust brightness relative to current
        await hass.services.async_call(
            DOMAIN,
            "set_state",
            {ATTR_ENTITY_ID: entity_id, ATTR_BRIGHTNESS_STEP_PCT: 50},
            blocking=True,
        )

        light.set_color.assert_called_once()
        color_arg = light.set_color.call_args[0][0]
        assert color_arg.brightness == pytest.approx(1.0, abs=0.02)
        assert color_arg.kelvin == 3500
        light.set_color.reset_mock()


async def test_lifx_set_state_color(hass: HomeAssistant) -> None:
    """Test lifx.set_state works with color names and RGB."""
    light = _mocked_bulb()
    light.state.power = 65535
    light.state.color = HSBK(hue=175.78, saturation=0, brightness=0.49, kelvin=2700)

    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: "127.0.0.1", CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    entry.add_to_hass(hass)

    with (
        _patch_device(light),
        _patch_discovery(light),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        entity_id = "light.my_bulb"

        # brightness should convert from 8 bit to float 0-1
        await hass.services.async_call(
            DOMAIN,
            "set_state",
            {ATTR_ENTITY_ID: entity_id, ATTR_BRIGHTNESS: 255},
            blocking=True,
        )

        light.set_color.assert_called_once()
        color_arg = light.set_color.call_args[0][0]
        assert color_arg.brightness == pytest.approx(1.0, abs=0.01)
        assert color_arg.kelvin == 2700
        light.set_color.reset_mock()

        # brightness_pct should convert percentage to float 0-1
        await hass.services.async_call(
            DOMAIN,
            "set_state",
            {ATTR_ENTITY_ID: entity_id, ATTR_BRIGHTNESS_PCT: 90},
            blocking=True,
        )

        light.set_color.assert_called_once()
        color_arg = light.set_color.call_args[0][0]
        assert color_arg.brightness == pytest.approx(0.9, abs=0.01)
        light.set_color.reset_mock()

        # color name should turn into hue, saturation
        await hass.services.async_call(
            DOMAIN,
            "set_state",
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_COLOR_NAME: "red",
                ATTR_BRIGHTNESS_PCT: 100,
            },
            blocking=True,
        )

        light.set_color.assert_called_once()
        color_arg = light.set_color.call_args[0][0]
        assert color_arg.hue == pytest.approx(0, abs=1)
        assert color_arg.saturation == pytest.approx(1.0, abs=0.01)
        assert color_arg.brightness == pytest.approx(1.0, abs=0.01)
        light.set_color.reset_mock()

        # unknown color name should reset to neutral white
        await hass.services.async_call(
            DOMAIN,
            "set_state",
            {ATTR_ENTITY_ID: entity_id, ATTR_COLOR_NAME: "deepblack"},
            blocking=True,
        )

        light.set_color.assert_called_once()
        color_arg = light.set_color.call_args[0][0]
        assert color_arg.hue == pytest.approx(0, abs=1)
        assert color_arg.saturation == pytest.approx(0.0, abs=0.01)
        light.set_color.reset_mock()

        # RGB should convert to hue, saturation
        await hass.services.async_call(
            DOMAIN,
            "set_state",
            {ATTR_ENTITY_ID: entity_id, ATTR_RGB_COLOR: (0, 255, 0)},
            blocking=True,
        )

        light.set_color.assert_called_once()
        color_arg = light.set_color.call_args[0][0]
        assert color_arg.hue == pytest.approx(120, abs=1)
        assert color_arg.saturation == pytest.approx(1.0, abs=0.01)
        light.set_color.reset_mock()

        # XY should convert to hue, saturation
        await hass.services.async_call(
            DOMAIN,
            "set_state",
            {ATTR_ENTITY_ID: entity_id, ATTR_XY_COLOR: (0.34, 0.339)},
            blocking=True,
        )

        light.set_color.assert_called_once()
        color_arg = light.set_color.call_args[0][0]
        # XY (0.34, 0.339) is approximately neutral white, low saturation
        assert color_arg.saturation == pytest.approx(0.078, abs=0.05)
        light.set_color.reset_mock()


async def test_lifx_set_state_kelvin(hass: HomeAssistant) -> None:
    """Test set_state works with kelvin parameter names."""
    light = _mocked_bulb()
    light.state.power = 65535
    light.state.color = HSBK(hue=175.78, saturation=0, brightness=0.49, kelvin=6000)

    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: "127.0.0.1", CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    entry.add_to_hass(hass)

    with (
        _patch_device(light),
        _patch_discovery(light),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        entity_id = "light.my_bulb"

        state = hass.states.get(entity_id)
        assert state.state == "on"
        attributes = state.attributes
        assert attributes[ATTR_BRIGHTNESS] == 125
        assert attributes[ATTR_COLOR_MODE] == ColorMode.COLOR_TEMP

        await hass.services.async_call(
            LIGHT_DOMAIN,
            "turn_off",
            {ATTR_ENTITY_ID: entity_id},
            blocking=True,
        )
        light.set_power.assert_called()
        light.set_power.reset_mock()
        light.set_color.reset_mock()

        # Set brightness and kelvin via set_state
        await hass.services.async_call(
            DOMAIN,
            "set_state",
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_BRIGHTNESS: 100,
                ATTR_COLOR_TEMP_KELVIN: 2700,
            },
            blocking=True,
        )

        light.set_color.assert_called_once()
        color_arg = light.set_color.call_args[0][0]
        assert color_arg.brightness == pytest.approx(100 / 255, abs=0.01)
        assert color_arg.kelvin == 2700
        assert color_arg.saturation == pytest.approx(0.0, abs=0.01)
        light.set_color.reset_mock()

        # Set brightness 255 and color temp in kelvin
        await hass.services.async_call(
            DOMAIN,
            "set_state",
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_BRIGHTNESS: 255,
                ATTR_COLOR_TEMP_KELVIN: 2500,
            },
            blocking=True,
        )

        light.set_color.assert_called_once()
        color_arg = light.set_color.call_args[0][0]
        assert color_arg.brightness == pytest.approx(1.0, abs=0.01)
        assert color_arg.kelvin == 2500
        assert color_arg.saturation == pytest.approx(0.0, abs=0.01)
        light.set_color.reset_mock()


async def test_infrared_color_bulb(hass: HomeAssistant) -> None:
    """Test setting infrared with an infrared bulb via set_state service."""
    light = _mocked_infrared_bulb()
    light.state.power = 65535
    light.state.color = HSBK(hue=175.78, saturation=0, brightness=0.49, kelvin=6000)

    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: "127.0.0.1", CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    entry.add_to_hass(hass)

    with (
        _patch_device(light),
        _patch_discovery(light),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        entity_id = "light.my_bulb"

        state = hass.states.get(entity_id)
        assert state.state == "on"
        attributes = state.attributes
        assert attributes[ATTR_BRIGHTNESS] == 125
        assert attributes[ATTR_COLOR_MODE] == ColorMode.COLOR_TEMP

        await hass.services.async_call(
            LIGHT_DOMAIN,
            "turn_off",
            {ATTR_ENTITY_ID: entity_id},
            blocking=True,
        )
        light.set_power.assert_called()
        light.set_power.reset_mock()

        # Call set_state with infrared and brightness
        await hass.services.async_call(
            DOMAIN,
            "set_state",
            {
                ATTR_INFRARED: 100,
                ATTR_ENTITY_ID: entity_id,
                ATTR_BRIGHTNESS: 100,
            },
            blocking=True,
        )

        # Infrared value 100 out of 255 = approx 0.39
        light.set_infrared.assert_called_once()
        infrared_arg = light.set_infrared.call_args[0][0]
        assert infrared_arg == pytest.approx(100 / 255, abs=0.01)


async def test_clean_bulb(hass: HomeAssistant) -> None:
    """Test setting HEV cycle state on Clean bulbs."""
    light = _mocked_clean_bulb()
    light.state.power = 0
    light.state.hev_cycle.remaining_s = 0

    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: "127.0.0.1", CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    entry.add_to_hass(hass)

    with (
        _patch_device(light),
        _patch_discovery(light),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        entity_id = "light.my_bulb"
        state = hass.states.get(entity_id)
        assert state.state == "off"

        await hass.services.async_call(
            DOMAIN,
            "set_hev_cycle_state",
            {ATTR_ENTITY_ID: entity_id, ATTR_POWER: True},
            blocking=True,
        )

        light.set_hev_cycle.assert_called_once_with(True, 0)
        light.set_hev_cycle.reset_mock()


async def test_set_hev_cycle_state_fails_for_color_bulb(
    hass: HomeAssistant,
) -> None:
    """Test that set_hev_cycle_state fails for a non-Clean bulb."""
    light = _mocked_bulb()
    light.state.power = 0

    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: "127.0.0.1", CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    entry.add_to_hass(hass)

    with (
        _patch_device(light),
        _patch_discovery(light),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        entity_id = "light.my_bulb"
        state = hass.states.get(entity_id)
        assert state.state == "off"

        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                DOMAIN,
                "set_hev_cycle_state",
                {ATTR_ENTITY_ID: entity_id, ATTR_POWER: True},
                blocking=True,
            )
