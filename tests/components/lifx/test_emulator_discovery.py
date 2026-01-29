"""Discovery and config flow tests using lifx-emulator."""

from __future__ import annotations

import pytest

from homeassistant.components.lifx.const import CONF_SERIAL, DOMAIN
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er

from . import get_entry_light_entity_id

from tests.common import MockConfigEntry


@pytest.mark.emulator
async def test_config_flow_manual_ip(
    hass: HomeAssistant,
    emulator_server,
    emulator_device_config,
) -> None:
    """Test manual IP entry in config flow with emulator."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: emulator_device_config["host"]},
    )

    assert result2["type"] is FlowResultType.FORM
    assert result2["step_id"] == "discovery_confirm"

    result3 = await hass.config_entries.flow.async_configure(result2["flow_id"], {})
    await hass.async_block_till_done()

    # Should succeed and create entry
    assert result3["type"] is FlowResultType.CREATE_ENTRY
    assert result3["data"][CONF_HOST] == emulator_device_config["host"]
    assert result3["data"][CONF_PORT] == emulator_device_config["port"]
    assert CONF_SERIAL in result3["data"]

    # Verify integration setup
    await hass.async_block_till_done()
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    entity_id = get_entry_light_entity_id(hass, entry)
    state = hass.states.get(entity_id)
    assert state is not None


@pytest.mark.emulator
async def test_duplicate_device_handling(
    hass: HomeAssistant,
    emulator_server,
    emulator_device_config,
) -> None:
    """Test that duplicate config entries are prevented."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=emulator_device_config,
        unique_id=emulator_device_config[CONF_SERIAL],
        version=2,
    )
    config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    # Try to add the same device again via config flow
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: emulator_device_config[CONF_HOST]},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.emulator
async def test_config_entry_unique_id_from_serial(
    hass: HomeAssistant,
    emulator_server,
    emulator_device_config,
) -> None:
    """Test that config entry unique_id is the device serial."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=emulator_device_config,
        unique_id=emulator_device_config[CONF_SERIAL],
        version=2,
    )
    config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.unique_id == emulator_device_config[CONF_SERIAL]

    entity_registry = er.async_get(hass)
    entity_id = get_entry_light_entity_id(hass, config_entry)
    entity_entry = entity_registry.async_get(entity_id)
    assert entity_entry.unique_id == emulator_device_config[CONF_SERIAL]
