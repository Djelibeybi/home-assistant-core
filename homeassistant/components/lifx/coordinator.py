"""DataUpdateCoordinator for the LIFX integration."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import contextlib
from dataclasses import dataclass
from math import floor, log10
from typing import Any

from awesomeversion import AwesomeVersion
from lifx import (
    HSBK,
    CeilingLight,
    CeilingLightState,
    Direction,
    FirmwareEffect,
    HevLight,
    HevLightState,
    InfraredLight,
    InfraredLightState,
    LifxConnectionError,
    LifxError,
    LifxTimeoutError,
    Light,
    LightState,
    MatrixLight,
    MatrixLightState,
    MultiZoneEffect,
    MultiZoneLight,
    MultiZoneLightState,
    Theme,
    ThemeLibrary,
)
from lifx.protocol.protocol_types import MultiZoneApplicationRequest, TileEffectSkyType

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_BRIGHTNESS_PCT,
    ATTR_BRIGHTNESS_STEP,
    ATTR_BRIGHTNESS_STEP_PCT,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
    SIGNAL_STRENGTH_DECIBELS,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    Platform,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    _LOGGER,
    CONF_SERIAL,
    DEFAULT_BRIGHTNESS,
    DEVICE_RETRIES,
    DEVICE_TIMEOUT,
    DEVICE_UNAVAILABLE_RETRIES,
    DOMAIN,
    IDENTIFY_DELAY,
    IDENTIFY_WAVEFORM,
    INFRARED_BRIGHTNESS_VALUES_MAP,
    LIFX_DEFAULT_PORT,
    REQUEST_REFRESH_DELAY,
    RSSI_DBM_FW,
    SCAN_INTERVAL,
)
from .util import generate_hsbk, normalize_serial

type LifxLightTypes = (
    Light | HevLight | InfraredLight | MatrixLight | MultiZoneLight | CeilingLight
)
type LifxLightStateTypes = (
    LightState
    | HevLightState
    | InfraredLightState
    | MatrixLightState
    | MultiZoneLightState
    | CeilingLightState
)
type LifxTypes = type[
    CeilingLight | HevLight | InfraredLight | Light | MatrixLight | MultiZoneLight
]

type LIFXConfigEntry = ConfigEntry[LIFXUpdateCoordinator]


@dataclass
class LifxLightState:
    """Device state information for a LIFX light."""

    state: LifxLightStateTypes
    rssi: int | None = None

    @property
    def is_on(self) -> bool:
        """Return true if light is on."""
        return bool(self.state.power > 0)

    @property
    def hs_color(self) -> tuple[float, float]:
        """Return hue and saturation as a tuple."""
        return self.state.color.hue, self.state.color.saturation * 100

    @property
    def brightness(self) -> int:
        """Return brightness scaled to 0-255."""
        return int(round(self.state.color.brightness * 255))

    @property
    def kelvin(self) -> int:
        """Return the current kelvin value."""
        return int(self.state.color.kelvin)

    @property
    def sw_version(self) -> str:
        """Return the host firmware version."""
        major = self.state.host_firmware.version_major
        minor = self.state.host_firmware.version_minor
        return f"{major}.{minor}"

    @property
    def rssi_uom(self) -> str:
        """Return the RSSI unit of measurement."""
        if AwesomeVersion(self.sw_version) <= RSSI_DBM_FW:
            return SIGNAL_STRENGTH_DECIBELS
        return SIGNAL_STRENGTH_DECIBELS_MILLIWATT

    @property
    def group_name(self) -> str:
        """Return the group name."""
        return str(self.state.group.label)


class LIFXUpdateCoordinator(DataUpdateCoordinator[LifxLightState]):
    """DataUpdateCoordinator to gather data for a specific LIFX device."""

    config_entry: LIFXConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: LIFXConfigEntry,
        state: LifxLightState,
        light_type: LifxTypes,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{entry.title} ({entry.data[CONF_HOST]})",
            update_interval=SCAN_INTERVAL,
            request_refresh_debouncer=Debouncer(
                hass, _LOGGER, cooldown=REQUEST_REFRESH_DELAY, immediate=False
            ),
        )
        self.entry = entry
        self.light: LifxLightTypes = light_type(
            serial=normalize_serial(entry.data[CONF_SERIAL]),
            ip=entry.data[CONF_HOST],
            port=entry.data.get(CONF_PORT, LIFX_DEFAULT_PORT),
            timeout=DEVICE_TIMEOUT,
            max_retries=DEVICE_RETRIES,
        )
        self.active_effect = FirmwareEffect.OFF
        self.last_used_theme: str = ""
        self._update_rssi: bool = False
        self._update_attempts: int = 0
        self._last_state: LifxLightState | None = state
        self.async_set_updated_data(state)

    @property
    def serial(self) -> str:
        """Return the serial number."""
        return normalize_serial(self.light.serial)

    @property
    def label(self) -> str:
        """Return the label of the light."""
        return str(self.data.state.label)

    @property
    def mac_address(self) -> str:
        """Return the MAC address from state."""
        return str(self.data.state.mac_address)

    @property
    def current_infrared_brightness(self) -> str | None:
        """Return the current infrared brightness as a string."""
        if not isinstance(self.data.state, InfraredLightState):
            return None
        value = self.data.state.infrared
        return INFRARED_BRIGHTNESS_VALUES_MAP.get(value)

    @property
    def has_ceiling(self) -> bool:
        """Return True if device is a LIFX Ceiling."""
        return isinstance(self.light, CeilingLight)

    @property
    def uplight_is_on(self) -> bool:
        """Return true if the uplight is on."""
        if not isinstance(self.data.state, CeilingLightState):
            return False
        return self.data.state.uplight_is_on

    @property
    def downlight_is_on(self) -> bool:
        """Return true if the downlight is on."""
        if not isinstance(self.data.state, CeilingLightState):
            return False
        return self.data.state.downlight_is_on

    @property
    def uplight_color(self) -> HSBK | None:
        """Return the uplight color."""
        if not isinstance(self.data.state, CeilingLightState):
            return None
        return self.data.state.uplight_color

    @property
    def downlight_colors(self) -> list[HSBK] | None:
        """Return the downlight colors."""
        if not isinstance(self.data.state, CeilingLightState):
            return None
        return self.data.state.downlight_colors

    async def async_close(self) -> None:
        """Close the connection."""
        await self._async_close_light()

    async def _async_close_light(self) -> None:
        """Close the device connection without masking primary errors."""
        try:
            await self.light.close()
        except LifxError as err:
            _LOGGER.debug("Failed to close connection: %s", err)

    async def _async_update_data(self) -> LifxLightState:
        """Fetch volatile state data from the light."""
        try:
            await self.light.refresh_state()

        except (LifxConnectionError, LifxTimeoutError) as err:
            self._update_attempts += 1
            if (
                self._update_attempts > DEVICE_UNAVAILABLE_RETRIES
                or self._last_state is None
            ):
                self._update_attempts = 0
                message = (
                    f"Timed out trying to update {self.entry.title}"
                    if isinstance(err, LifxTimeoutError)
                    else f"Error trying to connect to {self.entry.title}"
                )
                raise UpdateFailed(message) from err
            _LOGGER.debug("Transient update failure for %s: %s", self.entry.title, err)
            return self._last_state
        else:
            new_state = LifxLightState(state=self.light.state)
            wifi_info = None

            if self._update_rssi:
                with contextlib.suppress(LifxConnectionError, LifxTimeoutError):
                    wifi_info = await self.light.get_wifi_info()

            if wifi_info is not None:
                new_state.rssi = int(floor(10 * log10(wifi_info.signal) + 0.5))

            self._update_attempts = max(self._update_attempts - 1, 0)

            if isinstance(
                new_state.state,
                MatrixLightState | MultiZoneLightState | CeilingLightState,
            ):
                self.active_effect = new_state.state.effect

            self._last_state = new_state
            return new_state

        finally:
            await self._async_close_light()

    def async_get_entity_id(self, platform: Platform, key: str) -> str | None:
        """Return the entity_id from the platform and key provided."""
        ent_reg = er.async_get(self.hass)
        return ent_reg.async_get_entity_id(platform, DOMAIN, f"{self.serial}_{key}")

    def async_get_active_effect(self) -> FirmwareEffect:
        """Return the currently active firmware effect."""
        return self.active_effect

    async def async_set_power(self, state: bool, duration: float = 0.0) -> None:
        """Set power on the light."""
        try:
            await self.light.set_power(state, duration)
        except (LifxTimeoutError, LifxConnectionError) as ex:
            raise HomeAssistantError(
                f"Failed to set power for {self.entry.title}"
            ) from ex

    async def async_set_color(self, color: HSBK, duration: float = 0.0) -> None:
        """Set color on the light."""
        try:
            await self.light.set_color(color, duration)
        except (LifxTimeoutError, LifxConnectionError) as ex:
            raise HomeAssistantError(
                f"Failed to set color for {self.entry.title}"
            ) from ex

    async def async_set_color_zones(
        self,
        start_index: int,
        end_index: int,
        color: HSBK,
        duration: float = 0.0,
        apply: MultiZoneApplicationRequest = MultiZoneApplicationRequest.APPLY,
    ) -> None:
        """Set color zones on a multizone light."""
        if isinstance(self.light, MultiZoneLight):
            try:
                await self.light.set_color_zones(
                    start=start_index,
                    end=end_index,
                    color=color,
                    duration=duration,
                    apply=apply,
                )
            except (LifxTimeoutError, LifxConnectionError) as ex:
                raise HomeAssistantError(
                    f"Failed to set color zones for {self.entry.title}"
                ) from ex

    async def async_set_extended_color_zones(
        self,
        colors: list[HSBK],
        duration: float = 0.0,
        apply: MultiZoneApplicationRequest = MultiZoneApplicationRequest.APPLY,
    ) -> None:
        """Set extended color zones on a multizone light."""
        if isinstance(self.light, MultiZoneLight):
            try:
                await self.light.set_extended_color_zones(
                    zone_index=0,
                    colors=colors,
                    duration=duration,
                    apply=apply,
                )
            except (LifxTimeoutError, LifxConnectionError) as ex:
                raise HomeAssistantError(
                    f"Failed to set extended color zones for {self.entry.title}"
                ) from ex

    async def async_set_multizone_effect(
        self,
        effect_type: FirmwareEffect,
        speed: float = 3.0,
        direction: str | Direction | None = None,
        theme_name: str | None = None,
        power_on: bool = True,
    ) -> None:
        """Control the firmware-based Move effect on a multizone device."""
        if isinstance(self.light, MultiZoneLight):
            if power_on and self.data.state.power == 0:
                await self.async_set_power(True, 0)

            if theme_name is not None:
                theme = ThemeLibrary.get(theme_name)
                await self.light.apply_theme(theme, power_on, speed)

            if isinstance(direction, str):
                direction_map = {
                    "right": Direction.FORWARD,
                    "left": Direction.REVERSED,
                    "forward": Direction.FORWARD,
                    "reversed": Direction.REVERSED,
                }
                direction = direction_map.get(direction.lower(), Direction.FORWARD)
            elif direction is None:
                direction = Direction.FORWARD

            effect = MultiZoneEffect(effect_type=effect_type, speed=round(speed * 1000))
            if effect_type == FirmwareEffect.MOVE:
                effect.direction = direction

            await self.light.set_effect(effect)
            self.active_effect = effect_type

    async def async_set_matrix_effect(
        self,
        effect_type: FirmwareEffect,
        speed: float = 3.0,
        palette: list[HSBK] | None = None,
        power_on: bool = True,
        sky_type: str | None = None,
        cloud_saturation_min: int = 0,
        cloud_saturation_max: int = 0,
    ) -> None:
        """Control the firmware-based effects on a matrix device."""
        if isinstance(self.light, MatrixLight):
            if power_on and self.data.state.power == 0:
                await self.async_set_power(True, 0)

            tile_effect_sky_type = (
                TileEffectSkyType[sky_type.upper()]
                if sky_type is not None
                else TileEffectSkyType.SUNRISE
            )

            await self.light.set_effect(
                effect_type=effect_type,
                speed=speed,
                palette=palette,
                sky_type=tile_effect_sky_type,
                cloud_saturation_max=cloud_saturation_max,
                cloud_saturation_min=cloud_saturation_min,
            )
            self.active_effect = effect_type

    async def async_set_infrared(self, brightness: float) -> None:
        """Set infrared brightness on an infrared light."""
        if isinstance(self.light, InfraredLight):
            await self.light.set_infrared(brightness)

    async def async_set_infrared_brightness(self, option: str) -> None:
        """Set infrared brightness from a named option."""
        option_values = {v: k for k, v in INFRARED_BRIGHTNESS_VALUES_MAP.items()}
        if (brightness := option_values.get(option)) is not None:
            await self.async_set_infrared(brightness)

    async def async_turn_uplight_on(self, duration: float = 0.0, **kwargs: Any) -> None:
        """Turn on the uplight component.

        Computes the target HSBK from current state and kwargs.
        If no color attributes provided and component is off, lets lifx-async
        determine appropriate default brightness.
        """
        if not isinstance(self.light, CeilingLight):
            return

        current = await self.light.get_uplight_color()
        has_color_attrs = any(
            attr in kwargs
            for attr in (
                ATTR_BRIGHTNESS,
                ATTR_BRIGHTNESS_PCT,
                ATTR_BRIGHTNESS_STEP,
                ATTR_BRIGHTNESS_STEP_PCT,
                ATTR_HS_COLOR,
                ATTR_COLOR_TEMP_KELVIN,
            )
        )

        if has_color_attrs:
            hsbk = generate_hsbk(current, self.uplight_is_on, **kwargs)
            if hsbk.brightness == 0:
                if (
                    hsbk.hue == current.hue
                    and hsbk.saturation == current.saturation
                    and hsbk.kelvin == current.kelvin
                ):
                    await self.light.turn_uplight_on(duration=duration)
                    return
                current = HSBK(
                    current.hue,
                    current.saturation,
                    DEFAULT_BRIGHTNESS,
                    current.kelvin,
                )
                hsbk = generate_hsbk(current, self.uplight_is_on, **kwargs)
                await self.light.turn_uplight_on(color=hsbk, duration=duration)
                return

            await self.light.turn_uplight_on(color=hsbk, duration=duration)
        else:
            await self.light.turn_uplight_on(duration=duration)

    async def async_turn_uplight_off(self, duration: float = 0.0) -> None:
        """Turn off the uplight component."""
        if isinstance(self.light, CeilingLight):
            if not self.downlight_is_on:
                await self.async_set_power(False, duration)
            else:
                await self.light.turn_uplight_off(self.uplight_color, duration=duration)

    async def async_turn_downlight_on(
        self, duration: float = 0.0, **kwargs: Any
    ) -> None:
        """Turn on the downlight component.

        Computes the target HSBK from current state and kwargs.
        If no color attributes provided, delegates to lifx-async to handle defaults.
        """
        if not isinstance(self.light, CeilingLight):
            return

        colors = await self.light.get_downlight_colors()
        is_on = self.downlight_is_on
        has_color_attrs = any(
            attr in kwargs
            for attr in (
                ATTR_BRIGHTNESS,
                ATTR_BRIGHTNESS_PCT,
                ATTR_BRIGHTNESS_STEP,
                ATTR_BRIGHTNESS_STEP_PCT,
                ATTR_HS_COLOR,
                ATTR_COLOR_TEMP_KELVIN,
            )
        )

        if has_color_attrs:
            if colors:
                adjusted = [generate_hsbk(c, is_on, **kwargs) for c in colors]
                if all(c.brightness == 0 for c in adjusted):
                    hsk_changed = False
                    for index, c in enumerate(adjusted):
                        if (
                            c.hue != colors[index].hue
                            or c.saturation != colors[index].saturation
                            or c.kelvin != colors[index].kelvin
                        ):
                            hsk_changed = True
                            adjusted[index] = HSBK(
                                c.hue, c.saturation, DEFAULT_BRIGHTNESS, c.kelvin
                            )
                    if hsk_changed:
                        await self.light.turn_downlight_on(
                            colors=adjusted, duration=duration
                        )
                        return
                    await self.light.turn_downlight_on(duration=duration)
                    return
                await self.light.turn_downlight_on(colors=adjusted, duration=duration)
            else:
                default_color = HSBK(
                    hue=0, saturation=0, brightness=DEFAULT_BRIGHTNESS, kelvin=3500
                )
                hsbk = generate_hsbk(default_color, is_on, **kwargs)
                if hsbk.brightness == 0:
                    return
                await self.light.turn_downlight_on(colors=hsbk, duration=duration)
        else:
            await self.light.turn_downlight_on(duration=duration)

    async def async_turn_downlight_off(self, duration: float = 0.0) -> None:
        """Turn off the downlight component."""
        if isinstance(self.light, CeilingLight):
            if not self.uplight_is_on:
                await self.async_set_power(False, duration)
            else:
                await self.light.turn_downlight_off(
                    self.downlight_colors, duration=duration
                )

    async def async_identify_light(self) -> None:
        """Identify the device by flashing it three times."""
        if self.data.state.power > 0:
            await self.light.set_waveform(**IDENTIFY_WAVEFORM)
            return
        # Turn the light on first, flash for 3 seconds, then turn off
        await self.light.set_power(level=True, duration=1.0)
        await self.light.set_waveform(**IDENTIFY_WAVEFORM)
        await asyncio.sleep(IDENTIFY_DELAY)
        await self.light.set_power(level=False, duration=1.0)

    def async_enable_rssi_updates(self) -> Callable[[], None]:
        """Enable RSSI signal strength updates."""

        @callback
        def _async_disable_rssi_updates() -> None:
            """Disable RSSI updates when sensor removed."""
            self._update_rssi = False

        self._update_rssi = True
        return _async_disable_rssi_updates

    def async_get_hev_cycle_state(self) -> bool | None:
        """Return the current HEV cycle state."""
        if not isinstance(self.data.state, HevLightState):
            return None
        return bool(self.data.state.hev_cycle.remaining_s > 0)

    async def async_set_hev_cycle_state(self, enable: bool, duration: int = 0) -> None:
        """Start or stop an HEV cycle on a LIFX Clean light."""
        if isinstance(self.light, HevLight):
            await self.light.set_hev_cycle(enable, duration)

    async def async_apply_theme(
        self,
        theme_name: str = "",
        palette: list[HSBK] | None = None,
        power_on: bool = False,
        duration: float = 0.25,
    ) -> None:
        """Apply the selected theme to the device."""
        if palette and len(palette) > 0:
            theme = Theme(palette)
        elif theme_name:
            theme = ThemeLibrary.get(theme_name)
        else:
            raise HomeAssistantError(
                "Must provide either a theme name or a palette of colors"
            )

        await self.light.apply_theme(theme, power_on, duration)
        self.last_used_theme = theme_name

    async def diagnostics(self) -> dict[str, Any]:
        """Return diagnostic information about the device."""
        state = self.data.state
        device_data: dict[str, Any] = {
            "firmware": self.data.sw_version,
            "serial": self.serial,
            "model": state.model,
            "capabilities": {
                "has_color": state.capabilities.has_color,
                "has_multizone": state.capabilities.has_multizone,
                "has_matrix": state.capabilities.has_matrix,
                "has_infrared": state.capabilities.has_infrared,
                "has_hev": state.capabilities.has_hev,
            },
            "color": {
                "hue": state.color.hue,
                "saturation": state.color.saturation,
                "brightness": state.color.brightness,
                "kelvin": state.color.kelvin,
            },
            "power": state.power,
        }

        if isinstance(state, MultiZoneLightState):
            device_data["zones"] = {
                "count": state.zone_count,
                "colors": [
                    {
                        "hue": c.hue,
                        "saturation": c.saturation,
                        "brightness": c.brightness,
                        "kelvin": c.kelvin,
                    }
                    for c in state.zones
                ],
            }

        if isinstance(state, HevLightState):
            device_data["hev"] = {
                "cycle": {
                    "remaining": state.hev_cycle.remaining_s,
                },
            }

        if isinstance(state, InfraredLightState):
            device_data["infrared"] = {"brightness": state.infrared}

        if isinstance(state, MatrixLightState):
            device_data["matrix"] = {
                "effect": state.effect.name if state.effect else "OFF",
                "tile_count": state.tile_count,
            }

        return device_data
