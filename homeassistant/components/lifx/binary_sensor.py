"""Binary sensor entity for the LIFX integration."""

from __future__ import annotations

from lifx import HevLightState

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import HEV_CYCLE_STATE
from .coordinator import LIFXConfigEntry, LIFXUpdateCoordinator
from .entity import LIFXEntity

HEV_CYCLE_STATE_SENSOR = BinarySensorEntityDescription(
    key=HEV_CYCLE_STATE,
    translation_key="clean_cycle",
    entity_category=EntityCategory.DIAGNOSTIC,
    device_class=BinarySensorDeviceClass.RUNNING,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LIFXConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up LIFX binary sensor platform."""
    coordinator = entry.runtime_data
    if coordinator.data.state.capabilities.has_hev:
        async_add_entities(
            [LIFXHevCycleBinarySensor(coordinator, HEV_CYCLE_STATE_SENSOR)]
        )


class LIFXHevCycleBinarySensor(LIFXEntity, BinarySensorEntity):
    """LIFX HEV cycle state binary sensor."""

    def __init__(
        self,
        coordinator: LIFXUpdateCoordinator,
        description: BinarySensorEntityDescription,
    ) -> None:
        """Initialize the HEV cycle binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.serial}_{description.key}"
        self._async_update_attrs()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._async_update_attrs()
        super()._handle_coordinator_update()

    @callback
    def _async_update_attrs(self) -> None:
        """Handle coordinator updates."""
        if isinstance(self.coordinator.data.state, HevLightState):
            self._attr_is_on = self.coordinator.async_get_hev_cycle_state()
        else:
            self._attr_is_on = None
