"""Tests for the LIFX integration."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from lifx import (
    HSBK,
    CeilingLight,
    CeilingLightState,
    Device,
    FirmwareEffect,
    HevLight,
    HevLightState,
    InfraredLight,
    InfraredLightState,
    LifxTimeoutError,
    LifxUnsupportedCommandError,
    Light,
    LightState,
    MatrixLight,
    MatrixLightState,
    MultiZoneLight,
    MultiZoneLightState,
)

from homeassistant.components.lifx.const import LIFX_DEFAULT_PORT
from homeassistant.components.lifx.coordinator import LIFXUpdateCoordinator
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_registry import EntityRegistry, RegistryEntry

MODULE = "homeassistant.components.lifx"
MODULE_CONFIG_FLOW = "homeassistant.components.lifx.config_flow"
IP_ADDRESS = "127.0.0.1"
PORT = LIFX_DEFAULT_PORT
SERIAL_FORMATTED = "aa:bb:cc:dd:ee:cc"
SERIAL = "aabbccddeecc"
SERIAL_RAW = SERIAL
MAC_ADDRESS = "aa:bb:cc:dd:ee:cd"
DHCP_FORMATTED_MAC = "aabbccddeecd"
DEFAULT_ENTRY_TITLE = "My Bulb"
LABEL = "My Bulb"
GROUP = "My Group"


def get_entry_light_entity_id(hass: HomeAssistant, config: ConfigEntry) -> str:
    """Return the light entity ID for a config entry."""
    entity_registry: EntityRegistry = er.async_get(hass)
    entries: list[RegistryEntry] = er.async_entries_for_config_entry(
        registry=entity_registry, config_entry_id=config.entry_id
    )
    for entry in entries:
        if entry.entity_id.startswith("light."):
            return entry.entity_id
    raise AssertionError("No light entity found")


async def async_refresh_entry(hass: HomeAssistant, config: ConfigEntry) -> None:
    """Request a coordinator refresh for a LIFX config entry."""
    coordinator: LIFXUpdateCoordinator = config.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()


def _create_capabilities(**kwargs: Any) -> MagicMock:
    """Create mock device capabilities."""
    caps = MagicMock()
    caps.has_color = kwargs.get("has_color", True)
    caps.has_multizone = kwargs.get("has_multizone", False)
    caps.has_extended_multizone = kwargs.get("has_extended_multizone", False)
    caps.has_matrix = kwargs.get("has_matrix", False)
    caps.has_infrared = kwargs.get("has_infrared", False)
    caps.has_hev = kwargs.get("has_hev", False)
    caps.kelvin_min = kwargs.get("kelvin_min", 1500)
    caps.kelvin_max = kwargs.get("kelvin_max", 9000)
    return caps


def _create_state(state_class: type = LightState, **kwargs: Any) -> MagicMock:
    """Create a mock device state."""
    state = MagicMock(spec=state_class)
    state.power = kwargs.get("power", 0)
    state.color = kwargs.get(
        "color", HSBK(hue=0, saturation=0, brightness=0.5, kelvin=3500)
    )
    state.label = kwargs.get("label", LABEL)
    state.mac_address = kwargs.get("mac_address", SERIAL_FORMATTED)
    state.model = kwargs.get("model", "LIFX A19")
    state.host_firmware = MagicMock(
        version_major=kwargs.get("fw_major", 3),
        version_minor=kwargs.get("fw_minor", 0),
    )
    state.capabilities = _create_capabilities(**kwargs)
    state.group = MagicMock(label=kwargs.get("group", GROUP))
    state.group_name = kwargs.get("group", GROUP)
    state.serial = kwargs.get("serial", SERIAL)
    return state


def _build_mock_light(state: MagicMock, light_class: type = Light) -> MagicMock:
    """Build a mock light instance with the given state and spec."""
    light = MagicMock(spec=light_class)
    light.serial = SERIAL
    light.ip = IP_ADDRESS
    light.port = PORT
    light.state = state
    light.capabilities = state.capabilities

    # Async methods
    light.refresh_state = AsyncMock()
    light.close = AsyncMock()
    light.set_power = AsyncMock()
    light.set_color = AsyncMock()
    light.set_waveform = AsyncMock()
    light.set_reboot = AsyncMock()
    light.get_wifi_info = AsyncMock(return_value=MagicMock(signal=1e-7))
    light.set_hev_cycle = AsyncMock()
    light.set_infrared = AsyncMock()
    light.set_color_zones = AsyncMock()
    light.set_extended_color_zones = AsyncMock()
    light.set_effect = AsyncMock()
    light.apply_theme = AsyncMock()
    light.get_color = AsyncMock(return_value=(state.color, state.power, state.label))
    light.get_group = AsyncMock(return_value=state.group)
    light._ensure_capabilities = AsyncMock()
    return light


def _mocked_bulb() -> MagicMock:
    """Create a mocked LIFX color light."""
    state = _create_state()
    return _build_mock_light(state, Light)


def _mocked_failing_bulb() -> MagicMock:
    """Create a mocked LIFX light that fails to connect."""
    light = _mocked_bulb()
    light.get_color = AsyncMock(side_effect=LifxTimeoutError("timeout"))
    light.set_power = AsyncMock(side_effect=LifxTimeoutError("timeout"))
    light.set_color = AsyncMock(side_effect=LifxTimeoutError("timeout"))
    light.refresh_state = AsyncMock(side_effect=LifxTimeoutError("timeout"))
    return light


def _mocked_white_bulb() -> MagicMock:
    """Create a mocked LIFX white light (color temp only)."""
    state = _create_state(has_color=False)
    return _build_mock_light(state, Light)


def _mocked_brightness_bulb() -> MagicMock:
    """Create a mocked LIFX brightness-only light."""
    state = _create_state(has_color=False, kelvin_min=2700, kelvin_max=2700)
    return _build_mock_light(state, Light)


def _mocked_clean_bulb() -> MagicMock:
    """Create a mocked LIFX Clean (HEV) light."""
    state = _create_state(
        state_class=HevLightState,
        has_hev=True,
    )
    state.hev_cycle = MagicMock(
        duration_s=7200,
        remaining_s=30,
        last_power=False,
    )
    return _build_mock_light(state, HevLight)


def _mocked_infrared_bulb() -> MagicMock:
    """Create a mocked LIFX infrared (Night Vision) light."""
    state = _create_state(
        state_class=InfraredLightState,
        has_infrared=True,
    )
    state.infrared = 1.0
    return _build_mock_light(state, InfraredLight)


def _mocked_light_strip() -> MagicMock:
    """Create a mocked LIFX multizone light strip."""
    state = _create_state(
        state_class=MultiZoneLightState,
        has_multizone=True,
        has_extended_multizone=True,
    )
    state.zone_count = 3
    state.zones = [HSBK(hue=0, saturation=0, brightness=0.5, kelvin=3500)] * 3
    state.effect = FirmwareEffect.OFF
    return _build_mock_light(state, MultiZoneLight)


def _mocked_tile() -> MagicMock:
    """Create a mocked LIFX Tile (matrix) light."""
    state = _create_state(
        state_class=MatrixLightState,
        has_matrix=True,
    )
    state.effect = FirmwareEffect.OFF
    state.tile_count = 5
    return _build_mock_light(state, MatrixLight)


def _mocked_ceiling() -> MagicMock:
    """Create a mocked LIFX Ceiling (matrix) light."""
    state = _create_state(
        state_class=CeilingLightState,
        has_matrix=True,
        model="LIFX Ceiling",
    )
    state.effect = FirmwareEffect.OFF
    state.tile_count = 1
    state.uplight_is_on = False
    state.downlight_is_on = False
    state.uplight_color = HSBK(hue=0, saturation=0, brightness=0.5, kelvin=3500)
    state.downlight_colors = [HSBK(hue=0, saturation=0, brightness=0.5, kelvin=3500)]
    light = _build_mock_light(state, CeilingLight)
    light.turn_uplight_on = AsyncMock()
    light.turn_uplight_off = AsyncMock()
    light.turn_downlight_on = AsyncMock()
    light.turn_downlight_off = AsyncMock()
    light.get_uplight_color = AsyncMock(
        return_value=HSBK(hue=0, saturation=0, brightness=0.5, kelvin=3500)
    )
    light.get_downlight_colors = AsyncMock(
        return_value=[HSBK(hue=0, saturation=0, brightness=0.5, kelvin=3500)]
    )
    return light


def _mocked_128zone_ceiling() -> MagicMock:
    """Create a mocked LIFX 128-zone Ceiling (matrix) light."""
    state = _create_state(
        state_class=CeilingLightState,
        has_matrix=True,
        model="LIFX 128 Zone Ceiling",
    )
    state.effect = FirmwareEffect.OFF
    state.tile_count = 1
    state.uplight_is_on = False
    state.downlight_is_on = False
    state.uplight_color = HSBK(hue=0, saturation=0, brightness=0.5, kelvin=3500)
    state.downlight_colors = [HSBK(hue=0, saturation=0, brightness=0.5, kelvin=3500)]
    light = _build_mock_light(state, CeilingLight)
    light.turn_uplight_on = AsyncMock()
    light.turn_uplight_off = AsyncMock()
    light.turn_downlight_on = AsyncMock()
    light.turn_downlight_off = AsyncMock()
    light.get_uplight_color = AsyncMock(
        return_value=HSBK(hue=0, saturation=0, brightness=0.5, kelvin=3500)
    )
    light.get_downlight_colors = AsyncMock(
        return_value=[HSBK(hue=0, saturation=0, brightness=0.5, kelvin=3500)]
    )
    return light


def _mocked_bulb_old_firmware() -> MagicMock:
    """Create a mocked LIFX light with old firmware."""
    state = _create_state(fw_major=2, fw_minor=76)
    return _build_mock_light(state, Light)


def _mocked_bulb_new_firmware() -> MagicMock:
    """Create a mocked LIFX light with new firmware."""
    state = _create_state(fw_major=3, fw_minor=90, mac_address=MAC_ADDRESS)
    return _build_mock_light(state, Light)


def _mocked_relay() -> MagicMock:
    """Create a mocked LIFX Switch (relay, not a light)."""
    state = _create_state(has_color=False)
    light = _build_mock_light(state, Light)
    light.get_color = AsyncMock(side_effect=LifxUnsupportedCommandError("not a light"))
    return light


def _mocked_switch() -> Device:
    """Create a real Device instance representing a LIFX Switch.

    Returns a real Device (not a Light subclass) so that
    ``type(device) is Device`` is True in the config flow.
    """
    return Device(serial=SERIAL, ip=IP_ADDRESS)


class _MockAsyncContextManager:
    """Mock async context manager for Light.connect."""

    def __init__(self, light: MagicMock | Device) -> None:
        """Initialize the mock context manager."""
        self._light = light

    async def __aenter__(self) -> MagicMock | Device:
        """Enter the context manager."""
        return self._light

    async def __aexit__(self, *args: object) -> None:
        """Exit the context manager."""


_original_coordinator_init = LIFXUpdateCoordinator.__init__


def _patch_device(device: MagicMock | None = None, no_device: bool = False) -> Any:
    """Patch device communication to use a mock light."""
    if no_device:
        # Simulate connection failure via ExceptionGroup for except* handling
        async def mock_connect_fail(**kwargs: Any) -> _MockAsyncContextManager:
            raise ExceptionGroup("connect failed", [LifxTimeoutError("timeout")])

        return patch(
            "homeassistant.components.lifx.Light.connect",
            side_effect=mock_connect_fail,
        )

    mock_light = device or _mocked_bulb()

    async def mock_connect(**kwargs: Any) -> _MockAsyncContextManager:
        return _MockAsyncContextManager(mock_light)

    def patched_init(
        self: LIFXUpdateCoordinator,
        hass: Any,
        entry: Any,
        state: Any,
        light_type: Any,
    ) -> None:
        _original_coordinator_init(self, hass, entry, state, light_type)
        self.light = mock_light

    return _combined_patch(
        patch(
            "homeassistant.components.lifx.Light.connect",
            side_effect=mock_connect,
        ),
        patch.object(LIFXUpdateCoordinator, "__init__", patched_init),
    )


def _patch_discovery(device: MagicMock | None = None, no_device: bool = False) -> Any:
    """Patch out discovery."""

    async def mock_discover(**kwargs: Any) -> Any:
        if not no_device:
            yield device or _mocked_bulb()

    return patch(
        "homeassistant.components.lifx.discovery.discover",
        side_effect=mock_discover,
    )


def _patch_config_flow_try_connect(
    device: MagicMock | None = None, no_device: bool = False
) -> Any:
    """Patch Device.connect used in config flow."""
    if no_device:

        async def mock_connect_fail(**kwargs: Any) -> _MockAsyncContextManager:
            raise LifxTimeoutError("timeout")

        return patch(
            "homeassistant.components.lifx.config_flow.Device.connect",
            side_effect=mock_connect_fail,
        )

    mock_light = device or _mocked_bulb()

    # If the device mock has a get_color side_effect that is an exception,
    # raise it from Device.connect to simulate connection-level errors
    get_color_side_effect = getattr(mock_light.get_color, "side_effect", None)
    if isinstance(get_color_side_effect, Exception):

        async def mock_connect_error(**kwargs: Any) -> _MockAsyncContextManager:
            raise get_color_side_effect

        return patch(
            "homeassistant.components.lifx.config_flow.Device.connect",
            side_effect=mock_connect_error,
        )

    async def mock_connect(**kwargs: Any) -> _MockAsyncContextManager:
        return _MockAsyncContextManager(mock_light)

    return patch(
        "homeassistant.components.lifx.config_flow.Device.connect",
        side_effect=mock_connect,
    )


@contextmanager
def _combined_patch(*patches: Any) -> Any:
    """Combine multiple context-manager patches into one."""
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        yield
