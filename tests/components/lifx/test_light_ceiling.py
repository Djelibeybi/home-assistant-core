"""Tests for the LIFX ceiling uplight/downlight light entities."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from lifx import HSBK
import pytest

from homeassistant.components import lifx
from homeassistant.components.lifx import DOMAIN
from homeassistant.components.lifx.const import CONF_SERIAL
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_MODE,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ATTR_SUPPORTED_COLOR_MODES,
    ATTR_TRANSITION,
    DOMAIN as LIGHT_DOMAIN,
    ColorMode,
)
from homeassistant.const import ATTR_ENTITY_ID, CONF_HOST, STATE_OFF, STATE_ON, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from . import (
    DEFAULT_ENTRY_TITLE,
    IP_ADDRESS,
    SERIAL,
    _mocked_bulb,
    _mocked_ceiling,
    _patch_config_flow_try_connect,
    _patch_device,
    _patch_discovery,
    async_refresh_entry,
)

from tests.common import MockConfigEntry


@pytest.fixture(autouse=True)
def patch_lifx_state_settle_delay():
    """Set asyncio.sleep for state settles to zero."""
    with patch("homeassistant.components.lifx.light.LIFX_STATE_SETTLE_DELAY", 0):
        yield


def _create_ceiling_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Create and add a ceiling config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    entry.add_to_hass(hass)
    return entry


async def _setup_ceiling(
    hass: HomeAssistant,
    light=None,
    enable_components: bool = False,
) -> tuple:
    """Set up a ceiling light and return (entry, light).

    If enable_components is True, pre-enables the uplight and downlight entities
    in the entity registry before setup so they're active immediately.
    """
    ceiling = light or _mocked_ceiling()
    entry = _create_ceiling_entry(hass)

    if enable_components:
        ent_reg = er.async_get(hass)
        ent_reg.async_get_or_create(
            Platform.LIGHT,
            DOMAIN,
            f"{SERIAL}_uplight",
            config_entry=entry,
            disabled_by=None,
            suggested_object_id="my_bulb_uplight",
        )
        ent_reg.async_get_or_create(
            Platform.LIGHT,
            DOMAIN,
            f"{SERIAL}_downlight",
            config_entry=entry,
            disabled_by=None,
            suggested_object_id="my_bulb_downlight",
        )

    with (
        _patch_discovery(device=ceiling),
        _patch_config_flow_try_connect(device=ceiling),
        _patch_device(device=ceiling),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()
    return entry, ceiling


async def test_ceiling_creates_three_entities(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test that a ceiling device creates parent, uplight, and downlight entities."""
    await _setup_ceiling(hass)

    # Parent entity should exist and be enabled
    parent_entity = entity_registry.async_get("light.my_bulb")
    assert parent_entity is not None
    assert parent_entity.disabled_by is None

    # Uplight and downlight should exist but be disabled by default
    uplight_entity = entity_registry.async_get("light.my_bulb_uplight")
    assert uplight_entity is not None
    assert uplight_entity.disabled_by == er.RegistryEntryDisabler.INTEGRATION

    downlight_entity = entity_registry.async_get("light.my_bulb_downlight")
    assert downlight_entity is not None
    assert downlight_entity.disabled_by == er.RegistryEntryDisabler.INTEGRATION


async def test_ceiling_uplight_state(
    hass: HomeAssistant,
) -> None:
    """Test uplight entity reads state from coordinator."""
    ceiling = _mocked_ceiling()
    ceiling.state.uplight_is_on = True
    ceiling.state.uplight_color = HSBK(
        hue=120, saturation=0.5, brightness=0.8, kelvin=4000
    )

    await _setup_ceiling(hass, ceiling, enable_components=True)

    state = hass.states.get("light.my_bulb_uplight")
    assert state is not None
    assert state.state == STATE_ON
    assert state.attributes[ATTR_BRIGHTNESS] == round(0.8 * 255)
    assert state.attributes[ATTR_HS_COLOR] == (120, 50.0)
    assert state.attributes[ATTR_COLOR_MODE] == ColorMode.HS


async def test_ceiling_uplight_off_state(
    hass: HomeAssistant,
) -> None:
    """Test uplight entity reports off when uplight is off."""
    ceiling = _mocked_ceiling()
    ceiling.state.uplight_is_on = False

    await _setup_ceiling(hass, ceiling, enable_components=True)

    state = hass.states.get("light.my_bulb_uplight")
    assert state is not None
    assert state.state == STATE_OFF


async def test_ceiling_downlight_state(
    hass: HomeAssistant,
) -> None:
    """Test downlight entity reads state from coordinator."""
    ceiling = _mocked_ceiling()
    ceiling.state.downlight_is_on = True
    ceiling.state.downlight_colors = [
        HSBK(hue=200, saturation=0.8, brightness=0.6, kelvin=5000),
        HSBK(hue=200, saturation=0.8, brightness=0.9, kelvin=5000),
    ]

    await _setup_ceiling(hass, ceiling, enable_components=True)

    state = hass.states.get("light.my_bulb_downlight")
    assert state is not None
    assert state.state == STATE_ON
    # Brightness should be max across all zones
    assert state.attributes[ATTR_BRIGHTNESS] == round(0.9 * 255)
    # Color should come from first zone
    assert state.attributes[ATTR_HS_COLOR] == (200, 80.0)
    assert state.attributes[ATTR_COLOR_MODE] == ColorMode.HS


async def test_ceiling_downlight_color_temp_mode(
    hass: HomeAssistant,
) -> None:
    """Test downlight reports color_temp mode when saturation is 0."""
    ceiling = _mocked_ceiling()
    ceiling.state.downlight_is_on = True
    ceiling.state.downlight_colors = [
        HSBK(hue=0, saturation=0, brightness=0.7, kelvin=4000),
    ]

    await _setup_ceiling(hass, ceiling, enable_components=True)

    state = hass.states.get("light.my_bulb_downlight")
    assert state is not None
    assert state.attributes[ATTR_COLOR_MODE] == ColorMode.COLOR_TEMP


async def test_ceiling_uplight_turn_on(
    hass: HomeAssistant,
) -> None:
    """Test turning on the uplight."""
    ceiling = _mocked_ceiling()
    await _setup_ceiling(hass, ceiling, enable_components=True)

    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_on",
        {ATTR_ENTITY_ID: "light.my_bulb_uplight"},
        blocking=True,
    )

    ceiling.turn_uplight_on.assert_called_once()


async def test_ceiling_uplight_turn_on_with_brightness(
    hass: HomeAssistant,
) -> None:
    """Test turning on the uplight with brightness."""
    ceiling = _mocked_ceiling()
    await _setup_ceiling(hass, ceiling, enable_components=True)

    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_on",
        {
            ATTR_ENTITY_ID: "light.my_bulb_uplight",
            ATTR_BRIGHTNESS: 200,
        },
        blocking=True,
    )

    ceiling.turn_uplight_on.assert_called_once()
    call_kwargs = ceiling.turn_uplight_on.call_args
    assert call_kwargs.kwargs.get("color") is not None
    assert call_kwargs.kwargs["color"].brightness == pytest.approx(200 / 255, abs=0.01)


async def test_ceiling_uplight_turn_on_with_color_temp(
    hass: HomeAssistant,
) -> None:
    """Test turning on the uplight with color temperature."""
    ceiling = _mocked_ceiling()
    await _setup_ceiling(hass, ceiling, enable_components=True)

    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_on",
        {
            ATTR_ENTITY_ID: "light.my_bulb_uplight",
            ATTR_COLOR_TEMP_KELVIN: 5000,
        },
        blocking=True,
    )

    ceiling.turn_uplight_on.assert_called_once()
    call_kwargs = ceiling.turn_uplight_on.call_args
    assert call_kwargs.kwargs.get("color") is not None
    assert call_kwargs.kwargs["color"].kelvin == 5000


async def test_ceiling_uplight_turn_on_with_hs_color(
    hass: HomeAssistant,
) -> None:
    """Test turning on the uplight with HS color."""
    ceiling = _mocked_ceiling()
    await _setup_ceiling(hass, ceiling, enable_components=True)

    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_on",
        {
            ATTR_ENTITY_ID: "light.my_bulb_uplight",
            ATTR_HS_COLOR: (180, 75),
        },
        blocking=True,
    )

    ceiling.turn_uplight_on.assert_called_once()
    call_kwargs = ceiling.turn_uplight_on.call_args
    assert call_kwargs.kwargs.get("color") is not None
    assert call_kwargs.kwargs["color"].hue == 180
    assert call_kwargs.kwargs["color"].saturation == 0.75


async def test_ceiling_uplight_turn_off(
    hass: HomeAssistant,
) -> None:
    """Test turning off the uplight when downlight is still on."""
    ceiling = _mocked_ceiling()
    ceiling.state.uplight_is_on = True
    ceiling.state.downlight_is_on = True
    ceiling.state.power = 65535
    await _setup_ceiling(hass, ceiling, enable_components=True)

    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_off",
        {ATTR_ENTITY_ID: "light.my_bulb_uplight"},
        blocking=True,
    )

    # Downlight is still on, so it should use turn_uplight_off not set_power
    ceiling.turn_uplight_off.assert_called_once()


async def test_ceiling_uplight_turn_off_powers_off_when_both_off(
    hass: HomeAssistant,
) -> None:
    """Test turning off uplight powers off whole light when downlight is also off."""
    ceiling = _mocked_ceiling()
    ceiling.state.uplight_is_on = True
    ceiling.state.downlight_is_on = False
    ceiling.state.power = 65535
    await _setup_ceiling(hass, ceiling, enable_components=True)

    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_off",
        {ATTR_ENTITY_ID: "light.my_bulb_uplight"},
        blocking=True,
    )

    # Downlight is off, so it should power off the whole light
    ceiling.set_power.assert_called()
    ceiling.turn_uplight_off.assert_not_called()


async def test_ceiling_downlight_turn_on(
    hass: HomeAssistant,
) -> None:
    """Test turning on the downlight."""
    ceiling = _mocked_ceiling()
    await _setup_ceiling(hass, ceiling, enable_components=True)

    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_on",
        {ATTR_ENTITY_ID: "light.my_bulb_downlight"},
        blocking=True,
    )

    ceiling.turn_downlight_on.assert_called_once()


async def test_ceiling_downlight_turn_off(
    hass: HomeAssistant,
) -> None:
    """Test turning off the downlight when uplight is still on."""
    ceiling = _mocked_ceiling()
    ceiling.state.uplight_is_on = True
    ceiling.state.downlight_is_on = True
    ceiling.state.power = 65535
    await _setup_ceiling(hass, ceiling, enable_components=True)

    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_off",
        {ATTR_ENTITY_ID: "light.my_bulb_downlight"},
        blocking=True,
    )

    # Uplight is still on, so it should use turn_downlight_off
    ceiling.turn_downlight_off.assert_called_once()


async def test_ceiling_downlight_turn_off_powers_off_when_both_off(
    hass: HomeAssistant,
) -> None:
    """Test turning off downlight powers off whole light when uplight is also off."""
    ceiling = _mocked_ceiling()
    ceiling.state.uplight_is_on = False
    ceiling.state.downlight_is_on = True
    ceiling.state.power = 65535
    await _setup_ceiling(hass, ceiling, enable_components=True)

    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_off",
        {ATTR_ENTITY_ID: "light.my_bulb_downlight"},
        blocking=True,
    )

    # Uplight is off, so it should power off the whole light
    ceiling.set_power.assert_called()
    ceiling.turn_downlight_off.assert_not_called()


async def test_ceiling_uplight_turn_on_with_transition(
    hass: HomeAssistant,
) -> None:
    """Test turning on the uplight with a transition."""
    ceiling = _mocked_ceiling()
    await _setup_ceiling(hass, ceiling, enable_components=True)

    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_on",
        {
            ATTR_ENTITY_ID: "light.my_bulb_uplight",
            ATTR_TRANSITION: 2,
        },
        blocking=True,
    )

    ceiling.turn_uplight_on.assert_called_once()
    call_kwargs = ceiling.turn_uplight_on.call_args
    assert call_kwargs.kwargs.get("duration") == 2


async def test_ceiling_uplight_supported_color_modes(
    hass: HomeAssistant,
) -> None:
    """Test uplight supports HS and color_temp modes."""
    ceiling = _mocked_ceiling()
    await _setup_ceiling(hass, ceiling, enable_components=True)

    state = hass.states.get("light.my_bulb_uplight")
    assert state is not None
    supported = state.attributes[ATTR_SUPPORTED_COLOR_MODES]
    assert ColorMode.HS in supported
    assert ColorMode.COLOR_TEMP in supported


async def test_ceiling_entity_sync_enabled(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test enabling uplight also enables downlight."""
    ceiling = _mocked_ceiling()
    await _setup_ceiling(hass, ceiling)

    # Both should be disabled initially
    uplight = entity_registry.async_get("light.my_bulb_uplight")
    downlight = entity_registry.async_get("light.my_bulb_downlight")
    assert uplight.disabled_by == er.RegistryEntryDisabler.INTEGRATION
    assert downlight.disabled_by == er.RegistryEntryDisabler.INTEGRATION

    # Enable the uplight
    entity_registry.async_update_entity("light.my_bulb_uplight", disabled_by=None)
    await hass.async_block_till_done()

    # Downlight should also be enabled now
    downlight = entity_registry.async_get("light.my_bulb_downlight")
    assert downlight.disabled_by is None


async def test_ceiling_entity_sync_disabled(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test disabling downlight also disables uplight."""
    ceiling = _mocked_ceiling()
    await _setup_ceiling(hass, ceiling)

    # Enable both first
    entity_registry.async_update_entity("light.my_bulb_uplight", disabled_by=None)
    entity_registry.async_update_entity("light.my_bulb_downlight", disabled_by=None)
    await hass.async_block_till_done()

    # Disable the downlight
    entity_registry.async_update_entity(
        "light.my_bulb_downlight",
        disabled_by=er.RegistryEntryDisabler.USER,
    )
    await hass.async_block_till_done()

    # Uplight should also be disabled now
    uplight = entity_registry.async_get("light.my_bulb_uplight")
    assert uplight.disabled_by == er.RegistryEntryDisabler.USER


async def test_ceiling_parent_entity_has_sky_effect(
    hass: HomeAssistant,
) -> None:
    """Test parent ceiling entity includes sky effect in effect list."""
    ceiling = _mocked_ceiling()
    await _setup_ceiling(hass, ceiling)

    state = hass.states.get("light.my_bulb")
    assert state is not None
    assert "effect_sky" in state.attributes.get("effect_list", [])


async def test_ceiling_uplight_color_temp_mode(
    hass: HomeAssistant,
) -> None:
    """Test uplight reports color_temp mode when saturation is 0."""
    ceiling = _mocked_ceiling()
    ceiling.state.uplight_is_on = True
    ceiling.state.uplight_color = HSBK(hue=0, saturation=0, brightness=0.5, kelvin=3500)

    await _setup_ceiling(hass, ceiling, enable_components=True)

    state = hass.states.get("light.my_bulb_uplight")
    assert state is not None
    assert state.attributes[ATTR_COLOR_MODE] == ColorMode.COLOR_TEMP


async def test_ceiling_uplight_state_updates_on_refresh(
    hass: HomeAssistant,
) -> None:
    """Test uplight entity updates state when coordinator refreshes."""
    ceiling = _mocked_ceiling()
    ceiling.state.uplight_is_on = False
    entry, _ = await _setup_ceiling(hass, ceiling, enable_components=True)

    # Verify initially off
    state = hass.states.get("light.my_bulb_uplight")
    assert state is not None
    assert state.state == STATE_OFF

    # Simulate state change and trigger coordinator refresh
    ceiling.state.uplight_is_on = True
    ceiling.state.uplight_color = HSBK(
        hue=60, saturation=0.3, brightness=0.7, kelvin=4500
    )
    await async_refresh_entry(hass, entry)

    state = hass.states.get("light.my_bulb_uplight")
    assert state is not None
    assert state.state == STATE_ON
    assert state.attributes[ATTR_BRIGHTNESS] == round(0.7 * 255)


async def test_ceiling_downlight_state_updates_on_refresh(
    hass: HomeAssistant,
) -> None:
    """Test downlight entity updates state when coordinator refreshes."""
    ceiling = _mocked_ceiling()
    ceiling.state.downlight_is_on = False
    entry, _ = await _setup_ceiling(hass, ceiling, enable_components=True)

    # Verify initially off
    state = hass.states.get("light.my_bulb_downlight")
    assert state is not None
    assert state.state == STATE_OFF

    # Simulate state change and trigger coordinator refresh
    ceiling.state.downlight_is_on = True
    ceiling.state.downlight_colors = [
        HSBK(hue=0, saturation=0, brightness=0.9, kelvin=3000),
    ]
    await async_refresh_entry(hass, entry)

    state = hass.states.get("light.my_bulb_downlight")
    assert state is not None
    assert state.state == STATE_ON
    assert state.attributes[ATTR_BRIGHTNESS] == round(0.9 * 255)


async def test_ceiling_downlight_turn_on_with_brightness(
    hass: HomeAssistant,
) -> None:
    """Test turning on the downlight with brightness adjusts all zones."""
    ceiling = _mocked_ceiling()
    ceiling.state.downlight_colors = [
        HSBK(hue=0, saturation=0, brightness=0.5, kelvin=3500),
    ]
    ceiling.get_downlight_colors = AsyncMock(
        return_value=[HSBK(hue=0, saturation=0, brightness=0.5, kelvin=3500)]
    )
    await _setup_ceiling(hass, ceiling, enable_components=True)

    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_on",
        {
            ATTR_ENTITY_ID: "light.my_bulb_downlight",
            ATTR_BRIGHTNESS: 200,
        },
        blocking=True,
    )

    ceiling.turn_downlight_on.assert_called_once()
    call_kwargs = ceiling.turn_downlight_on.call_args
    assert call_kwargs.kwargs.get("colors") is not None


async def test_ceiling_downlight_turn_on_with_hs_color(
    hass: HomeAssistant,
) -> None:
    """Test turning on the downlight with HS color."""
    ceiling = _mocked_ceiling()
    ceiling.state.downlight_colors = [
        HSBK(hue=0, saturation=0, brightness=0.5, kelvin=3500),
    ]
    ceiling.get_downlight_colors = AsyncMock(
        return_value=[HSBK(hue=0, saturation=0, brightness=0.5, kelvin=3500)]
    )
    await _setup_ceiling(hass, ceiling, enable_components=True)

    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_on",
        {
            ATTR_ENTITY_ID: "light.my_bulb_downlight",
            ATTR_HS_COLOR: (240, 100),
        },
        blocking=True,
    )

    ceiling.turn_downlight_on.assert_called_once()
    call_kwargs = ceiling.turn_downlight_on.call_args
    colors = call_kwargs.kwargs.get("colors")
    assert colors is not None
    assert colors[0].hue == 240
    assert colors[0].saturation == 1.0


async def test_ceiling_uplight_turn_on_zero_brightness_no_hsk_change(
    hass: HomeAssistant,
) -> None:
    """Test uplight turn on with zero brightness and no HSK change calls turn_on without color."""
    ceiling = _mocked_ceiling()
    # Set current color with brightness 0 and same HSK as what generate_hsbk would produce
    ceiling.get_uplight_color = AsyncMock(
        return_value=HSBK(hue=0, saturation=0, brightness=0, kelvin=3500)
    )
    await _setup_ceiling(hass, ceiling, enable_components=True)

    # Turn on with color_temp that matches current kelvin - brightness stays 0, HSK unchanged
    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_on",
        {
            ATTR_ENTITY_ID: "light.my_bulb_uplight",
            ATTR_COLOR_TEMP_KELVIN: 3500,
        },
        blocking=True,
    )

    ceiling.turn_uplight_on.assert_called_once()
    call_kwargs = ceiling.turn_uplight_on.call_args
    # No color kwarg since HSK didn't change - just turn on with duration
    assert "color" not in call_kwargs.kwargs


async def test_ceiling_uplight_turn_on_zero_brightness_with_hsk_change(
    hass: HomeAssistant,
) -> None:
    """Test uplight turn on with zero brightness and HSK change uses default brightness."""
    ceiling = _mocked_ceiling()
    ceiling.get_uplight_color = AsyncMock(
        return_value=HSBK(hue=0, saturation=0, brightness=0, kelvin=3500)
    )
    await _setup_ceiling(hass, ceiling, enable_components=True)

    # Turn on with different color_temp - brightness is 0 but HSK changed
    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_on",
        {
            ATTR_ENTITY_ID: "light.my_bulb_uplight",
            ATTR_COLOR_TEMP_KELVIN: 6500,
        },
        blocking=True,
    )

    ceiling.turn_uplight_on.assert_called_once()
    call_kwargs = ceiling.turn_uplight_on.call_args
    color = call_kwargs.kwargs.get("color")
    assert color is not None
    assert color.kelvin == 6500
    # Should have used DEFAULT_BRIGHTNESS (0.8) as base since brightness was 0
    assert color.brightness > 0


async def test_ceiling_downlight_turn_on_zero_brightness_no_hsk_change(
    hass: HomeAssistant,
) -> None:
    """Test downlight turn on with zero brightness and no HSK change."""
    ceiling = _mocked_ceiling()
    ceiling.get_downlight_colors = AsyncMock(
        return_value=[HSBK(hue=0, saturation=0, brightness=0, kelvin=3500)]
    )
    await _setup_ceiling(hass, ceiling, enable_components=True)

    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_on",
        {
            ATTR_ENTITY_ID: "light.my_bulb_downlight",
            ATTR_COLOR_TEMP_KELVIN: 3500,
        },
        blocking=True,
    )

    ceiling.turn_downlight_on.assert_called_once()
    call_kwargs = ceiling.turn_downlight_on.call_args
    # No colors kwarg since HSK didn't change - just turn on with duration
    assert "colors" not in call_kwargs.kwargs


async def test_ceiling_downlight_turn_on_zero_brightness_with_hsk_change(
    hass: HomeAssistant,
) -> None:
    """Test downlight turn on with zero brightness and HSK change uses default brightness."""
    ceiling = _mocked_ceiling()
    ceiling.get_downlight_colors = AsyncMock(
        return_value=[HSBK(hue=0, saturation=0, brightness=0, kelvin=3500)]
    )
    await _setup_ceiling(hass, ceiling, enable_components=True)

    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_on",
        {
            ATTR_ENTITY_ID: "light.my_bulb_downlight",
            ATTR_COLOR_TEMP_KELVIN: 6500,
        },
        blocking=True,
    )

    ceiling.turn_downlight_on.assert_called_once()
    call_kwargs = ceiling.turn_downlight_on.call_args
    colors = call_kwargs.kwargs.get("colors")
    assert colors is not None
    assert colors[0].kelvin == 6500
    assert colors[0].brightness > 0


async def test_ceiling_downlight_turn_on_empty_zones_with_color(
    hass: HomeAssistant,
) -> None:
    """Test downlight turn on with color when zones list is empty uses default color."""
    ceiling = _mocked_ceiling()
    ceiling.get_downlight_colors = AsyncMock(return_value=[])
    await _setup_ceiling(hass, ceiling, enable_components=True)

    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_on",
        {
            ATTR_ENTITY_ID: "light.my_bulb_downlight",
            ATTR_BRIGHTNESS: 200,
        },
        blocking=True,
    )

    ceiling.turn_downlight_on.assert_called_once()
    call_kwargs = ceiling.turn_downlight_on.call_args
    assert call_kwargs.kwargs.get("colors") is not None


async def test_ceiling_sync_ignores_non_update_actions(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test sync handler ignores non-update entity registry events."""
    ceiling = _mocked_ceiling()
    await _setup_ceiling(hass, ceiling)

    # Enable both entities first
    entity_registry.async_update_entity("light.my_bulb_uplight", disabled_by=None)
    entity_registry.async_update_entity("light.my_bulb_downlight", disabled_by=None)
    await hass.async_block_till_done()

    # Remove the uplight entity - this fires a "remove" action, not "update"
    entity_registry.async_remove("light.my_bulb_uplight")
    await hass.async_block_till_done()

    # Downlight should NOT be affected by the remove event
    downlight = entity_registry.async_get("light.my_bulb_downlight")
    assert downlight is not None
    assert downlight.disabled_by is None


async def test_ceiling_sync_ignores_non_disabled_by_changes(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test sync handler ignores entity updates that don't change disabled_by."""
    ceiling = _mocked_ceiling()
    await _setup_ceiling(hass, ceiling)

    # Enable both entities
    entity_registry.async_update_entity("light.my_bulb_uplight", disabled_by=None)
    entity_registry.async_update_entity("light.my_bulb_downlight", disabled_by=None)
    await hass.async_block_till_done()

    # Update icon (not disabled_by) on uplight - should not sync to downlight
    entity_registry.async_update_entity("light.my_bulb_uplight", icon="mdi:lightbulb")
    await hass.async_block_till_done()

    # Both should still be enabled
    uplight = entity_registry.async_get("light.my_bulb_uplight")
    downlight = entity_registry.async_get("light.my_bulb_downlight")
    assert uplight is not None
    assert uplight.disabled_by is None
    assert downlight is not None
    assert downlight.disabled_by is None


async def test_ceiling_uplight_null_color_on_refresh(
    hass: HomeAssistant,
) -> None:
    """Test uplight handles null color gracefully on coordinator refresh."""
    ceiling = _mocked_ceiling()
    ceiling.state.uplight_is_on = True
    ceiling.state.uplight_color = HSBK(hue=0, saturation=0, brightness=0.5, kelvin=3500)
    entry, _ = await _setup_ceiling(hass, ceiling, enable_components=True)

    # Verify initially has color attributes
    state = hass.states.get("light.my_bulb_uplight")
    assert state is not None
    assert state.state == STATE_ON

    # Simulate uplight_color becoming None (e.g., state type changed)
    ceiling.state.uplight_color = None
    ceiling.state.uplight_is_on = False
    await async_refresh_entry(hass, entry)

    state = hass.states.get("light.my_bulb_uplight")
    assert state is not None
    assert state.state == STATE_OFF


async def test_ceiling_downlight_empty_colors_on_refresh(
    hass: HomeAssistant,
) -> None:
    """Test downlight handles empty colors list gracefully on coordinator refresh."""
    ceiling = _mocked_ceiling()
    ceiling.state.downlight_is_on = True
    ceiling.state.downlight_colors = [
        HSBK(hue=0, saturation=0, brightness=0.5, kelvin=3500),
    ]
    entry, _ = await _setup_ceiling(hass, ceiling, enable_components=True)

    # Verify initially has color attributes
    state = hass.states.get("light.my_bulb_downlight")
    assert state is not None
    assert state.state == STATE_ON

    # Simulate colors becoming empty
    ceiling.state.downlight_colors = []
    ceiling.state.downlight_is_on = False
    await async_refresh_entry(hass, entry)

    state = hass.states.get("light.my_bulb_downlight")
    assert state is not None
    assert state.state == STATE_OFF


async def test_ceiling_downlight_turn_on_empty_zones_zero_brightness(
    hass: HomeAssistant,
) -> None:
    """Test downlight turn on with empty zones and near-zero brightness is a no-op."""
    ceiling = _mocked_ceiling()
    ceiling.get_downlight_colors = AsyncMock(return_value=[])
    await _setup_ceiling(hass, ceiling, enable_components=True)

    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_on",
        {
            ATTR_ENTITY_ID: "light.my_bulb_downlight",
            ATTR_BRIGHTNESS: 1,
        },
        blocking=True,
    )

    # Brightness 1/255 rounds to 0.00 in HSBK, so turn_downlight_on should
    # not be called with colors (since brightness would be 0)
    call_kwargs = ceiling.turn_downlight_on.call_args
    if call_kwargs is not None:
        # If called, verify it was NOT called with colors (brightness was 0)
        assert call_kwargs.kwargs.get("colors") is None


async def test_ceiling_sync_missing_entities(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test sync setup logs warning when ceiling entities cannot be found."""
    ceiling = _mocked_ceiling()
    _create_ceiling_entry(hass)

    # Patch _async_setup_ceiling_entity_sync to intercept the entity lookup
    # by temporarily removing one entity after setup
    with (
        _patch_discovery(device=ceiling),
        _patch_config_flow_try_connect(device=ceiling),
        _patch_device(device=ceiling),
        patch(
            "homeassistant.components.lifx.er.async_get",
            return_value=entity_registry,
        ),
        patch.object(
            entity_registry,
            "async_get_entity_id",
            return_value=None,
        ),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

    assert "Could not find ceiling component entities" in caplog.text


async def test_coordinator_ceiling_properties_on_non_ceiling_device(
    hass: HomeAssistant,
) -> None:
    """Test ceiling-specific coordinator properties return defaults for non-ceiling devices."""
    bulb = _mocked_bulb()
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    entry.add_to_hass(hass)

    with (
        _patch_discovery(device=bulb),
        _patch_config_flow_try_connect(device=bulb),
        _patch_device(device=bulb),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

    coordinator = entry.runtime_data

    # These should return defaults since the device is not a CeilingLight
    assert coordinator.has_ceiling is False
    assert coordinator.uplight_is_on is False
    assert coordinator.downlight_is_on is False
    assert coordinator.uplight_color is None
    assert coordinator.downlight_colors is None


async def test_coordinator_ceiling_turn_methods_on_non_ceiling_device(
    hass: HomeAssistant,
) -> None:
    """Test ceiling turn methods are no-ops for non-ceiling devices."""
    bulb = _mocked_bulb()
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    entry.add_to_hass(hass)

    with (
        _patch_discovery(device=bulb),
        _patch_config_flow_try_connect(device=bulb),
        _patch_device(device=bulb),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

    coordinator = entry.runtime_data

    # These should be no-ops since the device is not a CeilingLight
    await coordinator.async_turn_uplight_on()
    await coordinator.async_turn_downlight_on()

    # Verify no ceiling-specific methods were called on the mock bulb
    assert not hasattr(bulb, "turn_uplight_on") or not bulb.turn_uplight_on.called
    assert not hasattr(bulb, "turn_downlight_on") or not bulb.turn_downlight_on.called


async def test_ceiling_sync_entity_removed_during_sync(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test sync handler handles entity being removed between event and lookup."""
    ceiling = _mocked_ceiling()
    await _setup_ceiling(hass, ceiling)

    # Enable both entities
    entity_registry.async_update_entity("light.my_bulb_uplight", disabled_by=None)
    entity_registry.async_update_entity("light.my_bulb_downlight", disabled_by=None)
    await hass.async_block_till_done()

    # Patch async_get to return None for the "other" entity, simulating
    # a race condition where the other entity is removed between event
    # and lookup
    original_async_get = entity_registry.async_get

    def mock_async_get(entity_id: str) -> MagicMock | None:
        if entity_id == "light.my_bulb_downlight":
            return None
        return original_async_get(entity_id)

    with patch.object(entity_registry, "async_get", side_effect=mock_async_get):
        # Disable the uplight - should attempt sync but gracefully handle
        # the missing downlight entity
        entity_registry.async_update_entity(
            "light.my_bulb_uplight",
            disabled_by=er.RegistryEntryDisabler.USER,
        )
        await hass.async_block_till_done()

    # No error should have occurred - the handler gracefully returned
