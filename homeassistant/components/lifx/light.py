"""LIFX light entity platform."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from lifx import HSBK, FirmwareEffect
from propcache.api import cached_property
import voluptuous as vol

from homeassistant.components.light import (
    ATTR_EFFECT,
    ATTR_TRANSITION,
    LIGHT_TURN_ON_SCHEMA,
    ColorMode,
    LightEntity,
    LightEntityDescription,
    LightEntityFeature,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.typing import VolDictType

from .const import (
    ATTR_DURATION,
    ATTR_INFRARED,
    ATTR_POWER,
    ATTR_ZONES,
    CEILING_DOWNLIGHT_SUFFIX,
    CEILING_UPLIGHT_SUFFIX,
    DATA_LIFX_MANAGER,
    DOMAIN,
)
from .coordinator import LIFXConfigEntry, LIFXUpdateCoordinator
from .entity import LIFXEntity
from .manager import (
    SERVICE_EFFECT_COLORLOOP,
    SERVICE_EFFECT_FLAME,
    SERVICE_EFFECT_MORPH,
    SERVICE_EFFECT_MOVE,
    SERVICE_EFFECT_PULSE,
    SERVICE_EFFECT_SKY,
    SERVICE_EFFECT_STOP,
)
from .util import generate_hsbk

if TYPE_CHECKING:
    from lifx import LIFXEffect

LIFX_STATE_SETTLE_DELAY = 0.3

SERVICE_LIFX_SET_STATE = "set_state"

LIFX_SET_STATE_SCHEMA: VolDictType = {
    **LIGHT_TURN_ON_SCHEMA,
    ATTR_INFRARED: vol.All(vol.Coerce(int), vol.Clamp(min=0, max=255)),
    ATTR_ZONES: vol.All(cv.ensure_list, [cv.positive_int]),
    ATTR_POWER: cv.boolean,
}

SERVICE_LIFX_SET_HEV_CYCLE_STATE = "set_hev_cycle_state"

LIFX_SET_HEV_CYCLE_STATE_SCHEMA: VolDictType = {
    ATTR_POWER: vol.Required(cv.boolean),
    ATTR_DURATION: vol.All(vol.Coerce(float), vol.Clamp(min=0, max=86400)),
}

CEILING_UPLIGHT_DESCRIPTION = LightEntityDescription(
    key=CEILING_UPLIGHT_SUFFIX,
    translation_key="uplight",
    entity_registry_enabled_default=False,
)

CEILING_DOWNLIGHT_DESCRIPTION = LightEntityDescription(
    key=CEILING_DOWNLIGHT_SUFFIX,
    translation_key="downlight",
    entity_registry_enabled_default=False,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LIFXConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up LIFX light platform."""
    coordinator = entry.runtime_data
    manager = hass.data[DATA_LIFX_MANAGER]

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_LIFX_SET_STATE,
        LIFX_SET_STATE_SCHEMA,
        "set_state",
    )
    platform.async_register_entity_service(
        SERVICE_LIFX_SET_HEV_CYCLE_STATE,
        LIFX_SET_HEV_CYCLE_STATE_SCHEMA,
        "set_hev_cycle_state",
    )

    entities: list[LightEntity] = []
    capabilities = coordinator.data.state.capabilities

    if coordinator.has_ceiling:
        entities.append(LIFXCeilingLight(coordinator, manager, entry))
        entities.append(
            LIFXCeilingUplightLight(coordinator, CEILING_UPLIGHT_DESCRIPTION)
        )
        entities.append(
            LIFXCeilingDownlightLight(coordinator, CEILING_DOWNLIGHT_DESCRIPTION)
        )
    elif capabilities.has_matrix:
        entities.append(LIFXMatrixLight(coordinator, manager, entry))
    elif capabilities.has_multizone:
        entities.append(LIFXMultiZoneLight(coordinator, manager, entry))
    elif capabilities.has_color:
        entities.append(LIFXColorLight(coordinator, manager, entry))
    else:
        entities.append(LIFXLight(coordinator, manager, entry))

    async_add_entities(entities)


class LIFXLight(LIFXEntity, LightEntity):
    """Representation of a LIFX light."""

    _attr_supported_features = LightEntityFeature.TRANSITION | LightEntityFeature.EFFECT
    _attr_name = None
    _attr_effect_list = [SERVICE_EFFECT_PULSE, SERVICE_EFFECT_STOP]

    def __init__(
        self,
        coordinator: LIFXUpdateCoordinator,
        manager: Any,
        entry: LIFXConfigEntry,
    ) -> None:
        """Initialize the light entity."""
        super().__init__(coordinator)
        self.entry = entry
        self.manager = manager
        self.postponed_update: CALLBACK_TYPE | None = None

        self._attr_unique_id = coordinator.serial
        capabilities = coordinator.data.state.capabilities
        max_kelvin = capabilities.kelvin_max
        min_kelvin = capabilities.kelvin_min

        self._attr_min_color_temp_kelvin = (
            min_kelvin if min_kelvin is not None else 1500
        )
        self._attr_max_color_temp_kelvin = (
            max_kelvin if max_kelvin is not None else 9000
        )
        if min_kelvin != max_kelvin:
            color_mode = ColorMode.COLOR_TEMP
        else:
            color_mode = ColorMode.BRIGHTNESS
        self._attr_color_mode = color_mode
        self._attr_supported_color_modes = {color_mode}
        self._attr_effect = None
        self._async_update_attrs()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._async_update_attrs()
        super()._handle_coordinator_update()

    @callback
    def _async_update_attrs(self) -> None:
        """Handle coordinator updates."""
        sw_effect: LIFXEffect | None
        fw_effect: FirmwareEffect | None

        self._attr_is_on = self.coordinator.data.is_on
        self._attr_brightness = self.coordinator.data.brightness
        self._attr_color_temp_kelvin = self.coordinator.data.kelvin

        if sw_effect := self.manager.effects_conductor.effect(self.coordinator.light):
            self._attr_effect = f"effect_{sw_effect.name}"
        elif (
            self.coordinator.data.state.capabilities.has_multizone
            or self.coordinator.data.state.capabilities.has_matrix
        ):
            if fw_effect := self.coordinator.async_get_active_effect():
                self._attr_effect = f"effect_{fw_effect.name.lower()}"
            else:
                self._attr_effect = None
        else:
            self._attr_effect = None

    async def async_added_to_hass(self) -> None:
        """Register callbacks when added to hass."""
        self.async_on_remove(
            self.manager.async_register_entity(self.entity_id, self.coordinator)
        )
        return await super().async_added_to_hass()

    def _cancel_postponed_update(self) -> None:
        """Cancel postponed update, if applicable."""
        if self.postponed_update:
            self.postponed_update()
            self.postponed_update = None

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        self._cancel_postponed_update()
        self.manager.async_unregister_entity(self.entity_id)
        return await super().async_will_remove_from_hass()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn this light on."""
        await self.set_state(**{**kwargs, ATTR_POWER: True})

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn this light off."""
        await self.set_state(**{**kwargs, ATTR_POWER: False})

    async def update_during_transition(self, when: int) -> None:
        """Update state at the start and end of a transition."""
        self._cancel_postponed_update()

        # Transition has started
        self.async_write_ha_state()

        # Request a refresh to get a fresh state
        await self.coordinator.async_request_refresh()

        # Transition has ended
        if when > 0:

            async def _async_refresh(now: datetime) -> None:
                """Refresh the state."""
                await self.coordinator.async_refresh()

            self.postponed_update = async_call_later(
                self.hass,
                timedelta(seconds=when),
                _async_refresh,
            )

    async def _async_set_zones_color(
        self, zones: list[int], color: HSBK, duration: float = 0.0
    ) -> None:
        """Set color for specific zones on a multizone light.

        For extended multizone lights, gets current state and updates only
        targeted zones in one or two packets. For legacy lights, groups zones
        into contiguous ranges.

        Args:
            zones: List of zone indices:
                   - [index]: Set single zone
                   - [z1, z2, z3, ...]: Set specific zones (grouped into ranges)
            color: The HSBK color to set
            duration: Transition duration in seconds

        """
        if not zones:
            return

        # For extended multizone: get current state, update targeted zones,
        # then send all zones in one or two packets (most efficient method)
        device = self.coordinator.light
        if (
            device.capabilities
            and device.capabilities.has_extended_multizone
            and hasattr(self.coordinator.data.state, "zones")
        ):
            # Get current zone colors
            current_zones = list(self.coordinator.data.state.zones)

            # Individual zones
            zones_to_update = {zone for zone in zones if 0 <= zone < len(current_zones)}
            if not zones_to_update:
                return

            # Update only the targeted zones
            for zone_idx in zones_to_update:
                if 0 <= zone_idx < len(current_zones):
                    current_zones[zone_idx] = color

            # Send all zones via extended multizone message
            await self.coordinator.async_set_extended_color_zones(
                colors=current_zones,
                duration=duration,
            )
            return

        # Group individual zones into contiguous ranges for legacy lights
        zone_count: int | None = getattr(
            self.coordinator.data.state, "zone_count", None
        )
        if zone_count is None and hasattr(self.coordinator.data.state, "zones"):
            zone_count = len(self.coordinator.data.state.zones)

        zones_sorted = sorted(set(zones))  # Remove duplicates and sort
        if zone_count is not None:
            zones_sorted = [zone for zone in zones_sorted if 0 <= zone < zone_count]
            if not zones_sorted:
                return
        ranges: list[tuple[int, int]] = []
        start = zones_sorted[0]
        end = zones_sorted[0]

        for zone in zones_sorted[1:]:
            if zone == end + 1:
                # Contiguous zone, extend the range
                end = zone
            else:
                # Gap found, save current range and start new one
                ranges.append((start, end))
                start = end = zone

        # Add the final range
        ranges.append((start, end))

        # Set color for each range
        for start_index, end_index in ranges:
            await self.coordinator.async_set_color_zones(
                start_index=start_index,
                end_index=end_index,
                color=color,
                duration=duration,
            )

    async def set_state(self, **kwargs: Any) -> None:
        """Change the state of this light."""
        await self.manager.effects_conductor.stop([self.coordinator.light])

        if ATTR_EFFECT in kwargs:
            await self.default_effect(**kwargs)
            return

        if ATTR_INFRARED in kwargs:
            infrared_value = kwargs.pop(ATTR_INFRARED) / 255
            await self.coordinator.async_set_infrared(infrared_value)

        # Handle zones parameter for multizone lights
        zones = kwargs.pop(ATTR_ZONES, None)

        duration = kwargs.get(ATTR_TRANSITION, 0)
        if ATTR_POWER in kwargs:
            power_on = kwargs[ATTR_POWER]
            power_off = not kwargs[ATTR_POWER]
        else:
            power_on = False
            power_off = False

        is_on = self.coordinator.data.is_on
        color = generate_hsbk(self.coordinator.data.state.color, is_on, **kwargs)

        if not is_on:
            if power_off:
                await self.coordinator.async_set_power(False)
            if color and power_on:
                # Set color first, then power on so the transition is visible
                if zones and self.coordinator.data.state.capabilities.has_multizone:
                    await self._async_set_zones_color(zones, color, duration)
                else:
                    await self.coordinator.async_set_color(color)
                await self.coordinator.async_set_power(True, duration)
            elif color:
                if zones and self.coordinator.data.state.capabilities.has_multizone:
                    await self._async_set_zones_color(zones, color, duration)
                else:
                    await self.coordinator.async_set_color(color, duration)
            elif (
                power_on
            ):  # pragma: no cover - generate_hsbk always returns a truthy HSBK
                await self.coordinator.async_set_power(True, duration)
        else:
            if power_on:
                await self.coordinator.async_set_power(True)
            if color:
                if zones and self.coordinator.data.state.capabilities.has_multizone:
                    await self._async_set_zones_color(zones, color, duration)
                else:
                    await self.coordinator.async_set_color(color, duration)
            if power_off:
                await self.coordinator.async_set_power(False, duration)

        # Avoid state ping-pong by holding off updates as the state settles
        await asyncio.sleep(LIFX_STATE_SETTLE_DELAY)

        # Update when the transition starts and ends
        await self.update_during_transition(duration)

    async def set_hev_cycle_state(
        self, power: bool, duration: int | None = None
    ) -> None:
        """Set the state of the HEV LEDs on a LIFX Clean light."""
        if not self.coordinator.data.state.capabilities.has_hev:
            raise HomeAssistantError(
                "This device does not support setting HEV cycle state"
            )

        await self.coordinator.async_set_hev_cycle_state(power, duration or 0)
        await self.update_during_transition(duration or 0)

    async def default_effect(self, **kwargs: Any) -> None:
        """Start an effect with default parameters."""
        await self.hass.services.async_call(
            DOMAIN,
            kwargs[ATTR_EFFECT],
            {ATTR_ENTITY_ID: self.entity_id},
            context=self._context,
        )


class LIFXColorLight(LIFXLight):
    """Representation of a color LIFX light."""

    _attr_effect_list = [
        SERVICE_EFFECT_COLORLOOP,
        SERVICE_EFFECT_PULSE,
        SERVICE_EFFECT_STOP,
    ]

    @callback
    def _async_update_attrs(self) -> None:
        """Update attrs from coordinator."""
        self._attr_color_mode = (
            ColorMode.HS
            if self.coordinator.data.state.color.saturation > 0
            else ColorMode.COLOR_TEMP
        )
        self._attr_hs_color = self.coordinator.data.hs_color
        return super()._async_update_attrs()

    @cached_property
    def supported_color_modes(self) -> set[ColorMode]:
        """Return the supported color modes."""
        return {ColorMode.COLOR_TEMP, ColorMode.HS}


class LIFXMultiZoneLight(LIFXColorLight):
    """Representation of a LIFX multizone light."""

    _attr_effect_list = [
        SERVICE_EFFECT_COLORLOOP,
        SERVICE_EFFECT_MOVE,
        SERVICE_EFFECT_PULSE,
        SERVICE_EFFECT_STOP,
    ]


class LIFXMatrixLight(LIFXColorLight):
    """Representation of a LIFX matrix light."""

    _attr_effect_list = [
        SERVICE_EFFECT_COLORLOOP,
        SERVICE_EFFECT_FLAME,
        SERVICE_EFFECT_MORPH,
        SERVICE_EFFECT_PULSE,
        SERVICE_EFFECT_SKY,
        SERVICE_EFFECT_STOP,
    ]


class LIFXCeilingLight(LIFXMatrixLight):
    """Representation of a LIFX Ceiling light (parent entity)."""


class LIFXCeilingUplightLight(LIFXEntity, LightEntity):
    """Representation of a LIFX Ceiling uplight component."""

    _attr_supported_features = LightEntityFeature.TRANSITION
    _attr_supported_color_modes = {ColorMode.COLOR_TEMP, ColorMode.HS}

    def __init__(
        self,
        coordinator: LIFXUpdateCoordinator,
        description: LightEntityDescription,
    ) -> None:
        """Initialize the uplight entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.serial}{description.key}"
        caps = coordinator.data.state.capabilities
        if caps.kelvin_min is not None:
            self._attr_min_color_temp_kelvin = caps.kelvin_min
        if caps.kelvin_max is not None:
            self._attr_max_color_temp_kelvin = caps.kelvin_max
        self._async_update_attrs()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._async_update_attrs()
        super()._handle_coordinator_update()

    @callback
    def _async_update_attrs(self) -> None:
        """Handle coordinator updates."""
        self._attr_is_on = self.coordinator.uplight_is_on
        color = self.coordinator.uplight_color
        if color is not None:
            self._attr_brightness = round(color.brightness * 255)
            self._attr_hs_color = (color.hue, color.saturation * 100)
            self._attr_color_temp_kelvin = color.kelvin
            self._attr_color_mode = (
                ColorMode.COLOR_TEMP if color.saturation == 0 else ColorMode.HS
            )
        else:
            self._attr_brightness = None
            self._attr_hs_color = None
            self._attr_color_temp_kelvin = None
            self._attr_color_mode = ColorMode.HS

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the uplight."""
        duration = kwargs.pop(ATTR_TRANSITION, 0)
        await self.coordinator.async_turn_uplight_on(duration=duration, **kwargs)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the uplight."""
        duration = kwargs.get(ATTR_TRANSITION, 0)
        await self.coordinator.async_turn_uplight_off(duration=duration)
        await self.coordinator.async_request_refresh()


class LIFXCeilingDownlightLight(LIFXEntity, LightEntity):
    """Representation of a LIFX Ceiling downlight component."""

    _attr_supported_features = LightEntityFeature.TRANSITION
    _attr_supported_color_modes = {ColorMode.COLOR_TEMP, ColorMode.HS}

    def __init__(
        self,
        coordinator: LIFXUpdateCoordinator,
        description: LightEntityDescription,
    ) -> None:
        """Initialize the downlight entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.serial}{description.key}"
        caps = coordinator.data.state.capabilities
        if caps.kelvin_min is not None:
            self._attr_min_color_temp_kelvin = caps.kelvin_min
        if caps.kelvin_max is not None:
            self._attr_max_color_temp_kelvin = caps.kelvin_max
        self._async_update_attrs()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._async_update_attrs()
        super()._handle_coordinator_update()

    @callback
    def _async_update_attrs(self) -> None:
        """Handle coordinator updates."""
        self._attr_is_on = self.coordinator.downlight_is_on
        colors = self.coordinator.downlight_colors
        if colors:
            self._attr_brightness = round(max(c.brightness for c in colors) * 255)
            first_color = colors[0]
            self._attr_hs_color = (first_color.hue, first_color.saturation * 100)
            self._attr_color_temp_kelvin = first_color.kelvin
            self._attr_color_mode = (
                ColorMode.COLOR_TEMP if first_color.saturation == 0 else ColorMode.HS
            )
        else:
            self._attr_brightness = None
            self._attr_hs_color = None
            self._attr_color_temp_kelvin = None
            self._attr_color_mode = ColorMode.HS

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the downlight."""
        duration = kwargs.pop(ATTR_TRANSITION, 0)
        await self.coordinator.async_turn_downlight_on(duration=duration, **kwargs)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the downlight."""
        duration = kwargs.get(ATTR_TRANSITION, 0)
        await self.coordinator.async_turn_downlight_off(duration=duration)
        await self.coordinator.async_request_refresh()
