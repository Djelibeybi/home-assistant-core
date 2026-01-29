"""Tests for the lifx component."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

from lifx import HSBK, LifxConnectionError, LifxTimeoutError
import pytest

from homeassistant.components import lifx
from homeassistant.components.lifx import DOMAIN
from homeassistant.components.lifx.const import (
    CONF_SERIAL,
    DATA_LIFX_MANAGER,
    LIFX_DEFAULT_PORT,
)
from homeassistant.components.lifx.discovery import async_discover_devices
from homeassistant.components.lifx.util import (
    infrared_brightness_option_to_value,
    infrared_brightness_value_to_option,
    mac_matches_serial,
    normalize_serial,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
    EVENT_HOMEASSISTANT_STARTED,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

from . import (
    DEFAULT_ENTRY_TITLE,
    IP_ADDRESS,
    SERIAL,
    SERIAL_FORMATTED,
    SERIAL_RAW,
    _mocked_bulb,
    _mocked_light_strip,
    _patch_config_flow_try_connect,
    _patch_device,
    _patch_discovery,
)

from tests.common import MockConfigEntry, async_fire_time_changed


async def test_configuring_lifx_causes_discovery(hass: HomeAssistant) -> None:
    """Test that configuring lifx triggers discovery."""
    discover_call_count = 0

    async def mock_discover(**kwargs):
        """Mock discover that counts invocations."""
        nonlocal discover_call_count
        discover_call_count += 1
        bulb = _mocked_bulb()
        yield bulb

    with (
        _patch_config_flow_try_connect(),
        patch(
            "homeassistant.components.lifx.discovery.discover",
            side_effect=mock_discover,
        ),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()
        assert discover_call_count == 0

        hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
        await hass.async_block_till_done()
        assert discover_call_count == 1

        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=5))
        await hass.async_block_till_done(wait_background_tasks=True)
        assert discover_call_count == 2

        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=15))
        await hass.async_block_till_done(wait_background_tasks=True)
        assert discover_call_count == 3

        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=30))
        await hass.async_block_till_done(wait_background_tasks=True)
        assert discover_call_count == 4


async def test_discovery_includes_ip_changes(hass: HomeAssistant) -> None:
    """Test discovery includes configured serials when IP changes."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4", CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)

    bulb_same = _mocked_bulb()
    bulb_same.serial = SERIAL
    bulb_same.ip = "1.2.3.4"
    bulb_same.port = LIFX_DEFAULT_PORT

    bulb_changed = _mocked_bulb()
    bulb_changed.serial = SERIAL
    bulb_changed.ip = "1.2.3.5"
    bulb_changed.port = LIFX_DEFAULT_PORT

    async def mock_discover(**kwargs):
        yield bulb_same
        yield bulb_changed

    with patch(
        "homeassistant.components.lifx.discovery.discover", side_effect=mock_discover
    ):
        discovered = await async_discover_devices(hass)

    assert discovered == [
        {
            CONF_HOST: "1.2.3.5",
            CONF_PORT: LIFX_DEFAULT_PORT,
            CONF_SERIAL: SERIAL,
        }
    ]


async def test_config_entry_reload(hass: HomeAssistant) -> None:
    """Test that a config entry can be reloaded."""
    already_migrated_config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    already_migrated_config_entry.add_to_hass(hass)
    with _patch_discovery(), _patch_config_flow_try_connect(), _patch_device():
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()
        assert already_migrated_config_entry.state is ConfigEntryState.LOADED
        await hass.config_entries.async_unload(already_migrated_config_entry.entry_id)
        await hass.async_block_till_done()
        assert already_migrated_config_entry.state is ConfigEntryState.NOT_LOADED
        await hass.config_entries.async_setup(already_migrated_config_entry.entry_id)
        await hass.async_block_till_done()
        assert already_migrated_config_entry.state is ConfigEntryState.LOADED


async def test_config_entry_retry(hass: HomeAssistant) -> None:
    """Test that a config entry can be retried."""
    already_migrated_config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    already_migrated_config_entry.add_to_hass(hass)
    with (
        _patch_discovery(no_device=True),
        _patch_config_flow_try_connect(no_device=True),
        _patch_device(no_device=True),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()
        assert already_migrated_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_connection_timeout_during_first_refresh(
    hass: HomeAssistant,
) -> None:
    """Test we handle connection timeout during initial connect."""
    already_migrated_config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    already_migrated_config_entry.add_to_hass(hass)
    with (
        _patch_discovery(no_device=True),
        _patch_config_flow_try_connect(no_device=True),
        _patch_device(no_device=True),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()
        assert already_migrated_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_connection_error_at_startup(hass: HomeAssistant) -> None:
    """Test we handle connection errors at startup."""
    already_migrated_config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    already_migrated_config_entry.add_to_hass(hass)
    with (
        _patch_discovery(no_device=True),
        _patch_config_flow_try_connect(no_device=True),
        _patch_device(no_device=True),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()
        assert already_migrated_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_connection_error_at_startup_direct_exception(
    hass: HomeAssistant,
) -> None:
    """Test we handle direct connection errors at startup."""
    already_migrated_config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    already_migrated_config_entry.add_to_hass(hass)
    with (
        _patch_discovery(no_device=True),
        _patch_config_flow_try_connect(no_device=True),
        patch(
            "homeassistant.components.lifx.Light.connect",
            new=AsyncMock(side_effect=LifxTimeoutError("timeout")),
        ),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()
        assert already_migrated_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_config_entry_wrong_serial(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Test config entry enters setup retry when serial mismatches."""
    mismatched_serial = f"{SERIAL[:-1]}0"
    already_migrated_config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: mismatched_serial},
        unique_id=mismatched_serial,
        version=2,
    )
    already_migrated_config_entry.add_to_hass(hass)
    with _patch_discovery(), _patch_config_flow_try_connect(), _patch_device():
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()
        assert already_migrated_config_entry.state is ConfigEntryState.SETUP_RETRY

    assert (
        f"Unexpected device found at {IP_ADDRESS};"
        f" expected {mismatched_serial}, found {SERIAL}" in caplog.text
    )


async def test_config_entry_migration(hass: HomeAssistant) -> None:
    """Test config entry migration from v1 to v2."""
    v1_config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: IP_ADDRESS},
        unique_id=SERIAL_FORMATTED,
        version=1,
    )
    v1_config_entry.add_to_hass(hass)
    with _patch_discovery(), _patch_config_flow_try_connect(), _patch_device():
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()
        assert v1_config_entry.state is ConfigEntryState.LOADED

    assert v1_config_entry.version == 2
    assert v1_config_entry.data[CONF_SERIAL] == SERIAL_RAW
    assert v1_config_entry.unique_id == SERIAL_RAW
    assert v1_config_entry.data[CONF_HOST] == IP_ADDRESS


async def test_legacy_entry_removed(hass: HomeAssistant) -> None:
    """Test legacy config entries are removed."""
    legacy_entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        unique_id=DOMAIN,
        version=1,
    )
    legacy_entry.add_to_hass(hass)

    with patch.object(
        hass.config_entries,
        "async_remove",
        new=AsyncMock(),
    ) as remove_entry:
        assert not await lifx.async_setup_entry(hass, legacy_entry)

    remove_entry.assert_called_once_with(legacy_entry.entry_id)


async def test_legacy_entry_migration_noop(hass: HomeAssistant) -> None:
    """Test legacy config entries skip migration."""
    legacy_entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        unique_id=None,
        version=1,
    )
    legacy_entry.add_to_hass(hass)

    assert await lifx.async_migrate_entry(hass, legacy_entry)
    assert legacy_entry.version == 1
    assert legacy_entry.unique_id is None


async def test_legacy_entry_unload_noop(hass: HomeAssistant) -> None:
    """Test legacy config entries unload without work."""
    legacy_entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        unique_id=None,
        version=1,
    )

    assert await lifx.async_unload_entry(hass, legacy_entry)


async def test_discovery_interval_reset(hass: HomeAssistant) -> None:
    """Test resetting discovery interval cancels the prior handle."""
    discovery_manager = lifx.LIFXDiscoveryManager(hass)
    cancel_called = False

    def _cancel() -> None:
        nonlocal cancel_called
        cancel_called = True

    discovery_manager._cancel_discovery = _cancel

    with patch(
        "homeassistant.components.lifx.async_track_time_interval",
        return_value=lambda: None,
    ):
        discovery_manager.async_setup_discovery_interval()

    assert cancel_called


async def test_first_refresh_fails_closes_coordinator(
    hass: HomeAssistant,
) -> None:
    """Test coordinator is closed when first refresh raises ConfigEntryNotReady."""
    already_migrated_config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    already_migrated_config_entry.add_to_hass(hass)
    bulb = _mocked_bulb()
    # Make the first coordinator refresh fail
    bulb.refresh_state = AsyncMock(
        side_effect=Exception("Connection failed during refresh")
    )
    with (
        _patch_discovery(),
        _patch_config_flow_try_connect(),
        _patch_device(device=bulb),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()
        assert already_migrated_config_entry.state is ConfigEntryState.SETUP_RETRY
        # Verify coordinator.async_close() was called (light.close())
        bulb.close.assert_called()


async def test_coordinator_close_handles_error(hass: HomeAssistant) -> None:
    """Test coordinator close swallows connection close errors."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    bulb = _mocked_bulb()
    with (
        _patch_discovery(device=bulb),
        _patch_config_flow_try_connect(device=bulb),
        _patch_device(device=bulb),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

    coordinator = config_entry.runtime_data
    bulb.close = AsyncMock(side_effect=LifxConnectionError("close failed"))

    await coordinator.async_close()
    bulb.close.assert_called_once()


async def test_non_lifx_exception_in_exception_group(
    hass: HomeAssistant,
) -> None:
    """Test that non-LifxError exceptions in ExceptionGroup are re-raised."""
    already_migrated_config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    already_migrated_config_entry.add_to_hass(hass)

    # Create an ExceptionGroup with a non-LifxError exception
    non_lifx_error = ValueError("Not a LIFX error")

    with (
        _patch_discovery(),
        _patch_config_flow_try_connect(),
        patch(
            "homeassistant.components.lifx.Light.connect",
            side_effect=ExceptionGroup("Multiple errors", [non_lifx_error]),
        ),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()
        assert already_migrated_config_entry.state is ConfigEntryState.SETUP_ERROR


async def test_infrared_brightness_on_non_infrared_light(
    hass: HomeAssistant,
) -> None:
    """Test current_infrared_brightness returns None for non-infrared lights."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    bulb = _mocked_bulb()
    with (
        _patch_discovery(device=bulb),
        _patch_config_flow_try_connect(device=bulb),
        _patch_device(device=bulb),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

    coordinator = config_entry.runtime_data
    assert coordinator.current_infrared_brightness is None


async def test_hev_cycle_state_on_non_hev_light(
    hass: HomeAssistant,
) -> None:
    """Test async_get_hev_cycle_state returns None for non-HEV lights."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    bulb = _mocked_bulb()
    with (
        _patch_discovery(device=bulb),
        _patch_config_flow_try_connect(device=bulb),
        _patch_device(device=bulb),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

    coordinator = config_entry.runtime_data
    assert coordinator.async_get_hev_cycle_state() is None


async def test_apply_theme_no_args_raises(
    hass: HomeAssistant,
) -> None:
    """Test async_apply_theme raises error with no theme_name and no palette."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    bulb = _mocked_bulb()
    with (
        _patch_discovery(device=bulb),
        _patch_config_flow_try_connect(device=bulb),
        _patch_device(device=bulb),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

    coordinator = config_entry.runtime_data
    with pytest.raises(HomeAssistantError):
        await coordinator.async_apply_theme()


async def test_connection_error_during_update(
    hass: HomeAssistant,
) -> None:
    """Test that a connection error during update marks entity unavailable."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    bulb = _mocked_bulb()
    bulb.state.power = 65535

    call_count = 0

    async def refresh_state_with_error():
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            raise LifxConnectionError("Connection lost")

    bulb.refresh_state = AsyncMock(side_effect=refresh_state_with_error)

    with (
        _patch_discovery(device=bulb),
        _patch_config_flow_try_connect(device=bulb),
        _patch_device(device=bulb),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

        entity_id = "light.my_bulb"
        state = hass.states.get(entity_id)
        assert state is not None

        bulb.close.reset_mock()

        # Trigger updates until the retry budget is exceeded
        now = dt_util.utcnow()
        for offset in range(1, 5):
            async_fire_time_changed(hass, now + timedelta(seconds=30 * offset))
            await hass.async_block_till_done(wait_background_tasks=True)

        state = hass.states.get(entity_id)
        assert state.state == "unavailable"
        assert bulb.close.call_count >= 4


async def test_manager_has_children(
    hass: HomeAssistant,
) -> None:
    """Test manager.has_children returns True after entity registration."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    bulb = _mocked_bulb()
    with (
        _patch_discovery(device=bulb),
        _patch_config_flow_try_connect(device=bulb),
        _patch_device(device=bulb),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

    manager = hass.data[DATA_LIFX_MANAGER]
    assert manager.has_children is True


def test_mac_matches_serial() -> None:
    """Test mac_matches_serial utility function."""
    # Exact match
    assert mac_matches_serial("aa:bb:cc:dd:ee:ff", "aa:bb:cc:dd:ee:ff") is True

    # Raw hex serial match
    assert mac_matches_serial("aa:bb:cc:dd:ee:ff", "aabbccddeeff") is True

    # Off-by-one in last byte (serial + 1 matches mac)
    assert mac_matches_serial("aa:bb:cc:dd:ee:ff", "aabbccddeefe") is True

    # No match
    assert mac_matches_serial("aa:bb:cc:dd:ee:ff", "aabbccddeead") is False

    # Invalid serial length (not 6 octets, not 12 hex chars)
    assert mac_matches_serial("aa:bb:cc:dd:ee:ff", "aabbcc") is False

    # Invalid hex serial should be handled
    assert mac_matches_serial("aa:bb:cc:dd:ee:ff", "zz:zz:zz:zz:zz:zz") is False


def test_normalize_serial_empty() -> None:
    """Test normalize_serial returns empty string for empty input."""
    assert normalize_serial("") == ""


def test_infrared_brightness_value_to_option() -> None:
    """Test infrared_brightness_value_to_option utility function."""
    assert infrared_brightness_value_to_option(0.0) == "Disabled"
    assert infrared_brightness_value_to_option(0.25) == "25%"
    assert infrared_brightness_value_to_option(0.50) == "50%"
    assert infrared_brightness_value_to_option(1.0) == "100%"
    assert infrared_brightness_value_to_option(0.75) is None


def test_infrared_brightness_option_to_value() -> None:
    """Test infrared_brightness_option_to_value utility function."""
    assert infrared_brightness_option_to_value("Disabled") == 0.0
    assert infrared_brightness_option_to_value("25%") == 0.25
    assert infrared_brightness_option_to_value("50%") == 0.50
    assert infrared_brightness_option_to_value("100%") == 1.0
    assert infrared_brightness_option_to_value("invalid") is None


async def test_coordinator_set_color_zones(
    hass: HomeAssistant,
) -> None:
    """Test coordinator.async_set_color_zones on a multizone light."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    bulb = _mocked_light_strip()
    bulb.state.power = 65535
    with (
        _patch_discovery(device=bulb),
        _patch_config_flow_try_connect(device=bulb),
        _patch_device(device=bulb),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

    coordinator = config_entry.runtime_data
    color = HSBK(hue=120, saturation=1.0, brightness=1.0, kelvin=3500)
    await coordinator.async_set_color_zones(0, 2, color)
    bulb.set_color_zones.assert_called_once()


async def test_coordinator_set_extended_color_zones(
    hass: HomeAssistant,
) -> None:
    """Test coordinator.async_set_extended_color_zones on a multizone light."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    bulb = _mocked_light_strip()
    bulb.state.power = 65535
    with (
        _patch_discovery(device=bulb),
        _patch_config_flow_try_connect(device=bulb),
        _patch_device(device=bulb),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

    coordinator = config_entry.runtime_data
    colors = [
        HSBK(hue=120, saturation=1.0, brightness=1.0, kelvin=3500),
        HSBK(hue=240, saturation=1.0, brightness=1.0, kelvin=3500),
    ]
    await coordinator.async_set_extended_color_zones(colors)
    bulb.set_extended_color_zones.assert_called_once()


async def test_coordinator_async_get_entity_id(
    hass: HomeAssistant,
) -> None:
    """Test coordinator.async_get_entity_id returns the entity id."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    bulb = _mocked_bulb()
    with (
        _patch_discovery(device=bulb),
        _patch_config_flow_try_connect(device=bulb),
        _patch_device(device=bulb),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

    coordinator = config_entry.runtime_data
    # The light entity has no key suffix, so use the sensor entity which has "rssi"
    entity_id = coordinator.async_get_entity_id(Platform.SENSOR, "rssi")
    assert entity_id == "sensor.my_bulb_rssi"


async def test_timeout_then_recovery_resets_attempts(
    hass: HomeAssistant,
) -> None:
    """Test that _update_attempts resets to 0 after a successful update."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_ENTRY_TITLE,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)
    bulb = _mocked_bulb()
    bulb.state.power = 65535

    call_count = 0

    async def refresh_state_timeout_then_success():
        nonlocal call_count
        call_count += 1
        # First call succeeds (setup), second fails with timeout, third succeeds
        if call_count == 2:
            raise LifxTimeoutError("timeout")

    bulb.refresh_state = AsyncMock(side_effect=refresh_state_timeout_then_success)

    with (
        _patch_discovery(device=bulb),
        _patch_config_flow_try_connect(device=bulb),
        _patch_device(device=bulb),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

        entity_id = "light.my_bulb"
        state = hass.states.get(entity_id)
        assert state is not None

        coordinator = config_entry.runtime_data

        # Trigger update that will timeout (increments _update_attempts)
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=30))
        await hass.async_block_till_done(wait_background_tasks=True)
        assert coordinator._update_attempts == 1

        # Trigger another update that succeeds (resets _update_attempts to 0)
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=60))
        await hass.async_block_till_done(wait_background_tasks=True)
        assert coordinator._update_attempts == 0


async def test_setup_with_custom_port(hass: HomeAssistant) -> None:
    """Test setup uses custom port when configured."""
    custom_port = 56701
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL, CONF_PORT: custom_port},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)

    with (
        _patch_discovery(),
        _patch_config_flow_try_connect(),
        _patch_device(),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.LOADED
    assert config_entry.data[CONF_PORT] == custom_port


async def test_setup_with_default_port(hass: HomeAssistant) -> None:
    """Test setup uses default port when not configured."""

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: IP_ADDRESS, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)

    with (
        _patch_discovery(),
        _patch_config_flow_try_connect(),
        _patch_device(),
    ):
        await async_setup_component(hass, lifx.DOMAIN, {lifx.DOMAIN: {}})
        await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.LOADED
    assert config_entry.data.get(CONF_PORT, LIFX_DEFAULT_PORT) == LIFX_DEFAULT_PORT
