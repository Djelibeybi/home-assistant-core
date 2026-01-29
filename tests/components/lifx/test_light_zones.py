"""Tests for the LIFX integration multizone light platform."""

from unittest.mock import AsyncMock, patch

from lifx import HSBK, FirmwareEffect, LifxTimeoutError
import pytest

from homeassistant.components import lifx
from homeassistant.components.lifx.const import (
    ATTR_POWER,
    ATTR_ZONES,
    CONF_SERIAL,
    DOMAIN,
)
from homeassistant.components.lifx.light import HSBK as LifxHSBK
from homeassistant.components.lifx.util import generate_hsbk
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_MODE,
    ATTR_HS_COLOR,
    ATTR_RGB_COLOR,
    ATTR_SUPPORTED_COLOR_MODES,
    ATTR_XY_COLOR,
    DOMAIN as LIGHT_DOMAIN,
    ColorMode,
)
from homeassistant.const import ATTR_ENTITY_ID, CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from . import (
    DEFAULT_ENTRY_TITLE,
    IP_ADDRESS,
    SERIAL,
    _mocked_light_strip,
    _patch_config_flow_try_connect,
    _patch_device,
    _patch_discovery,
)

from tests.common import MockConfigEntry


@pytest.fixture(autouse=True)
def patch_lifx_state_settle_delay():
    """Set asyncio.sleep for state settles to zero."""
    with patch("homeassistant.components.lifx.light.LIFX_STATE_SETTLE_DELAY", 0):
        yield


async def test_light_strip(hass: HomeAssistant) -> None:
    """Test a light strip."""
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
    light.state.color = HSBK(hue=0, saturation=1.0, brightness=1.0, kelvin=3500)
    light.state.zone_count = 8
    light.state.zones = [HSBK(hue=0, saturation=1.0, brightness=1.0, kelvin=3500)] * 8

    with (
        _patch_discovery(device=light),
        _patch_config_flow_try_connect(device=light),
        _patch_device(device=light),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

    entity_id = "light.my_bulb"

    state = hass.states.get(entity_id)
    assert state.state == "on"
    attributes = state.attributes
    assert attributes[ATTR_BRIGHTNESS] == 255
    assert attributes[ATTR_COLOR_MODE] == ColorMode.HS
    assert attributes[ATTR_SUPPORTED_COLOR_MODES] == [
        ColorMode.COLOR_TEMP,
        ColorMode.HS,
    ]
    assert attributes[ATTR_HS_COLOR] == (0, 100.0)
    assert attributes[ATTR_RGB_COLOR] == (255, 0, 0)
    assert attributes[ATTR_XY_COLOR] == (0.701, 0.299)

    with (
        _patch_device(device=light),
        _patch_discovery(device=light),
    ):
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
        # Brightness change calls set_color on the light
        light.set_color.assert_called()
        light.set_color.reset_mock()
        light.set_color_zones.assert_not_called()

        # Turn on with HS color
        await hass.services.async_call(
            LIGHT_DOMAIN,
            "turn_on",
            {ATTR_ENTITY_ID: entity_id, ATTR_HS_COLOR: (10, 30)},
            blocking=True,
        )
        # HS color change calls set_color
        light.set_color.assert_called()
        light.set_color.reset_mock()
        light.set_color_zones.assert_not_called()

        # Now set up distinct zone colors to test multizone behavior
        light.state.zones = [
            HSBK(hue=0, saturation=1.0, brightness=1.0, kelvin=3500),
            HSBK(hue=300, saturation=1.0, brightness=1.0, kelvin=3500),
            HSBK(hue=300, saturation=1.0, brightness=1.0, kelvin=3500),
            HSBK(hue=300, saturation=1.0, brightness=1.0, kelvin=3500),
            HSBK(hue=255, saturation=1.0, brightness=1.0, kelvin=3500),
            HSBK(hue=255, saturation=1.0, brightness=1.0, kelvin=3500),
            HSBK(hue=255, saturation=1.0, brightness=1.0, kelvin=3500),
            HSBK(hue=255, saturation=1.0, brightness=1.0, kelvin=3500),
        ]

        # Set HS color on all zones - color change uses set_color
        await hass.services.async_call(
            LIGHT_DOMAIN,
            "turn_on",
            {ATTR_ENTITY_ID: entity_id, ATTR_HS_COLOR: (10, 30)},
            blocking=True,
        )
        light.set_color.assert_called()
        light.set_color.reset_mock()

        # set_state service with RGB color
        await hass.services.async_call(
            DOMAIN,
            "set_state",
            {ATTR_ENTITY_ID: entity_id, ATTR_RGB_COLOR: (255, 10, 30)},
            blocking=True,
        )
        light.set_color.assert_called()
        light.set_color.reset_mock()

        # set_state service with XY color
        await hass.services.async_call(
            DOMAIN,
            "set_state",
            {ATTR_ENTITY_ID: entity_id, ATTR_XY_COLOR: (0.3, 0.7)},
            blocking=True,
        )
        light.set_color.assert_called()
        light.set_color.reset_mock()

        # set_state service with brightness only (adjusts brightness on the color)
        await hass.services.async_call(
            DOMAIN,
            "set_state",
            {ATTR_ENTITY_ID: entity_id, ATTR_BRIGHTNESS: 128},
            blocking=True,
        )
        light.set_color.assert_called()
        light.set_color.reset_mock()

        # set_state service with RGB color and specific zones
        await hass.services.async_call(
            DOMAIN,
            "set_state",
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_RGB_COLOR: (255, 255, 255),
                ATTR_ZONES: [0, 2],
            },
            blocking=True,
        )
        # When zones are specified on extended multizone, set_extended_color_zones is called
        light.set_extended_color_zones.assert_called()
        # Should update zones 0, 1, 2 with new color and send all zones
        call_args = light.set_extended_color_zones.call_args
        assert len(call_args.kwargs["colors"]) == 8  # All 8 zones sent
        light.set_color.assert_not_called()
        light.set_color_zones.assert_not_called()
        light.set_extended_color_zones.reset_mock()

        # set_state with out-of-range zones (ignore invalid indices)
        light.state.zones = [
            HSBK(hue=0, saturation=1.0, brightness=1.0, kelvin=3500),
            HSBK(hue=30, saturation=1.0, brightness=1.0, kelvin=3500),
            HSBK(hue=60, saturation=1.0, brightness=1.0, kelvin=3500),
            HSBK(hue=90, saturation=1.0, brightness=1.0, kelvin=3500),
            HSBK(hue=120, saturation=1.0, brightness=1.0, kelvin=3500),
            HSBK(hue=150, saturation=1.0, brightness=1.0, kelvin=3500),
            HSBK(hue=180, saturation=1.0, brightness=1.0, kelvin=3500),
            HSBK(hue=210, saturation=1.0, brightness=1.0, kelvin=3500),
        ]
        original_zones = list(light.state.zones)
        await hass.services.async_call(
            DOMAIN,
            "set_state",
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_RGB_COLOR: (0, 255, 0),
                ATTR_ZONES: [0, 9],
            },
            blocking=True,
        )
        light.set_extended_color_zones.assert_called_once()
        colors = light.set_extended_color_zones.call_args.kwargs["colors"]
        expected = generate_hsbk(
            light.state.color, True, **{ATTR_RGB_COLOR: (0, 255, 0)}
        )
        assert colors[0] == expected
        assert colors[1:] == original_zones[1:]
        light.set_extended_color_zones.reset_mock()

        # set_state with only out-of-range zones should no-op
        light.set_color.reset_mock()
        light.set_color_zones.reset_mock()
        light.set_extended_color_zones.reset_mock()
        await hass.services.async_call(
            DOMAIN,
            "set_state",
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_RGB_COLOR: (0, 0, 255),
                ATTR_ZONES: [99],
            },
            blocking=True,
        )
        light.set_extended_color_zones.assert_not_called()
        light.set_color.assert_not_called()
        light.set_color_zones.assert_not_called()

        # set_state with zones on a powered-off light (no power parameter)
        light.set_power.reset_mock()
        light.set_extended_color_zones.reset_mock()
        light.state.power = 0

        await hass.services.async_call(
            DOMAIN,
            "set_state",
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_RGB_COLOR: (255, 255, 255),
                ATTR_ZONES: [3],
            },
            blocking=True,
        )
        # set_state without power should not turn on the light
        light.set_power.assert_not_called()
        # Zone [3] uses extended multizone to update just zone 3
        light.set_extended_color_zones.assert_called()
        call_args = light.set_extended_color_zones.call_args
        assert len(call_args.kwargs["colors"]) == 8  # All zones sent
        light.set_power.reset_mock()
        light.set_extended_color_zones.reset_mock()

        # set_state with zones on a powered-off light (power: true)
        await hass.services.async_call(
            DOMAIN,
            "set_state",
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_RGB_COLOR: (255, 255, 255),
                ATTR_ZONES: [3],
                ATTR_POWER: True,
            },
            blocking=True,
        )
        # set_state with power should turn on the light
        light.set_power.assert_called()
        light.set_extended_color_zones.assert_called()
        light.set_power.reset_mock()
        light.set_extended_color_zones.reset_mock()
        light.state.power = 65535

        # Verify error handling: set_extended_color_zones raises timeout
        light.set_extended_color_zones = AsyncMock(
            side_effect=LifxTimeoutError("timeout")
        )

        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                DOMAIN,
                "set_state",
                {
                    ATTR_ENTITY_ID: entity_id,
                    ATTR_RGB_COLOR: (255, 255, 255),
                    ATTR_ZONES: [3],
                },
                blocking=True,
            )


async def test_zone_grouping(hass: HomeAssistant) -> None:
    """Test that zones are correctly grouped into contiguous ranges."""
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
    light.state.color = HSBK(hue=0, saturation=1.0, brightness=1.0, kelvin=3500)
    light.state.zone_count = 16
    light.state.zones = [HSBK(hue=0, saturation=1.0, brightness=1.0, kelvin=3500)] * 16

    with (
        _patch_discovery(device=light),
        _patch_config_flow_try_connect(device=light),
        _patch_device(device=light),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

    entity_id = "light.my_bulb"

    with (
        _patch_device(device=light),
        _patch_discovery(device=light),
    ):
        # Test multiple non-contiguous groups: [0, 2, 3, 4, 7, 10, 11]
        # With extended multizone, updates all zones in one call
        light.set_extended_color_zones = AsyncMock()

        await hass.services.async_call(
            DOMAIN,
            "set_state",
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_RGB_COLOR: (255, 128, 0),
                ATTR_ZONES: [0, 2, 3, 4, 7, 10, 11],
            },
            blocking=True,
        )

        # Should use extended multizone (one call with all zones)
        light.set_extended_color_zones.assert_called()
        call_args = light.set_extended_color_zones.call_args
        assert len(call_args.kwargs["colors"]) == 16  # All 16 zones sent

        # Test with duplicates: [1, 1, 3, 3, 5, 6, 6]
        # Should deduplicate and update zones 1, 3, 5, 6
        light.set_extended_color_zones.reset_mock()

        await hass.services.async_call(
            DOMAIN,
            "set_state",
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_RGB_COLOR: (0, 255, 128),
                ATTR_ZONES: [1, 1, 3, 3, 5, 6, 6],
            },
            blocking=True,
        )

        light.set_extended_color_zones.assert_called()
        call_args = light.set_extended_color_zones.call_args
        assert len(call_args.kwargs["colors"]) == 16

        # Test unsorted input: [15, 0, 8, 9, 5]
        # Should update zones 0, 5, 8, 9, 15
        light.set_extended_color_zones.reset_mock()

        await hass.services.async_call(
            DOMAIN,
            "set_state",
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_RGB_COLOR: (128, 0, 255),
                ATTR_ZONES: [15, 0, 8, 9, 5],
            },
            blocking=True,
        )

        light.set_extended_color_zones.assert_called()
        call_args = light.set_extended_color_zones.call_args
        assert len(call_args.kwargs["colors"]) == 16

        # Test all contiguous zones: [0, 1, 2, 3, 4, 5]
        # Should update all specified zones
        light.set_extended_color_zones.reset_mock()

        await hass.services.async_call(
            DOMAIN,
            "set_state",
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_RGB_COLOR: (255, 255, 0),
                ATTR_ZONES: [0, 1, 2, 3, 4, 5],
            },
            blocking=True,
        )

        light.set_extended_color_zones.assert_called()
        call_args = light.set_extended_color_zones.call_args
        assert len(call_args.kwargs["colors"]) == 16


async def test_extended_multizone_messages(hass: HomeAssistant) -> None:
    """Test a light strip that supports extended multizone."""
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
    light.state.color = HSBK(hue=0, saturation=1.0, brightness=1.0, kelvin=3500)
    light.state.zone_count = 8
    light.state.zones = [HSBK(hue=0, saturation=1.0, brightness=1.0, kelvin=3500)] * 8
    light.state.effect = FirmwareEffect.OFF

    with (
        _patch_discovery(device=light),
        _patch_config_flow_try_connect(device=light),
        _patch_device(device=light),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

    entity_id = "light.my_bulb"

    state = hass.states.get(entity_id)
    assert state.state == "on"
    attributes = state.attributes
    assert attributes[ATTR_BRIGHTNESS] == 255
    assert attributes[ATTR_COLOR_MODE] == ColorMode.HS
    assert attributes[ATTR_SUPPORTED_COLOR_MODES] == [
        ColorMode.COLOR_TEMP,
        ColorMode.HS,
    ]
    assert attributes[ATTR_HS_COLOR] == (0, 100.0)
    assert attributes[ATTR_RGB_COLOR] == (255, 0, 0)
    assert attributes[ATTR_XY_COLOR] == (0.701, 0.299)

    with (
        _patch_device(device=light),
        _patch_discovery(device=light),
    ):
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

        # Turn on with brightness - uses set_color to apply brightness
        await hass.services.async_call(
            LIGHT_DOMAIN,
            "turn_on",
            {ATTR_ENTITY_ID: entity_id, ATTR_BRIGHTNESS: 100},
            blocking=True,
        )
        light.set_color.assert_called()
        light.set_color.reset_mock()
        # Extended multizone does not use set_color_zones for simple color changes
        light.set_color_zones.assert_not_called()

        # Turn on with HS color
        await hass.services.async_call(
            LIGHT_DOMAIN,
            "turn_on",
            {ATTR_ENTITY_ID: entity_id, ATTR_HS_COLOR: (10, 30)},
            blocking=True,
        )
        light.set_color.assert_called()
        light.set_color.reset_mock()
        light.set_color_zones.assert_not_called()
        light.set_extended_color_zones.assert_not_called()

        # Set up distinct zone colors
        light.state.zones = [
            HSBK(hue=0, saturation=1.0, brightness=1.0, kelvin=3500),
            HSBK(hue=300, saturation=1.0, brightness=1.0, kelvin=3500),
            HSBK(hue=300, saturation=1.0, brightness=1.0, kelvin=3500),
            HSBK(hue=300, saturation=1.0, brightness=1.0, kelvin=3500),
            HSBK(hue=255, saturation=1.0, brightness=1.0, kelvin=3500),
            HSBK(hue=255, saturation=1.0, brightness=1.0, kelvin=3500),
            HSBK(hue=255, saturation=1.0, brightness=1.0, kelvin=3500),
            HSBK(hue=255, saturation=1.0, brightness=1.0, kelvin=3500),
        ]

        # HS color with distinct zones
        await hass.services.async_call(
            LIGHT_DOMAIN,
            "turn_on",
            {ATTR_ENTITY_ID: entity_id, ATTR_HS_COLOR: (10, 30)},
            blocking=True,
        )
        light.set_color.assert_called()
        light.set_color.reset_mock()
        light.set_color_zones.assert_not_called()
        light.set_extended_color_zones.assert_not_called()

        # set_state with RGB color
        await hass.services.async_call(
            DOMAIN,
            "set_state",
            {ATTR_ENTITY_ID: entity_id, ATTR_RGB_COLOR: (255, 10, 30)},
            blocking=True,
        )
        light.set_color.assert_called()
        light.set_color.reset_mock()
        light.set_color_zones.assert_not_called()
        light.set_extended_color_zones.assert_not_called()

        # set_state with XY color
        light.state.zones = [
            HSBK(hue=0, saturation=1.0, brightness=1.0, kelvin=3500),
            HSBK(hue=300, saturation=1.0, brightness=1.0, kelvin=3500),
            HSBK(hue=300, saturation=1.0, brightness=1.0, kelvin=3500),
            HSBK(hue=300, saturation=1.0, brightness=1.0, kelvin=3500),
            HSBK(hue=255, saturation=1.0, brightness=1.0, kelvin=3500),
            HSBK(hue=255, saturation=1.0, brightness=1.0, kelvin=3500),
            HSBK(hue=255, saturation=1.0, brightness=1.0, kelvin=3500),
            HSBK(hue=255, saturation=1.0, brightness=1.0, kelvin=3500),
        ]

        await hass.services.async_call(
            DOMAIN,
            "set_state",
            {ATTR_ENTITY_ID: entity_id, ATTR_XY_COLOR: (0.3, 0.7)},
            blocking=True,
        )
        light.set_color.assert_called()
        light.set_color.reset_mock()
        light.set_color_zones.assert_not_called()
        light.set_extended_color_zones.assert_not_called()

        # set_state with brightness only
        light.state.zones = [
            HSBK(hue=0, saturation=1.0, brightness=1.0, kelvin=3500),
            HSBK(hue=300, saturation=1.0, brightness=1.0, kelvin=3500),
            HSBK(hue=300, saturation=1.0, brightness=1.0, kelvin=3500),
            HSBK(hue=300, saturation=1.0, brightness=1.0, kelvin=3500),
            HSBK(hue=255, saturation=1.0, brightness=1.0, kelvin=3500),
            HSBK(hue=255, saturation=1.0, brightness=1.0, kelvin=3500),
            HSBK(hue=255, saturation=1.0, brightness=1.0, kelvin=3500),
            HSBK(hue=255, saturation=1.0, brightness=1.0, kelvin=3500),
        ]

        await hass.services.async_call(
            DOMAIN,
            "set_state",
            {ATTR_ENTITY_ID: entity_id, ATTR_BRIGHTNESS: 128},
            blocking=True,
        )
        light.set_color.assert_called()
        light.set_color.reset_mock()
        light.set_color_zones.assert_not_called()
        light.set_extended_color_zones.assert_not_called()

        # set_state with RGB color and specific zones
        await hass.services.async_call(
            DOMAIN,
            "set_state",
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_RGB_COLOR: (255, 255, 255),
                ATTR_ZONES: [0, 2],
            },
            blocking=True,
        )
        # When zones are specified on extended multizone, uses extended messages
        light.set_extended_color_zones.assert_called()
        assert len(light.set_extended_color_zones.call_args.kwargs["colors"]) == 8
        light.set_color.assert_not_called()
        light.set_color_zones.assert_not_called()
        light.set_extended_color_zones.reset_mock()

        # set_state with zones on a powered-off light (no power parameter)
        light.set_power.reset_mock()
        light.set_extended_color_zones.reset_mock()
        light.state.power = 0

        await hass.services.async_call(
            DOMAIN,
            "set_state",
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_RGB_COLOR: (255, 255, 255),
                ATTR_ZONES: [3],
            },
            blocking=True,
        )
        # set_state without power should not turn on the light
        light.set_power.assert_not_called()
        # Zone [3] uses extended multizone
        light.set_extended_color_zones.assert_called()
        assert len(light.set_extended_color_zones.call_args.kwargs["colors"]) == 8
        light.set_power.reset_mock()
        light.set_extended_color_zones.reset_mock()

        # Error handling: set_extended_color_zones raises timeout
        light.state.power = 65535
        light.set_extended_color_zones = AsyncMock(
            side_effect=LifxTimeoutError("timeout")
        )

        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                DOMAIN,
                "set_state",
                {
                    ATTR_ENTITY_ID: entity_id,
                    ATTR_RGB_COLOR: (255, 255, 255),
                    ATTR_ZONES: [3],
                },
                blocking=True,
            )


async def test_legacy_multizone_light(hass: HomeAssistant) -> None:
    """Test a legacy multizone light strip (without extended multizone support)."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    # Create a legacy light strip without extended multizone support
    light = _mocked_light_strip()
    light.state.capabilities.has_extended_multizone = False
    light.capabilities.has_extended_multizone = False
    light.state.power = 65535
    light.state.color = HSBK(hue=0, saturation=1.0, brightness=1.0, kelvin=3500)
    light.state.zone_count = 8
    light.state.zones = [HSBK(hue=0, saturation=1.0, brightness=1.0, kelvin=3500)] * 8

    with (
        _patch_discovery(device=light),
        _patch_config_flow_try_connect(device=light),
        _patch_device(device=light),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

    entity_id = "light.my_bulb"

    with (
        _patch_device(device=light),
        _patch_discovery(device=light),
    ):
        # Test with two non-contiguous zones [0, 2]
        await hass.services.async_call(
            DOMAIN,
            "set_state",
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_RGB_COLOR: (255, 255, 255),
                ATTR_ZONES: [0, 2],
            },
            blocking=True,
        )
        # Legacy devices use set_color_zones, not set_extended_color_zones
        assert light.set_color_zones.call_count == 2
        first_call = light.set_color_zones.call_args_list[0]
        second_call = light.set_color_zones.call_args_list[1]
        assert first_call.kwargs["start"] == 0
        assert first_call.kwargs["end"] == 0
        assert second_call.kwargs["start"] == 2
        assert second_call.kwargs["end"] == 2
        light.set_extended_color_zones.assert_not_called()
        light.set_color_zones.reset_mock()

        # Test with non-contiguous zones [0, 2, 5, 7]
        # Should group into ranges: [0], [2], [5], [7]
        await hass.services.async_call(
            DOMAIN,
            "set_state",
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_RGB_COLOR: (255, 128, 0),
                ATTR_ZONES: [0, 2, 5, 7],
            },
            blocking=True,
        )
        # Should call set_color_zones 4 times (one for each zone)
        assert light.set_color_zones.call_count == 4
        light.set_extended_color_zones.assert_not_called()
        light.set_color_zones.reset_mock()

        # Test with contiguous zones [1, 2, 3, 4]
        # Should group into one range: [1-4]
        await hass.services.async_call(
            DOMAIN,
            "set_state",
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_RGB_COLOR: (0, 255, 128),
                ATTR_ZONES: [1, 2, 3, 4],
            },
            blocking=True,
        )
        # Should call set_color_zones once with range 1-4
        assert light.set_color_zones.call_count == 1
        call_args = light.set_color_zones.call_args
        assert call_args.kwargs["start"] == 1
        assert call_args.kwargs["end"] == 4
        light.set_extended_color_zones.assert_not_called()
        light.set_color_zones.reset_mock()

        # Test with mixed contiguous and non-contiguous zones [0, 1, 2, 5, 6, 9]
        # Should group into ranges: [0-2], [5-6] (zone 9 out of range)
        await hass.services.async_call(
            DOMAIN,
            "set_state",
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_RGB_COLOR: (128, 0, 255),
                ATTR_ZONES: [0, 1, 2, 5, 6, 9],
            },
            blocking=True,
        )
        # Should call set_color_zones 2 times
        assert light.set_color_zones.call_count == 2
        light.set_extended_color_zones.assert_not_called()
        light.set_color_zones.reset_mock()

        # Test with out-of-range zones [2, 20]
        await hass.services.async_call(
            DOMAIN,
            "set_state",
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_RGB_COLOR: (0, 128, 255),
                ATTR_ZONES: [2, 20],
            },
            blocking=True,
        )
        # Should clamp to valid zone 2 only
        assert light.set_color_zones.call_count == 1
        call_args = light.set_color_zones.call_args
        assert call_args.kwargs["start"] == 2
        assert call_args.kwargs["end"] == 2
        light.set_extended_color_zones.assert_not_called()
        light.set_color_zones.reset_mock()

        # Test when zone_count is missing and zones are out of range
        light.state.zone_count = None
        await hass.services.async_call(
            DOMAIN,
            "set_state",
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_RGB_COLOR: (0, 0, 255),
                ATTR_ZONES: [20],
            },
            blocking=True,
        )
        light.set_color_zones.assert_not_called()
        light.set_extended_color_zones.assert_not_called()
        light.state.zone_count = 8

        # Test with empty zones list - should not call anything
        await hass.services.async_call(
            DOMAIN,
            "set_state",
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_RGB_COLOR: (255, 255, 0),
                ATTR_ZONES: [],
            },
            blocking=True,
        )
        # Empty zones should result in no zone-specific calls
        light.set_color_zones.assert_not_called()
        light.set_extended_color_zones.assert_not_called()
        # Should call set_color instead (no zones specified)
        light.set_color.assert_called()


async def test_zones_on_powered_off_light_without_power_flag(
    hass: HomeAssistant,
) -> None:
    """Test setting zones on a powered-off light without explicit power flag."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    light = _mocked_light_strip()
    light.state.power = 0  # Light is off
    # Set initial color to white (0 hue, 0 saturation)
    light.state.color = HSBK(hue=0, saturation=0.0, brightness=1.0, kelvin=3500)
    light.state.zone_count = 8
    light.state.zones = [HSBK(hue=0, saturation=0.0, brightness=1.0, kelvin=3500)] * 8

    with (
        _patch_discovery(device=light),
        _patch_config_flow_try_connect(device=light),
        _patch_device(device=light),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

    entity_id = "light.my_bulb"

    with (
        _patch_device(device=light),
        _patch_discovery(device=light),
    ):
        # Set the same color on zones (no color change, just zone update)
        # This hits the elif color: path without turning on the light
        await hass.services.async_call(
            DOMAIN,
            "set_state",
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_RGB_COLOR: (255, 255, 255),  # White (same as current)
                ATTR_ZONES: [0, 2],
            },
            blocking=True,
        )
        # Should call set_extended_color_zones to set zone colors
        light.set_extended_color_zones.assert_called()
        # Should not turn on the light (no power command for same color)
        light.set_power.assert_not_called()


async def test_empty_zones_list_edge_case(hass: HomeAssistant) -> None:
    """Test that empty zones list is handled gracefully."""
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
    light.state.color = HSBK(hue=0, saturation=1.0, brightness=1.0, kelvin=3500)
    light.state.zone_count = 8
    light.state.zones = [HSBK(hue=0, saturation=1.0, brightness=1.0, kelvin=3500)] * 8

    with (
        _patch_discovery(device=light),
        _patch_config_flow_try_connect(device=light),
        _patch_device(device=light),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

    entity_id = "light.my_bulb"

    with (
        _patch_device(device=light),
        _patch_discovery(device=light),
    ):
        # Get the light entity to call _async_set_zones_color directly
        state = hass.states.get(entity_id)
        assert state is not None

        # Get the entity from the registry
        entity_reg = er.async_get(hass)
        entity_entry = entity_reg.async_get(entity_id)
        assert entity_entry is not None

        # Get the light entity
        light_entity = hass.data["light"].get_entity(entity_id)
        assert light_entity is not None

        # Call _async_set_zones_color with empty list directly
        # This tests the defensive early return at line 241
        color = LifxHSBK(hue=0, saturation=0, brightness=1.0, kelvin=3500)
        await light_entity._async_set_zones_color([], color, 0.0)

        # Should return early without calling any zone methods
        light.set_extended_color_zones.assert_not_called()
        light.set_color_zones.assert_not_called()


async def test_legacy_multizone_error_handling(hass: HomeAssistant) -> None:
    """Test error handling for legacy multizone set_color_zones."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    # Create a legacy light strip without extended multizone support
    light = _mocked_light_strip()
    light.state.capabilities.has_extended_multizone = False
    light.capabilities.has_extended_multizone = False
    light.state.power = 65535
    light.state.color = HSBK(hue=0, saturation=1.0, brightness=1.0, kelvin=3500)
    light.state.zone_count = 8
    light.state.zones = [HSBK(hue=0, saturation=1.0, brightness=1.0, kelvin=3500)] * 8

    with (
        _patch_discovery(device=light),
        _patch_config_flow_try_connect(device=light),
        _patch_device(device=light),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

    entity_id = "light.my_bulb"

    with (
        _patch_device(device=light),
        _patch_discovery(device=light),
    ):
        # Make set_color_zones raise a timeout error
        light.set_color_zones = AsyncMock(side_effect=LifxTimeoutError("timeout"))

        # Try to set zones - should raise HomeAssistantError
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                DOMAIN,
                "set_state",
                {
                    ATTR_ENTITY_ID: entity_id,
                    ATTR_RGB_COLOR: (255, 255, 255),
                    ATTR_ZONES: [0, 2],
                },
                blocking=True,
            )
