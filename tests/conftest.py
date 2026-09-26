"""A living room with an LG TV, a Denon receiver and a Chromecast, running in real Home Assistant.

Source names follow what a real LG and Denon report, with generic room names.
"""

import pytest
from homeassistant.components.media_player import MediaPlayerEntity, MediaPlayerState
from homeassistant.components.media_player import MediaPlayerEntityFeature as F
from homeassistant.components.remote import RemoteEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    setup_test_component_platform,
)

from custom_components.home_theater import theater as theater_module

TV_SOURCES = ["Apps", "Denon Hjemmekinoanlegg", "HDMI 3", "Live TV", "NRK TV", "Netflix", "YouTube"]
RECEIVER_SOURCES = ["Blu-ray", "Game", "Media Player", "TV Audio"]
# webOS without a Wake-on-LAN trigger reports no TURN_ON.
TV_FEATURES = (
    F.TURN_OFF | F.SELECT_SOURCE | F.VOLUME_STEP | F.VOLUME_MUTE | F.PLAY | F.PAUSE | F.STOP
)
RECEIVER_FEATURES = (
    F.TURN_ON | F.TURN_OFF | F.SELECT_SOURCE | F.VOLUME_STEP | F.VOLUME_SET | F.VOLUME_MUTE
)
OPTIONS = {
    "tv": "media_player.lg",
    "receiver": "media_player.denon",
    "tv_input": "Denon Hjemmekinoanlegg",
    "sources": [
        {
            "device": "receiver",
            "source": "Media Player",
            "name": "Chromecast",
            "player": "media_player.cast",
            "remote": "remote.cast",
        },
        {"device": "receiver", "source": "Game", "name": "PlayStation"},
        {"device": "tv", "source": "NRK TV"},
        {"device": "tv", "source": "Netflix"},
    ],
}


class FakePlayer(MediaPlayerEntity):
    """A media player that behaves like the device: slow to wake, deaf while off."""

    _attr_should_poll = False

    def __init__(self, entity_id, features, sources=None, on=True, wakes=True, **attributes):
        self.entity_id = entity_id
        self._attr_name = entity_id
        self._attr_supported_features = features
        self._attr_state = MediaPlayerState.ON if on else MediaPlayerState.OFF
        self._attr_source_list = sources
        self.wakes = wakes
        self.calls = []
        for key, value in attributes.items():
            setattr(self, f"_attr_{key}", value)

    def set(self, **attributes):
        for key, value in attributes.items():
            setattr(self, f"_attr_{key}", value)
        self.async_write_ha_state()

    async def async_turn_on(self):
        self.calls.append(("turn_on",))
        if self.wakes:
            self.set(state=MediaPlayerState.ON)

    async def async_turn_off(self):
        self.calls.append(("turn_off",))
        self.set(state=MediaPlayerState.OFF)

    async def async_select_source(self, source):
        self.calls.append(("select_source", source))
        if self._attr_state == MediaPlayerState.OFF:
            raise HomeAssistantError("device is off")
        self.set(source=source)

    async def async_volume_up(self):
        self.calls.append(("volume_up",))
        self.set(volume_level=round((self._attr_volume_level or 0) + 0.01, 2))

    async def async_mute_volume(self, mute):
        self.calls.append(("mute", mute))
        self.set(is_volume_muted=mute)

    async def async_media_pause(self):
        self.calls.append(("pause",))
        self.set(state=MediaPlayerState.PAUSED)


class FakeRemote(RemoteEntity):
    _attr_should_poll = False
    _attr_is_on = True

    def __init__(self, entity_id):
        self.entity_id = entity_id
        self._attr_name = entity_id
        self.commands = []

    async def async_send_command(self, command, **kwargs):
        self.commands.extend(command)


class Room:
    def __init__(self, hass):
        self.hass = hass
        self.tv = FakePlayer(
            "media_player.lg",
            TV_FEATURES,
            list(TV_SOURCES),
            source="Denon Hjemmekinoanlegg",
            extra_state_attributes={"sound_output": "external_arc"},
        )
        self.receiver = FakePlayer(
            "media_player.denon",
            RECEIVER_FEATURES,
            list(RECEIVER_SOURCES),
            source="Media Player",
            volume_level=0.45,
            is_volume_muted=False,
        )
        self.cast = FakePlayer(
            "media_player.cast",
            F.PLAY | F.PAUSE | F.TURN_OFF,
            state=MediaPlayerState.PLAYING,
            media_title="Episode 4",
            media_series_title="A Series",
            app_name="YouTube",
            media_image_url="http://cast.local/art.png",
        )
        self.cast._attr_state = MediaPlayerState.PLAYING
        self.remote = FakeRemote("remote.cast")
        self.buttons = []
        self.outputs = []

    async def setup(self):
        setup_test_component_platform(
            self.hass, "media_player", [self.tv, self.receiver, self.cast]
        )
        setup_test_component_platform(self.hass, "remote", [self.remote])
        assert await async_setup_component(
            self.hass, "media_player", {"media_player": {"platform": "test"}}
        )
        assert await async_setup_component(self.hass, "remote", {"remote": {"platform": "test"}})
        await self.hass.async_block_till_done()

        async def button(call):
            self.buttons.append((call.data["entity_id"], call.data["button"]))

        async def sound_output(call):
            self.outputs.append(call.data["sound_output"])
            self.tv.set(extra_state_attributes={"sound_output": call.data["sound_output"]})

        self.hass.services.async_register("webostv", "button", button)
        self.hass.services.async_register("webostv", "select_sound_output", sound_output)


@pytest.fixture(autouse=True)
def enable(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(theater_module, "WAKE_TIMEOUT", 0.5)
    monkeypatch.setattr(theater_module, "SWITCH_TIMEOUT", 0.2)


@pytest.fixture
async def room(hass):
    room = Room(hass)
    await room.setup()
    return room


@pytest.fixture
def entry(hass):
    entry = MockConfigEntry(domain="home_theater", title="Stue", data={}, options=dict(OPTIONS))
    entry.add_to_hass(hass)
    return entry


async def setup(hass, entry):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def call(hass, domain, service, entity_id, **data):
    await hass.services.async_call(domain, service, {"entity_id": entity_id, **data}, blocking=True)
    await hass.async_block_till_done()
