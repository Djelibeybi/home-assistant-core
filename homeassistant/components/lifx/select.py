"""Select entity for the LIFX integration."""

from __future__ import annotations

from lifx import ThemeLibrary

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import ATTR_THEME, INFRARED_BRIGHTNESS, INFRARED_BRIGHTNESS_VALUES_MAP
from .coordinator import LIFXConfigEntry, LIFXUpdateCoordinator
from .entity import LIFXEntity

THEME_NAMES = [theme_name.lower() for theme_name in ThemeLibrary.list()]

THEME_ENTITY = SelectEntityDescription(
    key=ATTR_THEME,
    translation_key="theme",
    entity_category=EntityCategory.CONFIG,
    options=THEME_NAMES,
)

INFRARED_BRIGHTNESS_ENTITY = SelectEntityDescription(
    key=INFRARED_BRIGHTNESS,
    translation_key="infrared_brightness",
    entity_category=EntityCategory.CONFIG,
    options=list(INFRARED_BRIGHTNESS_VALUES_MAP.values()),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LIFXConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up LIFX select entities."""
    coordinator = entry.runtime_data
    entities: list[SelectEntity] = []
    capabilities = coordinator.data.state.capabilities

    if capabilities.has_multizone or capabilities.has_matrix:
        entities.append(LIFXThemeSelectEntity(coordinator, THEME_ENTITY))

    if capabilities.has_infrared:
        entities.append(
            LIFXInfraredBrightnessSelectEntity(coordinator, INFRARED_BRIGHTNESS_ENTITY)
        )

    if entities:
        async_add_entities(entities)


class LIFXThemeSelectEntity(LIFXEntity, SelectEntity):
    """Theme selection entity for LIFX multizone devices."""

    def __init__(
        self,
        coordinator: LIFXUpdateCoordinator,
        description: SelectEntityDescription,
    ) -> None:
        """Initialize the theme selection entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.serial}_{description.key}"
        self._attr_current_option = None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._async_update_attrs()
        super()._handle_coordinator_update()

    @callback
    def _async_update_attrs(self) -> None:
        """Update attrs from coordinator data."""
        self._attr_current_option = self.coordinator.last_used_theme

    async def async_select_option(self, option: str) -> None:
        """Paint the selected theme onto the device."""
        await self.coordinator.async_apply_theme(option.lower())


class LIFXInfraredBrightnessSelectEntity(LIFXEntity, SelectEntity):
    """Infrared brightness selection entity for LIFX nightvision devices."""

    def __init__(
        self,
        coordinator: LIFXUpdateCoordinator,
        description: SelectEntityDescription,
    ) -> None:
        """Initialize the infrared brightness selection entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.serial}_{description.key}"
        self._attr_current_option = coordinator.current_infrared_brightness

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._async_update_attrs()
        super()._handle_coordinator_update()

    @callback
    def _async_update_attrs(self) -> None:
        """Update attrs from coordinator data."""
        self._attr_current_option = self.coordinator.current_infrared_brightness

    async def async_select_option(self, option: str) -> None:
        """Set the infrared brightness."""
        await self.coordinator.async_set_infrared_brightness(option)
        await self.coordinator.async_request_refresh()
