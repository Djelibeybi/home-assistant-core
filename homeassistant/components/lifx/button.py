"""Button entity for the LIFX integration."""

from __future__ import annotations

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import IDENTIFY, RESTART
from .coordinator import LIFXConfigEntry, LIFXUpdateCoordinator
from .entity import LIFXEntity

RESTART_BUTTON_DESCRIPTION = ButtonEntityDescription(
    key=RESTART,
    device_class=ButtonDeviceClass.RESTART,
    entity_category=EntityCategory.CONFIG,
)

IDENTIFY_BUTTON_DESCRIPTION = ButtonEntityDescription(
    key=IDENTIFY,
    device_class=ButtonDeviceClass.IDENTIFY,
    entity_category=EntityCategory.CONFIG,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LIFXConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up LIFX button entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        [LIFXRestartButton(coordinator), LIFXIdentifyButton(coordinator)]
    )


class LIFXButton(LIFXEntity, ButtonEntity):
    """Base LIFX button entity."""

    _attr_should_poll = False

    def __init__(self, coordinator: LIFXUpdateCoordinator) -> None:
        """Initialize a LIFX button entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.serial}_{self.entity_description.key}"


class LIFXRestartButton(LIFXButton):
    """LIFX restart button."""

    entity_description = RESTART_BUTTON_DESCRIPTION

    async def async_press(self) -> None:
        """Restart the device."""
        await self.coordinator.light.set_reboot()


class LIFXIdentifyButton(LIFXButton):
    """LIFX identify button."""

    entity_description = IDENTIFY_BUTTON_DESCRIPTION

    async def async_press(self) -> None:
        """Identify the device by flashing it."""
        await self.coordinator.async_identify_light()
