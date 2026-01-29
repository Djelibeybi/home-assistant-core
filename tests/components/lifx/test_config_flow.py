"""Tests for the LIFX integration config flow."""

from collections.abc import Generator
from ipaddress import ip_address
from unittest.mock import AsyncMock, patch

from lifx import LifxConnectionError
import pytest

from homeassistant import config_entries
from homeassistant.components.lifx import DOMAIN
from homeassistant.components.lifx.const import CONF_SERIAL
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from . import (
    DEFAULT_ENTRY_TITLE,
    DHCP_FORMATTED_MAC,
    GROUP,
    IP_ADDRESS,
    LABEL,
    MODULE,
    PORT,
    SERIAL,
    SERIAL_FORMATTED,
    _MockAsyncContextManager,
    _mocked_bulb,
    _mocked_relay,
    _mocked_switch,
    _patch_config_flow_try_connect,
)

from tests.common import MockConfigEntry


@pytest.fixture(autouse=True)
def mock_setup_entry() -> Generator[AsyncMock]:
    """Override async_setup_entry."""
    with patch(
        "homeassistant.components.lifx.async_setup_entry", return_value=True
    ) as mock_setup_entry:
        yield mock_setup_entry


async def test_user_form_show(hass: HomeAssistant) -> None:
    """Test that the user form is shown."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert not result["errors"]


async def test_manual(hass: HomeAssistant) -> None:
    """Test manually setting up a LIFX device."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert not result["errors"]

    # Cannot connect (timeout)
    with _patch_config_flow_try_connect(no_device=True):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: IP_ADDRESS, CONF_PORT: PORT, CONF_SERIAL: SERIAL},
        )
        await hass.async_block_till_done()

    assert result2["type"] is FlowResultType.FORM
    assert result2["step_id"] == "user"
    assert result2["errors"] == {"base": "timeout_connect"}

    # Success
    with (
        _patch_config_flow_try_connect(),
        patch(f"{MODULE}.async_setup", return_value=True),
        patch(f"{MODULE}.async_setup_entry", return_value=True),
    ):
        result3 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: IP_ADDRESS, CONF_PORT: PORT, CONF_SERIAL: SERIAL},
        )
        await hass.async_block_till_done()

    assert result3["type"] is FlowResultType.FORM
    assert result3["step_id"] == "discovery_confirm"

    with (
        patch(f"{MODULE}.async_setup", return_value=True),
        patch(f"{MODULE}.async_setup_entry", return_value=True),
    ):
        result4 = await hass.config_entries.flow.async_configure(result3["flow_id"], {})
        await hass.async_block_till_done()

    assert result4["type"] is FlowResultType.CREATE_ENTRY
    assert result4["title"] == DEFAULT_ENTRY_TITLE
    assert result4["data"] == {
        CONF_HOST: IP_ADDRESS,
        CONF_PORT: PORT,
        CONF_SERIAL: SERIAL,
    }


async def test_manual_without_serial(hass: HomeAssistant) -> None:
    """Test manually setting up a LIFX device without a serial."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert not result["errors"]

    with (
        _patch_config_flow_try_connect(),
        patch(f"{MODULE}.async_setup", return_value=True),
        patch(f"{MODULE}.async_setup_entry", return_value=True),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: IP_ADDRESS},
        )
        await hass.async_block_till_done()

    assert result2["type"] is FlowResultType.FORM
    assert result2["step_id"] == "discovery_confirm"

    with (
        patch(f"{MODULE}.async_setup", return_value=True),
        patch(f"{MODULE}.async_setup_entry", return_value=True),
    ):
        result3 = await hass.config_entries.flow.async_configure(result2["flow_id"], {})
        await hass.async_block_till_done()

    assert result3["type"] is FlowResultType.CREATE_ENTRY
    assert result3["title"] == DEFAULT_ENTRY_TITLE
    assert result3["data"] == {
        CONF_HOST: IP_ADDRESS,
        CONF_PORT: PORT,
        CONF_SERIAL: SERIAL,
    }


async def test_manual_duplicate(hass: HomeAssistant) -> None:
    """Test manually setting up a duplicate LIFX device."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: IP_ADDRESS, CONF_PORT: PORT, CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with _patch_config_flow_try_connect():
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: IP_ADDRESS, CONF_PORT: PORT, CONF_SERIAL: SERIAL},
        )
        await hass.async_block_till_done()

    assert result2["type"] is FlowResultType.ABORT
    assert result2["reason"] == "already_configured"


async def test_manual_no_host(hass: HomeAssistant) -> None:
    """Test manually setting up without a host aborts."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    with _patch_config_flow_try_connect():
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "", CONF_SERIAL: SERIAL},
        )
        await hass.async_block_till_done()

    assert result2["type"] is FlowResultType.ABORT
    assert result2["reason"] == "no_devices_found"


async def test_manual_dns_error(hass: HomeAssistant) -> None:
    """Test manually setting up with a connection error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert not result["errors"]

    bulb = _mocked_bulb()
    bulb.get_color = AsyncMock(side_effect=LifxConnectionError("DNS resolution failed"))
    with _patch_config_flow_try_connect(device=bulb):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "does.not.resolve", CONF_SERIAL: SERIAL},
        )
        await hass.async_block_till_done()

    assert result2["type"] is FlowResultType.FORM
    assert result2["step_id"] == "user"
    assert result2["errors"] == {"base": "cannot_connect"}


async def test_refuse_relays(hass: HomeAssistant) -> None:
    """Test we refuse to set up relays."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert not result["errors"]

    with _patch_config_flow_try_connect(device=_mocked_relay()):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: IP_ADDRESS, CONF_PORT: PORT, CONF_SERIAL: SERIAL},
        )
        await hass.async_block_till_done()

    assert result2["type"] is FlowResultType.ABORT
    assert result2["reason"] == "invalid_device"


async def test_discovered_by_dhcp(hass: HomeAssistant) -> None:
    """Test setup from DHCP discovery."""
    with _patch_config_flow_try_connect():
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_DHCP},
            data=DhcpServiceInfo(
                ip=IP_ADDRESS, macaddress=DHCP_FORMATTED_MAC, hostname=LABEL
            ),
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"
    assert result["errors"] is None

    with (
        patch(f"{MODULE}.async_setup", return_value=True) as mock_async_setup,
        patch(
            f"{MODULE}.async_setup_entry", return_value=True
        ) as mock_async_setup_entry,
    ):
        result2 = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        await hass.async_block_till_done()

    assert result2["type"] is FlowResultType.CREATE_ENTRY
    assert result2["data"] == {
        CONF_HOST: IP_ADDRESS,
        CONF_PORT: PORT,
        CONF_SERIAL: SERIAL,
    }
    assert mock_async_setup.called
    assert mock_async_setup_entry.called


async def test_discovered_by_homekit(hass: HomeAssistant) -> None:
    """Test setup from HomeKit discovery."""
    with _patch_config_flow_try_connect():
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_HOMEKIT},
            data=ZeroconfServiceInfo(
                ip_address=ip_address(IP_ADDRESS),
                ip_addresses=[ip_address(IP_ADDRESS)],
                hostname=LABEL,
                name=LABEL,
                port=None,
                properties={"id": "any"},
                type="mock_type",
            ),
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"
    assert result["errors"] is None

    with (
        patch(f"{MODULE}.async_setup", return_value=True) as mock_async_setup,
        patch(
            f"{MODULE}.async_setup_entry", return_value=True
        ) as mock_async_setup_entry,
    ):
        result2 = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        await hass.async_block_till_done()

    assert result2["type"] is FlowResultType.CREATE_ENTRY
    assert result2["data"] == {
        CONF_HOST: IP_ADDRESS,
        CONF_PORT: PORT,
        CONF_SERIAL: SERIAL,
    }
    assert mock_async_setup.called
    assert mock_async_setup_entry.called


async def test_discovered_by_zeroconf(hass: HomeAssistant) -> None:
    """Test setup from zeroconf discovery."""
    with _patch_config_flow_try_connect():
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=ZeroconfServiceInfo(
                ip_address=ip_address(IP_ADDRESS),
                ip_addresses=[ip_address(IP_ADDRESS)],
                hostname=LABEL,
                name=LABEL,
                port=None,
                properties={"id": SERIAL},
                type="_lifx._tcp.local.",
            ),
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"
    assert result["errors"] is None

    with (
        patch(f"{MODULE}.async_setup", return_value=True) as mock_async_setup,
        patch(
            f"{MODULE}.async_setup_entry", return_value=True
        ) as mock_async_setup_entry,
    ):
        result2 = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        await hass.async_block_till_done()

    assert result2["type"] is FlowResultType.CREATE_ENTRY
    assert result2["data"] == {
        CONF_HOST: IP_ADDRESS,
        CONF_PORT: PORT,
        CONF_SERIAL: SERIAL,
    }
    assert mock_async_setup.called
    assert mock_async_setup_entry.called


async def test_discovered_by_integration_discovery(hass: HomeAssistant) -> None:
    """Test setup from integration discovery auto-creates entry."""
    with _patch_config_flow_try_connect():
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_INTEGRATION_DISCOVERY},
            data={CONF_HOST: IP_ADDRESS, CONF_PORT: PORT, CONF_SERIAL: SERIAL},
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_HOST: IP_ADDRESS,
        CONF_PORT: PORT,
        CONF_SERIAL: SERIAL,
    }


@pytest.mark.parametrize(
    ("source", "data"),
    [
        (
            config_entries.SOURCE_DHCP,
            DhcpServiceInfo(
                ip=IP_ADDRESS, macaddress=DHCP_FORMATTED_MAC, hostname=LABEL
            ),
        ),
        (
            config_entries.SOURCE_HOMEKIT,
            ZeroconfServiceInfo(
                ip_address=ip_address(IP_ADDRESS),
                ip_addresses=[ip_address(IP_ADDRESS)],
                hostname=LABEL,
                name=LABEL,
                port=None,
                properties={"id": "any"},
                type="mock_type",
            ),
        ),
        (
            config_entries.SOURCE_ZEROCONF,
            ZeroconfServiceInfo(
                ip_address=ip_address(IP_ADDRESS),
                ip_addresses=[ip_address(IP_ADDRESS)],
                hostname=LABEL,
                name=LABEL,
                port=None,
                properties={"id": SERIAL},
                type="_lifx._tcp.local.",
            ),
        ),
        (
            config_entries.SOURCE_INTEGRATION_DISCOVERY,
            {CONF_HOST: IP_ADDRESS, CONF_PORT: PORT, CONF_SERIAL: SERIAL},
        ),
    ],
)
async def test_discovered_cannot_connect(
    hass: HomeAssistant, source: str, data: DhcpServiceInfo | ZeroconfServiceInfo | dict
) -> None:
    """Test we abort when discovered but cannot connect."""
    with _patch_config_flow_try_connect(no_device=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": source}, data=data
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


@pytest.mark.parametrize(
    ("source", "data"),
    [
        (
            config_entries.SOURCE_DHCP,
            DhcpServiceInfo(
                ip=IP_ADDRESS, macaddress=DHCP_FORMATTED_MAC, hostname=LABEL
            ),
        ),
        (
            config_entries.SOURCE_HOMEKIT,
            ZeroconfServiceInfo(
                ip_address=ip_address(IP_ADDRESS),
                ip_addresses=[ip_address(IP_ADDRESS)],
                hostname=LABEL,
                name=LABEL,
                port=None,
                properties={"id": "any"},
                type="mock_type",
            ),
        ),
        (
            config_entries.SOURCE_ZEROCONF,
            ZeroconfServiceInfo(
                ip_address=ip_address(IP_ADDRESS),
                ip_addresses=[ip_address(IP_ADDRESS)],
                hostname=LABEL,
                name=LABEL,
                port=None,
                properties={"id": SERIAL},
                type="_lifx._tcp.local.",
            ),
        ),
        (
            config_entries.SOURCE_INTEGRATION_DISCOVERY,
            {CONF_HOST: IP_ADDRESS, CONF_PORT: PORT, CONF_SERIAL: SERIAL},
        ),
    ],
)
async def test_discovered_relay_aborts(
    hass: HomeAssistant, source: str, data: DhcpServiceInfo | ZeroconfServiceInfo | dict
) -> None:
    """Test we abort when a discovered device is a relay."""
    with _patch_config_flow_try_connect(device=_mocked_relay()):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": source}, data=data
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "invalid_device"


@pytest.mark.parametrize(
    ("source", "data"),
    [
        (
            config_entries.SOURCE_DHCP,
            DhcpServiceInfo(
                ip=IP_ADDRESS, macaddress=DHCP_FORMATTED_MAC, hostname=LABEL
            ),
        ),
        (
            config_entries.SOURCE_HOMEKIT,
            ZeroconfServiceInfo(
                ip_address=ip_address(IP_ADDRESS),
                ip_addresses=[ip_address(IP_ADDRESS)],
                hostname=LABEL,
                name=LABEL,
                port=None,
                properties={"id": "any"},
                type="mock_type",
            ),
        ),
        (
            config_entries.SOURCE_ZEROCONF,
            ZeroconfServiceInfo(
                ip_address=ip_address(IP_ADDRESS),
                ip_addresses=[ip_address(IP_ADDRESS)],
                hostname=LABEL,
                name=LABEL,
                port=None,
                properties={"id": SERIAL},
                type="_lifx._tcp.local.",
            ),
        ),
    ],
)
async def test_discovered_updates_ip(
    hass: HomeAssistant, source: str, data: DhcpServiceInfo | ZeroconfServiceInfo
) -> None:
    """Test discovery updates the host of an existing entry."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "127.0.0.2", CONF_SERIAL: SERIAL},
        unique_id=SERIAL,
        version=2,
    )
    config_entry.add_to_hass(hass)

    with _patch_config_flow_try_connect():
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": source},
            data=data,
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert config_entry.data[CONF_HOST] == IP_ADDRESS
    assert config_entry.data[CONF_SERIAL] == SERIAL


async def test_dhcp_already_configured_by_mac(hass: HomeAssistant) -> None:
    """Test DHCP discovery aborts when the MAC matches an existing serial."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "127.0.0.2", CONF_SERIAL: SERIAL},
        unique_id=SERIAL_FORMATTED,
        version=2,
    )
    config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_DHCP},
        data=DhcpServiceInfo(
            ip=IP_ADDRESS, macaddress=DHCP_FORMATTED_MAC, hostname=LABEL
        ),
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_discovered_by_discovery_and_dhcp(hass: HomeAssistant) -> None:
    """Test integration discovery auto-creates entry, and DHCP aborts as already configured."""
    with _patch_config_flow_try_connect():
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_INTEGRATION_DISCOVERY},
            data={CONF_HOST: IP_ADDRESS, CONF_PORT: PORT, CONF_SERIAL: SERIAL},
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_HOST: IP_ADDRESS,
        CONF_PORT: PORT,
        CONF_SERIAL: SERIAL,
    }

    # DHCP discovery for the same device should abort as already configured
    with _patch_config_flow_try_connect():
        result2 = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_DHCP},
            data=DhcpServiceInfo(
                ip=IP_ADDRESS, macaddress=DHCP_FORMATTED_MAC, hostname=LABEL
            ),
        )
        await hass.async_block_till_done()

    assert result2["type"] is FlowResultType.ABORT
    assert result2["reason"] == "already_configured"

    # Different device that cannot connect
    with _patch_config_flow_try_connect(no_device=True):
        result3 = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_DHCP},
            data=DhcpServiceInfo(
                ip="1.2.3.5",
                macaddress="000000000001",
                hostname="mock_hostname",
            ),
        )
        await hass.async_block_till_done()

    assert result3["type"] is FlowResultType.ABORT
    assert result3["reason"] == "cannot_connect"


async def test_discovered_switch_aborts(hass: HomeAssistant) -> None:
    """Test that discovering a LIFX Switch aborts with invalid_device."""
    switch = _mocked_switch()

    async def mock_connect(**kwargs):
        return _MockAsyncContextManager(switch)

    with patch(
        "homeassistant.components.lifx.config_flow.Device.connect",
        side_effect=mock_connect,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_INTEGRATION_DISCOVERY},
            data={CONF_HOST: IP_ADDRESS, CONF_PORT: PORT, CONF_SERIAL: SERIAL},
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "invalid_device"


async def test_discovery_confirm_placeholders(hass: HomeAssistant) -> None:
    """Test that discovery confirm shows label and group placeholders."""
    with _patch_config_flow_try_connect():
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_HOMEKIT},
            data=ZeroconfServiceInfo(
                ip_address=ip_address(IP_ADDRESS),
                ip_addresses=[ip_address(IP_ADDRESS)],
                hostname=LABEL,
                name=LABEL,
                port=None,
                properties={},
                type="mock_type",
            ),
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"
    assert result["description_placeholders"] == {
        "label": LABEL,
        "group": GROUP,
    }
