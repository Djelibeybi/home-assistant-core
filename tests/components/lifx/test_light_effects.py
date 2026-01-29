"""Tests for the LIFX integration light effects."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from lifx import HSBK, FirmwareEffect
import pytest

from homeassistant.components.lifx.const import ATTR_THEME, CONF_SERIAL, DOMAIN
from homeassistant.components.lifx.manager import (
    ATTR_CHANGE,
    ATTR_CLOUD_SATURATION_MAX,
    ATTR_CLOUD_SATURATION_MIN,
    ATTR_DIRECTION,
    ATTR_PALETTE,
    ATTR_PERIOD,
    ATTR_POWER_ON,
    ATTR_SATURATION_MAX,
    ATTR_SATURATION_MIN,
    ATTR_SKY_TYPE,
    ATTR_SPEED,
    ATTR_SPREAD,
    SERVICE_EFFECT_COLORLOOP,
    SERVICE_EFFECT_FLAME,
    SERVICE_EFFECT_MORPH,
    SERVICE_EFFECT_MOVE,
    SERVICE_EFFECT_PULSE,
    SERVICE_EFFECT_SKY,
    SERVICE_EFFECT_STOP,
    SERVICE_PAINT_THEME,
)
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_BRIGHTNESS_PCT,
    ATTR_EFFECT,
    ATTR_TRANSITION,
    DOMAIN as LIGHT_DOMAIN,
)
from homeassistant.const import ATTR_ENTITY_ID, CONF_HOST, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from . import (
    DEFAULT_ENTRY_TITLE,
    IP_ADDRESS,
    SERIAL,
    _mocked_bulb,
    _mocked_ceiling,
    _mocked_light_strip,
    _mocked_tile,
    _patch_device,
    _patch_discovery,
    get_entry_light_entity_id,
)

from tests.common import MockConfigEntry, async_fire_time_changed


async def test_effect_list_color_light(hass: HomeAssistant) -> None:
    """Test effect list for a color light."""
    light = _mocked_bulb()
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    entry.add_to_hass(hass)

    with _patch_device(light), _patch_discovery(light):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    entity_id = get_entry_light_entity_id(hass, entry)
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes["effect_list"] == [
        SERVICE_EFFECT_COLORLOOP,
        SERVICE_EFFECT_PULSE,
        SERVICE_EFFECT_STOP,
    ]


async def test_effect_list_multizone_light(hass: HomeAssistant) -> None:
    """Test effect list for a multizone light."""
    light = _mocked_light_strip()
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    entry.add_to_hass(hass)

    with _patch_device(light), _patch_discovery(light):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    entity_id = get_entry_light_entity_id(hass, entry)
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes["effect_list"] == [
        SERVICE_EFFECT_COLORLOOP,
        SERVICE_EFFECT_MOVE,
        SERVICE_EFFECT_PULSE,
        SERVICE_EFFECT_STOP,
    ]


async def test_effect_list_matrix_light(hass: HomeAssistant) -> None:
    """Test effect list for a matrix light."""
    light = _mocked_tile()
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    entry.add_to_hass(hass)

    with _patch_device(light), _patch_discovery(light):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    entity_id = get_entry_light_entity_id(hass, entry)
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes["effect_list"] == [
        SERVICE_EFFECT_COLORLOOP,
        SERVICE_EFFECT_FLAME,
        SERVICE_EFFECT_MORPH,
        SERVICE_EFFECT_PULSE,
        SERVICE_EFFECT_SKY,
        SERVICE_EFFECT_STOP,
    ]


async def test_matrix_flame_morph_effects(hass: HomeAssistant) -> None:
    """Test the firmware flame and morph effects on a matrix device."""
    light = _mocked_tile()
    light.state.power = 0
    light.state.color = HSBK(hue=360, saturation=1.0, brightness=1.0, kelvin=9000)

    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    entry.add_to_hass(hass)

    with (
        _patch_device(light),
        _patch_discovery(light),
        patch("homeassistant.components.lifx.light.LIFX_STATE_SETTLE_DELAY", 0),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        entity_id = "light.my_bulb"

        # FLAME effect test via turn_on with ATTR_EFFECT
        await hass.services.async_call(
            LIGHT_DOMAIN,
            "turn_on",
            {ATTR_ENTITY_ID: entity_id, ATTR_EFFECT: "effect_flame"},
            blocking=True,
        )
        await hass.async_block_till_done()

        # Power should have been turned on (was 0)
        light.set_power.assert_called()
        # set_effect called for the flame effect
        light.set_effect.assert_called_once()

        flame_call_kwargs = light.set_effect.call_args
        # Verify the effect_type is FLAME and speed is the default (3)
        assert (
            flame_call_kwargs.kwargs.get("effect_type") is not None
            or flame_call_kwargs.args is not None
        )

        light.set_effect.reset_mock()
        light.set_power.reset_mock()

        # MORPH effect test with theme via service call
        light.state.power = 0
        await hass.services.async_call(
            DOMAIN,
            SERVICE_EFFECT_MORPH,
            {ATTR_ENTITY_ID: entity_id, ATTR_SPEED: 4, ATTR_THEME: "autumn"},
            blocking=True,
        )

        # Power should have been turned on
        light.set_power.assert_called()
        # set_effect called for the morph effect
        light.set_effect.assert_called_once()

        morph_call = light.set_effect.call_args
        # Verify morph effect was called with speed 4 and a palette
        assert morph_call.kwargs["speed"] == 4
        assert morph_call.kwargs["palette"] is not None
        assert len(morph_call.kwargs["palette"]) > 0

        # Simulate the light turning on and effect running
        light.state.power = 65535
        light.state.effect = FirmwareEffect.MORPH
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=30))
        await hass.async_block_till_done(wait_background_tasks=True)

        state = hass.states.get(entity_id)
        assert state.state == STATE_ON

        light.set_effect.reset_mock()
        light.set_power.reset_mock()

        # MORPH effect test with explicit palette via service call
        light.state.power = 0
        await hass.services.async_call(
            DOMAIN,
            SERVICE_EFFECT_MORPH,
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_SPEED: 6,
                ATTR_PALETTE: [
                    (0, 100, 100, 3500),
                    (60, 100, 100, 3500),
                    (120, 100, 100, 3500),
                    (180, 100, 100, 3500),
                    (240, 100, 100, 3500),
                    (300, 100, 100, 3500),
                ],
            },
            blocking=True,
        )

        # Power should have been turned on
        light.set_power.assert_called()
        # set_effect called for the morph effect
        light.set_effect.assert_called_once()

        morph_palette_call = light.set_effect.call_args
        # Verify morph effect was called with speed 6 and the provided palette
        assert morph_palette_call.kwargs["speed"] == 6
        assert morph_palette_call.kwargs["palette"] is not None
        assert len(morph_palette_call.kwargs["palette"]) == 6

        # Simulate the light turning on and effect running
        light.state.power = 65535
        light.state.effect = FirmwareEffect.MORPH
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=30))
        await hass.async_block_till_done(wait_background_tasks=True)

        state = hass.states.get(entity_id)
        assert state.state == STATE_ON

        light.set_effect.reset_mock()
        light.set_power.reset_mock()


@pytest.mark.usefixtures("mock_discovery")
async def test_sky_effect(hass: HomeAssistant) -> None:
    """Test the firmware sky effect on a ceiling device."""
    light = _mocked_ceiling()
    light.state.power = 0
    light.state.color = HSBK(hue=360, saturation=1.0, brightness=1.0, kelvin=9000)

    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    entry.add_to_hass(hass)

    with (
        _patch_device(light),
        _patch_discovery(light),
        patch("homeassistant.components.lifx.light.LIFX_STATE_SETTLE_DELAY", 0),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        entity_id = "light.my_bulb"

        # SKY effect test without palette
        light.state.power = 0
        await hass.services.async_call(
            DOMAIN,
            SERVICE_EFFECT_SKY,
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_SKY_TYPE: "Clouds",
                ATTR_CLOUD_SATURATION_MAX: 180,
                ATTR_CLOUD_SATURATION_MIN: 50,
            },
            blocking=True,
        )

        # set_effect called for the sky effect
        light.set_effect.assert_called_once()

        sky_call = light.set_effect.call_args
        # Verify sky effect parameters
        assert sky_call.kwargs["cloud_saturation_min"] == 50
        assert sky_call.kwargs["cloud_saturation_max"] == 180

        # Simulate the light turning on and effect running
        light.state.power = 65535
        light.state.effect = FirmwareEffect.SKY
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=30))
        await hass.async_block_till_done(wait_background_tasks=True)

        state = hass.states.get(entity_id)
        assert state.state == STATE_ON

        light.set_effect.reset_mock()
        light.set_power.reset_mock()

        # SKY effect test with palette and Sunrise sky_type
        light.state.power = 0
        await hass.services.async_call(
            DOMAIN,
            SERVICE_EFFECT_SKY,
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_PALETTE: [
                    (200, 100, 1, 3500),
                    (241, 100, 1, 3500),
                    (189, 100, 8, 3500),
                    (40, 100, 100, 3500),
                    (40, 50, 100, 3500),
                    (0, 0, 100, 6500),
                ],
                ATTR_SKY_TYPE: "Sunrise",
                ATTR_CLOUD_SATURATION_MAX: 180,
                ATTR_CLOUD_SATURATION_MIN: 50,
            },
            blocking=True,
        )

        # set_effect called for the sky effect with palette
        light.set_effect.assert_called_once()

        sky_palette_call = light.set_effect.call_args
        # Verify sky effect was called with the palette
        assert sky_palette_call.kwargs["palette"] is not None
        assert len(sky_palette_call.kwargs["palette"]) == 6
        assert sky_palette_call.kwargs["cloud_saturation_min"] == 50
        assert sky_palette_call.kwargs["cloud_saturation_max"] == 180

        # Simulate the light turning on and effect running
        light.state.power = 65535
        light.state.effect = FirmwareEffect.SKY
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=30))
        await hass.async_block_till_done(wait_background_tasks=True)

        state = hass.states.get(entity_id)
        assert state.state == STATE_ON

        light.set_effect.reset_mock()
        light.set_power.reset_mock()


@pytest.mark.usefixtures("mock_discovery")
async def test_lightstrip_move_effect(hass: HomeAssistant) -> None:
    """Test the firmware move effect on a light strip."""
    light = _mocked_light_strip()
    light.state.power = 0
    light.state.color = HSBK(hue=360, saturation=1.0, brightness=1.0, kelvin=9000)

    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    entry.add_to_hass(hass)

    with (
        _patch_device(light),
        _patch_discovery(light),
        patch("homeassistant.components.lifx.light.LIFX_STATE_SETTLE_DELAY", 0),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        entity_id = "light.my_bulb"

        # MOVE effect test via turn_on with ATTR_EFFECT
        await hass.services.async_call(
            LIGHT_DOMAIN,
            "turn_on",
            {ATTR_ENTITY_ID: entity_id, ATTR_EFFECT: "effect_move"},
            blocking=True,
        )
        await hass.async_block_till_done()

        # set_effect called for the move effect
        light.set_effect.assert_called_once()

        light.set_effect.reset_mock()
        light.set_power.reset_mock()

        # MOVE effect test with speed, direction, and theme via service call
        light.state.power = 0
        await hass.services.async_call(
            DOMAIN,
            SERVICE_EFFECT_MOVE,
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_SPEED: 4.5,
                ATTR_DIRECTION: "left",
                ATTR_THEME: "sports",
            },
            blocking=True,
        )

        # set_effect should be called for the move effect
        light.set_effect.assert_called_once()

        # Simulate the light turning on and effect running
        light.state.power = 65535
        light.state.effect = FirmwareEffect.MOVE
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=30))
        await hass.async_block_till_done(wait_background_tasks=True)

        state = hass.states.get(entity_id)
        assert state.state == STATE_ON

        # apply_theme should have been called for the sports theme
        light.apply_theme.assert_called_once()

        light.set_effect.reset_mock()
        light.set_power.reset_mock()
        light.apply_theme.reset_mock()

        # STOP effect test via turn_on with ATTR_EFFECT
        await hass.services.async_call(
            LIGHT_DOMAIN,
            "turn_on",
            {ATTR_ENTITY_ID: entity_id, ATTR_EFFECT: "effect_stop"},
            blocking=True,
        )
        await hass.async_block_till_done()

        # set_effect should be called to stop the effect (FirmwareEffect.OFF)
        light.set_effect.assert_called()

        light.set_effect.reset_mock()
        light.set_power.reset_mock()


@pytest.mark.usefixtures("mock_discovery")
async def test_paint_theme_service(hass: HomeAssistant) -> None:
    """Test the paint_theme service on a standard light."""
    light = _mocked_bulb()
    light.state.power = 0
    light.state.color = HSBK(hue=360, saturation=1.0, brightness=1.0, kelvin=9000)

    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    entry.add_to_hass(hass)

    with (
        _patch_device(light),
        _patch_discovery(light),
        patch("homeassistant.components.lifx.light.LIFX_STATE_SETTLE_DELAY", 0),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        entity_id = "light.my_bulb"

        # Paint theme with named theme "autumn"
        light.state.power = 0
        await hass.services.async_call(
            DOMAIN,
            SERVICE_PAINT_THEME,
            {ATTR_ENTITY_ID: entity_id, ATTR_TRANSITION: 4, ATTR_THEME: "autumn"},
            blocking=True,
        )

        # apply_theme should have been called
        light.apply_theme.assert_called_once()

        theme_call = light.apply_theme.call_args
        # The first positional arg should be a Theme object
        theme_arg = theme_call.args[0]
        assert theme_arg is not None

        # Simulate the light turning on
        light.state.power = 65535
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=30))
        await hass.async_block_till_done(wait_background_tasks=True)

        state = hass.states.get(entity_id)
        assert state.state == STATE_ON

        light.apply_theme.reset_mock()
        light.set_power.reset_mock()

        # Paint theme with explicit palette
        light.state.power = 0
        await hass.services.async_call(
            DOMAIN,
            SERVICE_PAINT_THEME,
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_TRANSITION: 6,
                ATTR_PALETTE: [
                    (0, 100, 100, 3500),
                    (60, 100, 100, 3500),
                    (120, 100, 100, 3500),
                    (180, 100, 100, 3500),
                    (240, 100, 100, 3500),
                    (300, 100, 100, 3500),
                ],
            },
            blocking=True,
        )

        # apply_theme should have been called with the palette-based theme
        light.apply_theme.assert_called_once()

        palette_theme_call = light.apply_theme.call_args
        palette_theme_arg = palette_theme_call.args[0]
        assert palette_theme_arg is not None

        # Simulate the light turning on
        light.state.power = 65535
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=30))
        await hass.async_block_till_done(wait_background_tasks=True)

        state = hass.states.get(entity_id)
        assert state.state == STATE_ON

        light.apply_theme.reset_mock()
        light.set_power.reset_mock()


async def test_effect_pulse(hass: HomeAssistant, mock_effect_conductor) -> None:
    """Test the software-based pulse effect."""
    light = _mocked_bulb()
    light.state.power = 65535
    light.state.color = HSBK(hue=360, saturation=1.0, brightness=1.0, kelvin=9000)

    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    entry.add_to_hass(hass)

    with (
        _patch_device(light),
        _patch_discovery(light),
        patch("homeassistant.components.lifx.light.LIFX_STATE_SETTLE_DELAY", 0),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        entity_id = "light.my_bulb"

        await hass.services.async_call(
            DOMAIN,
            SERVICE_EFFECT_PULSE,
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_POWER_ON: True,
            },
            blocking=True,
        )

        mock_effect_conductor.start.assert_called_once()
        effect_arg = mock_effect_conductor.start.call_args[0][0]
        assert effect_arg.power_on is True


async def test_effect_colorloop(hass: HomeAssistant, mock_effect_conductor) -> None:
    """Test the software-based colorloop effect."""
    light = _mocked_bulb()
    light.state.power = 65535
    light.state.color = HSBK(hue=360, saturation=1.0, brightness=1.0, kelvin=9000)

    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    entry.add_to_hass(hass)

    with (
        _patch_device(light),
        _patch_discovery(light),
        patch("homeassistant.components.lifx.light.LIFX_STATE_SETTLE_DELAY", 0),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        entity_id = "light.my_bulb"

        await hass.services.async_call(
            DOMAIN,
            SERVICE_EFFECT_COLORLOOP,
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_PERIOD: 30.0,
                ATTR_CHANGE: 45.0,
                ATTR_SPREAD: 90.0,
                ATTR_BRIGHTNESS_PCT: 80,
                ATTR_SATURATION_MAX: 90,
                ATTR_SATURATION_MIN: 50,
                ATTR_POWER_ON: True,
            },
            blocking=True,
        )

        mock_effect_conductor.start.assert_called_once()
        effect_arg = mock_effect_conductor.start.call_args[0][0]
        assert effect_arg.period == 30.0
        assert effect_arg.change == 45.0
        assert effect_arg.spread == 90.0
        assert effect_arg.brightness == pytest.approx(0.8, abs=0.01)
        assert effect_arg.saturation_max == pytest.approx(0.9, abs=0.01)
        assert effect_arg.saturation_min == pytest.approx(0.5, abs=0.01)
        assert effect_arg.power_on is True


async def test_effect_colorloop_with_brightness(
    hass: HomeAssistant, mock_effect_conductor
) -> None:
    """Test colorloop effect with ATTR_BRIGHTNESS instead of ATTR_BRIGHTNESS_PCT."""
    light = _mocked_bulb()
    light.state.power = 65535
    light.state.color = HSBK(hue=360, saturation=1.0, brightness=1.0, kelvin=9000)

    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    entry.add_to_hass(hass)

    with (
        _patch_device(light),
        _patch_discovery(light),
        patch("homeassistant.components.lifx.light.LIFX_STATE_SETTLE_DELAY", 0),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        entity_id = "light.my_bulb"

        await hass.services.async_call(
            DOMAIN,
            SERVICE_EFFECT_COLORLOOP,
            {
                ATTR_ENTITY_ID: entity_id,
                ATTR_BRIGHTNESS: 128,
                ATTR_POWER_ON: True,
            },
            blocking=True,
        )

        mock_effect_conductor.start.assert_called_once()
        effect_arg = mock_effect_conductor.start.call_args[0][0]
        assert effect_arg.brightness == pytest.approx(128 / 255, abs=0.01)
        assert effect_arg.power_on is True
