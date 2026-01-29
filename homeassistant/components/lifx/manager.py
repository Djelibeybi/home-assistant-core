"""LIFX effects conductor and service manager."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from functools import partial
from typing import TYPE_CHECKING, Any

from lifx import (
    HSBK,
    Colors,
    Conductor,
    EffectColorloop,
    EffectPulse,
    FirmwareEffect,
    Light,
    Theme,
    ThemeLibrary,
)
import voluptuous as vol

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_BRIGHTNESS_PCT,
    ATTR_COLOR_NAME,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ATTR_RGB_COLOR,
    ATTR_TRANSITION,
    ATTR_XY_COLOR,
    COLOR_GROUP,
    VALID_BRIGHTNESS,
    VALID_BRIGHTNESS_PCT,
)
from homeassistant.const import ATTR_MODE
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.target import (
    TargetSelectorData,
    async_extract_referenced_entity_ids,
)

from .const import ATTR_THEME, DOMAIN
from .util import generate_hsbk

if TYPE_CHECKING:
    from .coordinator import LIFXUpdateCoordinator

SERVICE_EFFECT_COLORLOOP = "effect_colorloop"
SERVICE_EFFECT_FLAME = "effect_flame"
SERVICE_EFFECT_MORPH = "effect_morph"
SERVICE_EFFECT_MOVE = "effect_move"
SERVICE_EFFECT_PULSE = "effect_pulse"
SERVICE_EFFECT_SKY = "effect_sky"
SERVICE_EFFECT_STOP = "effect_stop"
SERVICE_PAINT_THEME = "paint_theme"

ATTR_CHANGE = "change"
ATTR_CLOUD_SATURATION_MIN = "cloud_saturation_min"
ATTR_CLOUD_SATURATION_MAX = "cloud_saturation_max"
ATTR_CYCLES = "cycles"
ATTR_DIRECTION = "direction"
ATTR_PALETTE = "palette"
ATTR_PERIOD = "period"
ATTR_POWER_OFF = "power_off"
ATTR_POWER_ON = "power_on"
ATTR_SATURATION_MAX = "saturation_max"
ATTR_SATURATION_MIN = "saturation_min"
ATTR_SKY_TYPE = "sky_type"
ATTR_SPEED = "speed"
ATTR_SPREAD = "spread"

EFFECT_FLAME_DEFAULT_SPEED = 3
EFFECT_MORPH_DEFAULT_SPEED = 3
EFFECT_MOVE_DEFAULT_SPEED = 3
EFFECT_MOVE_DEFAULT_DIRECTION = "right"
EFFECT_SKY_DEFAULT_SPEED = 50
EFFECT_SKY_DEFAULT_SKY_TYPE = "Clouds"
EFFECT_SKY_DEFAULT_CLOUD_SATURATION_MIN = 50
EFFECT_SKY_DEFAULT_CLOUD_SATURATION_MAX = 180

PAINT_THEME_DEFAULT_TRANSITION = 1

PULSE_MODE_BLINK = "blink"
PULSE_MODE_BREATHE = "breathe"
PULSE_MODE_PING = "ping"
PULSE_MODE_SOLID = "solid"
PULSE_MODE_STROBE = "strobe"

PULSE_MODES = [
    PULSE_MODE_BLINK,
    PULSE_MODE_BREATHE,
    PULSE_MODE_PING,
    PULSE_MODE_STROBE,
    PULSE_MODE_SOLID,
]

LIFX_EFFECT_SCHEMA = {
    vol.Optional(ATTR_POWER_ON, default=True): cv.boolean,
}

LIFX_EFFECT_PULSE_SCHEMA = cv.make_entity_service_schema(
    {
        **LIFX_EFFECT_SCHEMA,
        vol.Exclusive(ATTR_BRIGHTNESS, ATTR_BRIGHTNESS): VALID_BRIGHTNESS,
        vol.Exclusive(ATTR_BRIGHTNESS_PCT, ATTR_BRIGHTNESS): VALID_BRIGHTNESS_PCT,
        vol.Exclusive(ATTR_COLOR_NAME, COLOR_GROUP): cv.string,
        vol.Exclusive(ATTR_RGB_COLOR, COLOR_GROUP): vol.All(
            vol.Coerce(tuple), vol.ExactSequence((cv.byte, cv.byte, cv.byte))
        ),
        vol.Exclusive(ATTR_XY_COLOR, COLOR_GROUP): vol.All(
            vol.Coerce(tuple), vol.ExactSequence((cv.small_float, cv.small_float))
        ),
        vol.Exclusive(ATTR_HS_COLOR, COLOR_GROUP): vol.All(
            vol.Coerce(tuple),
            vol.ExactSequence(
                (
                    vol.All(vol.Coerce(float), vol.Range(min=0, max=360)),
                    vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
                )
            ),
        ),
        vol.Exclusive(ATTR_COLOR_TEMP_KELVIN, COLOR_GROUP): vol.All(
            vol.Coerce(int), vol.Range(min=1500, max=9000)
        ),
        ATTR_PERIOD: vol.All(vol.Coerce(float), vol.Range(min=0.05)),
        ATTR_CYCLES: vol.All(vol.Coerce(float), vol.Range(min=1)),
        ATTR_MODE: vol.In(PULSE_MODES),
    }
)

LIFX_EFFECT_COLORLOOP_SCHEMA = cv.make_entity_service_schema(
    {
        **LIFX_EFFECT_SCHEMA,
        vol.Exclusive(ATTR_BRIGHTNESS, ATTR_BRIGHTNESS): VALID_BRIGHTNESS,
        vol.Exclusive(ATTR_BRIGHTNESS_PCT, ATTR_BRIGHTNESS): VALID_BRIGHTNESS_PCT,
        ATTR_SATURATION_MAX: vol.All(vol.Coerce(int), vol.Clamp(min=0, max=100)),
        ATTR_SATURATION_MIN: vol.All(vol.Coerce(int), vol.Clamp(min=0, max=100)),
        ATTR_PERIOD: vol.All(vol.Coerce(float), vol.Clamp(min=0.05)),
        ATTR_CHANGE: vol.All(vol.Coerce(float), vol.Clamp(min=0, max=360)),
        ATTR_SPREAD: vol.All(vol.Coerce(float), vol.Clamp(min=0, max=360)),
        ATTR_TRANSITION: cv.positive_float,
    }
)

LIFX_EFFECT_STOP_SCHEMA = cv.make_entity_service_schema({})

LIFX_EFFECT_FLAME_SCHEMA = cv.make_entity_service_schema(
    {
        **LIFX_EFFECT_SCHEMA,
        ATTR_SPEED: vol.All(vol.Coerce(int), vol.Clamp(min=1, max=25)),
    }
)

HSBK_SCHEMA = vol.All(
    vol.Coerce(tuple),
    vol.ExactSequence(
        (
            vol.All(vol.Coerce(float), vol.Range(min=0, max=360)),
            vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
            vol.All(vol.Coerce(float), vol.Clamp(min=0, max=100)),
            vol.All(vol.Coerce(int), vol.Clamp(min=1500, max=9000)),
        )
    ),
)

LIFX_EFFECT_MORPH_SCHEMA = cv.make_entity_service_schema(
    {
        **LIFX_EFFECT_SCHEMA,
        ATTR_SPEED: vol.All(vol.Coerce(int), vol.Clamp(min=1, max=25)),
        vol.Exclusive(ATTR_THEME, COLOR_GROUP): vol.Optional(
            vol.In(ThemeLibrary.list())
        ),
        vol.Exclusive(ATTR_PALETTE, COLOR_GROUP): vol.All(
            cv.ensure_list, [HSBK_SCHEMA]
        ),
    }
)

LIFX_EFFECT_MOVE_SCHEMA = cv.make_entity_service_schema(
    {
        **LIFX_EFFECT_SCHEMA,
        ATTR_SPEED: vol.All(vol.Coerce(float), vol.Clamp(min=0.1, max=60)),
        ATTR_DIRECTION: vol.In(["left", "right"]),
        ATTR_THEME: vol.Optional(vol.In(ThemeLibrary.list())),
    }
)

LIFX_EFFECT_SKY_SCHEMA = cv.make_entity_service_schema(
    {
        **LIFX_EFFECT_SCHEMA,
        ATTR_SPEED: vol.All(vol.Coerce(int), vol.Clamp(min=1, max=86400)),
        ATTR_SKY_TYPE: vol.In(["Sunrise", "Sunset", "Clouds"]),
        ATTR_CLOUD_SATURATION_MIN: vol.All(vol.Coerce(int), vol.Clamp(min=0, max=255)),
        ATTR_CLOUD_SATURATION_MAX: vol.All(vol.Coerce(int), vol.Clamp(min=0, max=255)),
        ATTR_PALETTE: vol.All(cv.ensure_list, [HSBK_SCHEMA]),
    }
)

LIFX_PAINT_THEME_SCHEMA = cv.make_entity_service_schema(
    {
        **LIFX_EFFECT_SCHEMA,
        ATTR_TRANSITION: vol.All(vol.Coerce(int), vol.Clamp(min=1, max=3600)),
        vol.Exclusive(ATTR_THEME, COLOR_GROUP): vol.Optional(
            vol.In(ThemeLibrary.list())
        ),
        vol.Exclusive(ATTR_PALETTE, COLOR_GROUP): vol.All(
            cv.ensure_list, [HSBK_SCHEMA]
        ),
    }
)

SERVICES_SCHEMA = {
    SERVICE_EFFECT_COLORLOOP: LIFX_EFFECT_COLORLOOP_SCHEMA,
    SERVICE_EFFECT_FLAME: LIFX_EFFECT_FLAME_SCHEMA,
    SERVICE_EFFECT_MORPH: LIFX_EFFECT_MORPH_SCHEMA,
    SERVICE_EFFECT_MOVE: LIFX_EFFECT_MOVE_SCHEMA,
    SERVICE_EFFECT_PULSE: LIFX_EFFECT_PULSE_SCHEMA,
    SERVICE_EFFECT_SKY: LIFX_EFFECT_SKY_SCHEMA,
    SERVICE_EFFECT_STOP: LIFX_EFFECT_STOP_SCHEMA,
    SERVICE_PAINT_THEME: LIFX_PAINT_THEME_SCHEMA,
}


class LIFXManager:
    """Manage LIFX effects and services."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the effects conductor."""
        self.hass = hass
        self.effects_conductor = Conductor()
        self._entity_id_to_coordinator: dict[str, LIFXUpdateCoordinator] = {}

    @property
    def has_children(self) -> bool:
        """Return true if there are still registered light entities."""
        return bool(self._entity_id_to_coordinator)

    @callback
    def async_unload(self) -> None:
        """Unload the manager."""
        for service in SERVICES_SCHEMA:
            self.hass.services.async_remove(DOMAIN, service)

    @callback
    def async_register_entity(
        self, entity_id: str, coordinator: LIFXUpdateCoordinator
    ) -> Callable[[], None]:
        """Register an entity to its coordinator."""
        self._entity_id_to_coordinator[entity_id] = coordinator
        return partial(self.async_unregister_entity, entity_id)

    @callback
    def async_unregister_entity(self, entity_id: str) -> None:
        """Unregister the entity."""
        self._entity_id_to_coordinator.pop(entity_id, None)

    @callback
    def async_setup(self) -> None:
        """Register LIFX effects as hass services."""

        async def service_handler(service: ServiceCall) -> None:
            """Apply a service, i.e. start an effect."""
            referenced = async_extract_referenced_entity_ids(
                self.hass, TargetSelectorData(service.data)
            )
            all_referenced = referenced.referenced | referenced.indirectly_referenced
            if all_referenced:
                await self.start_effect(all_referenced, service.service, **service.data)

        for service, schema in SERVICES_SCHEMA.items():
            self.hass.services.async_register(
                DOMAIN, service, service_handler, schema=schema
            )

    @staticmethod
    def build_theme(
        theme_name: str = "exciting",
        palette: list[list[float | int]] | None = None,
    ) -> Theme:
        """Build a theme from a name or palette."""
        if palette is None:
            return ThemeLibrary.get(theme_name)

        colors = [
            HSBK(
                round(color_values[0]),
                color_values[1] / 100,
                color_values[2] / 100,
                round(color_values[3]),
            )
            for color_values in palette
            if len(color_values) == 4
        ]
        theme = Theme()
        theme.colors = colors
        return theme

    async def _start_effect_flame(
        self,
        lights: list[Light],
        coordinators: list[LIFXUpdateCoordinator],
        **kwargs: Any,
    ) -> None:
        """Start the firmware-based Flame effect."""
        await asyncio.gather(
            *(
                coordinator.async_set_matrix_effect(
                    effect_type=FirmwareEffect.FLAME,
                    speed=kwargs.get(ATTR_SPEED, EFFECT_FLAME_DEFAULT_SPEED),
                    power_on=kwargs.get(ATTR_POWER_ON, True),
                )
                for coordinator in coordinators
            )
        )

    async def _start_paint_theme(
        self,
        lights: list[Light],
        coordinators: list[LIFXUpdateCoordinator],
        **kwargs: Any,
    ) -> None:
        """Paint a theme across one or more LIFX lights."""
        theme_name = kwargs.get(ATTR_THEME, "exciting")
        palette = kwargs.get(ATTR_PALETTE)

        theme = self.build_theme(theme_name, palette)

        await asyncio.gather(
            *(
                coordinator.async_apply_theme(
                    palette=theme.colors,
                    power_on=kwargs.get(ATTR_POWER_ON, True),
                    duration=kwargs.get(
                        ATTR_TRANSITION, PAINT_THEME_DEFAULT_TRANSITION
                    ),
                )
                for coordinator in coordinators
            )
        )

    async def _start_effect_morph(
        self,
        lights: list[Light],
        coordinators: list[LIFXUpdateCoordinator],
        **kwargs: Any,
    ) -> None:
        """Start the firmware-based Morph effect."""
        theme_name = kwargs.get(ATTR_THEME, "exciting")
        palette = kwargs.get(ATTR_PALETTE)

        theme = self.build_theme(theme_name, palette)

        await asyncio.gather(
            *(
                coordinator.async_set_matrix_effect(
                    effect_type=FirmwareEffect.MORPH,
                    speed=kwargs.get(ATTR_SPEED, EFFECT_MORPH_DEFAULT_SPEED),
                    palette=theme.colors,
                    power_on=kwargs.get(ATTR_POWER_ON, True),
                )
                for coordinator in coordinators
            )
        )

    async def _start_effect_move(
        self,
        lights: list[Light],
        coordinators: list[LIFXUpdateCoordinator],
        **kwargs: Any,
    ) -> None:
        """Start the firmware-based Move effect."""
        await asyncio.gather(
            *(
                coordinator.async_set_multizone_effect(
                    effect_type=FirmwareEffect.MOVE,
                    speed=kwargs.get(ATTR_SPEED, EFFECT_MOVE_DEFAULT_SPEED),
                    direction=kwargs.get(ATTR_DIRECTION, EFFECT_MOVE_DEFAULT_DIRECTION),
                    theme_name=kwargs.get(ATTR_THEME),
                    power_on=kwargs.get(ATTR_POWER_ON, False),
                )
                for coordinator in coordinators
            )
        )

    async def _start_effect_pulse(
        self,
        lights: list[Light],
        coordinators: list[LIFXUpdateCoordinator],
        **kwargs: Any,
    ) -> None:
        """Start the software-based Pulse effect."""
        color_attrs: set[str] = {
            ATTR_BRIGHTNESS,
            ATTR_BRIGHTNESS_PCT,
            ATTR_COLOR_NAME,
            ATTR_RGB_COLOR,
            ATTR_XY_COLOR,
            ATTR_HS_COLOR,
            ATTR_COLOR_TEMP_KELVIN,
        }
        color: HSBK | None = (
            generate_hsbk(Colors.WHITE_NEUTRAL, False, **kwargs)
            if color_attrs.intersection(kwargs)
            else None
        )

        effect = EffectPulse(
            power_on=bool(kwargs.get(ATTR_POWER_ON)),
            period=kwargs.get(ATTR_PERIOD),
            cycles=kwargs.get(ATTR_CYCLES),
            mode=kwargs.get(ATTR_MODE, "blink"),
            color=color,
        )

        await self.effects_conductor.start(effect, lights)

    async def _start_effect_colorloop(
        self,
        lights: list[Light],
        coordinators: list[LIFXUpdateCoordinator],
        **kwargs: Any,
    ) -> None:
        """Start the software-based Color Loop effect."""
        brightness: float | None = None
        saturation_max: float | None = None
        saturation_min: float | None = None

        if ATTR_BRIGHTNESS in kwargs:
            brightness = kwargs[ATTR_BRIGHTNESS] / 255
        elif ATTR_BRIGHTNESS_PCT in kwargs:
            brightness = kwargs[ATTR_BRIGHTNESS_PCT] / 100

        if ATTR_SATURATION_MAX in kwargs:
            saturation_max = kwargs[ATTR_SATURATION_MAX] / 100

        if ATTR_SATURATION_MIN in kwargs:
            saturation_min = kwargs[ATTR_SATURATION_MIN] / 100

        period: float | None = kwargs.get(ATTR_PERIOD)
        if period is None:
            period = 60

        change: float | None = kwargs.get(ATTR_CHANGE)
        if change is None:
            change = 20

        spread: float | None = kwargs.get(ATTR_SPREAD)
        if spread is None:
            spread = 30

        if saturation_max is None:
            saturation_max = 1.0

        if saturation_min is None:
            saturation_min = 0.8

        effect = EffectColorloop(
            power_on=bool(kwargs.get(ATTR_POWER_ON)),
            period=period,
            change=change,
            spread=spread,
            transition=kwargs.get(ATTR_TRANSITION),
            brightness=brightness,
            saturation_max=saturation_max,
            saturation_min=saturation_min,
        )

        await self.effects_conductor.start(effect, lights)

    async def _start_effect_sky(
        self,
        lights: list[Light],
        coordinators: list[LIFXUpdateCoordinator],
        **kwargs: Any,
    ) -> None:
        """Start the firmware-based Sky effect."""
        if ATTR_PALETTE in kwargs:
            theme = self.build_theme(palette=kwargs.get(ATTR_PALETTE))
        else:
            theme = None

        speed = kwargs.get(ATTR_SPEED, EFFECT_SKY_DEFAULT_SPEED)
        sky_type = kwargs.get(ATTR_SKY_TYPE, EFFECT_SKY_DEFAULT_SKY_TYPE)

        cloud_saturation_min = kwargs.get(
            ATTR_CLOUD_SATURATION_MIN,
            EFFECT_SKY_DEFAULT_CLOUD_SATURATION_MIN,
        )
        cloud_saturation_max = kwargs.get(
            ATTR_CLOUD_SATURATION_MAX,
            EFFECT_SKY_DEFAULT_CLOUD_SATURATION_MAX,
        )

        await asyncio.gather(
            *(
                coordinator.async_set_matrix_effect(
                    effect_type=FirmwareEffect.SKY,
                    speed=speed,
                    sky_type=sky_type,
                    cloud_saturation_min=cloud_saturation_min,
                    cloud_saturation_max=cloud_saturation_max,
                    palette=theme.colors if theme else None,
                )
                for coordinator in coordinators
            )
        )

    async def _start_effect_stop(
        self,
        lights: list[Light],
        coordinators: list[LIFXUpdateCoordinator],
        **kwargs: Any,
    ) -> None:
        """Stop any running software or firmware effect."""
        await self.effects_conductor.stop(lights)

        for coordinator in coordinators:
            await coordinator.async_set_matrix_effect(
                effect_type=FirmwareEffect.OFF, power_on=False
            )
            await coordinator.async_set_multizone_effect(
                effect_type=FirmwareEffect.OFF, power_on=False
            )

    _effect_dispatch: dict[str, Callable[..., Any]] = {
        SERVICE_EFFECT_COLORLOOP: _start_effect_colorloop,
        SERVICE_EFFECT_FLAME: _start_effect_flame,
        SERVICE_EFFECT_MORPH: _start_effect_morph,
        SERVICE_EFFECT_MOVE: _start_effect_move,
        SERVICE_EFFECT_PULSE: _start_effect_pulse,
        SERVICE_EFFECT_SKY: _start_effect_sky,
        SERVICE_EFFECT_STOP: _start_effect_stop,
        SERVICE_PAINT_THEME: _start_paint_theme,
    }

    async def start_effect(
        self, entity_ids: set[str], service: str, **kwargs: Any
    ) -> None:
        """Start a light effect on entities."""
        coordinators = [
            coordinator
            for entity_id, coordinator in self._entity_id_to_coordinator.items()
            if entity_id in entity_ids
        ]
        lights = [coordinator.light for coordinator in coordinators]

        if start_effect_func := self._effect_dispatch.get(service):
            await start_effect_func(self, lights, coordinators, **kwargs)
