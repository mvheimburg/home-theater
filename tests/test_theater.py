"""The room follows its devices and sequences them, through real Home Assistant services."""

from unittest.mock import patch

import pytest
from homeassistant.components.media_player import MediaPlayerState
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .conftest import call, setup

THEATER = "media_player.stue_theater"
SOURCE = "sensor.stue_source"
AUDIO = "binary_sensor.stue_audio"
REMOTE = "remote.stue_remote"


async def test_entity_ids_follow_the_room_name(hass, room, entry):
    await setup(hass, entry)
    for entity_id in (THEATER, SOURCE, AUDIO, REMOTE):
        assert hass.states.get(entity_id), entity_id


async def test_entity_ids_are_english_in_any_language(hass, room, entry):
    hass.config.language = "nb"
    await setup(hass, entry)
    assert hass.states.get(THEATER).attributes["friendly_name"] == "Stue Hjemmekino"
    assert hass.states.get(SOURCE)


async def test_a_registered_entity_keeps_its_id(hass, room, entry):
    er.async_get(hass).async_get_or_create(
        "media_player",
        "home_theater",
        f"{entry.entry_id}_theater",
        suggested_object_id="living_room_tv",
        config_entry=entry,
    )
    await setup(hass, entry)
    assert hass.states.get("media_player.living_room_tv")
    assert not hass.states.get(THEATER)


async def test_shows_the_linked_player_on_the_receiver_input(hass, room, entry):
    await setup(hass, entry)
    state = hass.states.get(THEATER)
    assert state.state == MediaPlayerState.PLAYING
    assert state.attributes["source"] == "Chromecast"
    assert state.attributes["source_list"] == ["Chromecast", "PlayStation", "NRK TV", "Netflix"]
    assert state.attributes["media_title"] == "Episode 4"
    assert state.attributes["media_series_title"] == "A Series"
    assert state.attributes["app_name"] == "YouTube"
    assert state.attributes["volume_level"] == 0.45
    assert state.attributes["entity_picture"].startswith(
        "/api/media_player_proxy/media_player.cast"
    )
    assert state.attributes["linked_player"] == "media_player.cast"
    assert hass.states.get(SOURCE).state == "Chromecast"
    assert hass.states.get(SOURCE).attributes["device"] == "receiver"


async def test_a_tv_app_on_tv_audio_is_the_source(hass, room, entry):
    await setup(hass, entry)
    room.receiver.set(source="TV Audio")
    room.tv.set(source="Netflix")
    await hass.async_block_till_done()
    state = hass.states.get(THEATER)
    assert state.attributes["source"] == "Netflix"
    assert state.attributes["app_name"] == "Netflix"
    assert state.state == MediaPlayerState.ON
    assert hass.states.get(SOURCE).state == "Netflix"


async def test_sources_stay_known_while_everything_is_off(hass, room, entry):
    await setup(hass, entry)
    room.tv.set(state=MediaPlayerState.OFF, source_list=None)
    room.receiver.set(state=MediaPlayerState.OFF, source_list=None)
    await hass.async_block_till_done()
    assert hass.states.get(THEATER).state == MediaPlayerState.OFF
    source = hass.states.get(SOURCE)
    assert source.state == "off"
    assert source.attributes["source_list"] == ["Chromecast", "PlayStation", "NRK TV", "Netflix"]
    room_state = hass.states.get(THEATER)
    assert room_state.attributes["sources"] == ["Chromecast", "PlayStation", "NRK TV", "Netflix"]
    assert "YouTube" in room_state.attributes["all_sources"]
    assert room_state.attributes["tv"] == "media_player.lg"
    assert room_state.attributes["receiver"] == "media_player.denon"
    assert "YouTube" in source.attributes["all_sources"]
    assert "Denon Hjemmekinoanlegg" not in source.attributes["all_sources"]
    assert "TV Audio" not in source.attributes["all_sources"]


async def test_default_sources_are_receiver_inputs_and_live_tv(hass, room, entry):
    hass.config_entries.async_update_entry(entry, options={**entry.options, "sources": []})
    await setup(hass, entry)
    assert hass.states.get(THEATER).attributes["source_list"] == [
        "Blu-ray",
        "Game",
        "Media Player",
        "Live TV",
    ]


async def test_a_tv_app_switches_the_receiver_to_tv_audio(hass, room, entry):
    await setup(hass, entry)
    await call(hass, "media_player", "select_source", THEATER, source="Netflix")
    assert room.receiver.calls == [("select_source", "TV Audio")]
    assert room.tv.calls == [("select_source", "Netflix")]
    assert hass.states.get(SOURCE).state == "Netflix"


async def test_a_receiver_source_puts_the_tv_on_the_receiver_input(hass, room, entry):
    await setup(hass, entry)
    room.tv.set(source="YouTube")
    await call(hass, "media_player", "select_source", THEATER, source="PlayStation")
    assert room.receiver.calls == [("select_source", "Game")]
    assert room.tv.calls == [("select_source", "Denon Hjemmekinoanlegg")]


async def test_the_room_wakes_before_a_tv_app_with_wake_on_lan(hass, room, entry):
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, "wol_mac": "AA:BB:CC:DD:EE:FF"}
    )
    room.tv.set(state=MediaPlayerState.OFF)
    room.receiver.set(state=MediaPlayerState.OFF)
    await setup(hass, entry)
    packets = []

    def woken(packet):
        packets.append(packet)
        hass.loop.call_soon_threadsafe(lambda: room.tv.set(state=MediaPlayerState.ON))

    with patch("custom_components.home_theater.wol._send", woken):
        await call(hass, "media_player", "select_source", THEATER, source="NRK TV")
    assert packets == [bytes.fromhex("FF" * 6 + "AABBCCDDEEFF" * 16)]
    assert room.receiver.calls == [("turn_on",), ("select_source", "TV Audio")]
    assert room.tv.calls == [("select_source", "NRK TV")]


async def test_a_tv_that_never_wakes_is_reported(hass, room, entry):
    room.tv.set(state=MediaPlayerState.OFF)
    await setup(hass, entry)
    with pytest.raises(HomeAssistantError) as err:
        await call(hass, "media_player", "select_source", THEATER, source="Netflix")
    assert err.value.translation_key == "no_response"
    assert ("select_source", "Netflix") not in room.tv.calls


async def test_unknown_sources_are_refused(hass, room, entry):
    await setup(hass, entry)
    with pytest.raises(HomeAssistantError) as err:
        await call(hass, "media_player", "select_source", THEATER, source="Radio")
    assert err.value.translation_key == "unknown_source"


async def test_power_turns_both_on_and_off(hass, room, entry):
    await setup(hass, entry)
    await call(hass, "media_player", "turn_off", THEATER)
    assert room.tv.calls == [("turn_off",)] and room.receiver.calls == [("turn_off",)]
    assert hass.states.get(THEATER).state == MediaPlayerState.OFF
    await call(hass, "media_player", "turn_on", THEATER)
    # Without Wake-on-LAN or TURN_ON, only the receiver can be turned on.
    assert room.receiver.calls[-1] == ("turn_on",)
    assert room.tv.calls == [("turn_off",)]
    assert hass.states.get(THEATER).attributes["can_turn_on_tv"] is False


async def test_volume_and_media_go_to_the_right_player(hass, room, entry):
    await setup(hass, entry)
    await call(hass, "media_player", "volume_up", THEATER)
    await call(hass, "media_player", "volume_mute", THEATER, is_volume_muted=True)
    assert room.receiver.calls == [("volume_up",), ("mute", True)]
    assert hass.states.get(THEATER).attributes["is_volume_muted"] is True
    await call(hass, "media_player", "media_pause", THEATER)
    assert room.cast.calls == [("pause",)]
    assert hass.states.get(THEATER).state == MediaPlayerState.PAUSED


async def test_arrow_keys_follow_the_active_source(hass, room, entry):
    await setup(hass, entry)
    await call(hass, "remote", "send_command", REMOTE, command=["up", "ok"])
    assert room.remote.commands == ["up", "ok"]
    assert room.buttons == []
    room.receiver.set(source="Game")
    await call(hass, "remote", "send_command", REMOTE, command=["left", "ok", "back"])
    assert room.buttons == [
        ("media_player.lg", "LEFT"),
        ("media_player.lg", "ENTER"),
        ("media_player.lg", "BACK"),
    ]


async def test_android_tv_remotes_get_their_key_names(hass, room, entry):
    await setup(hass, entry)
    theater = entry.runtime_data
    registry = er.async_get(hass)
    registry.async_get_or_create("remote", "androidtv_remote", "box", suggested_object_id="box")
    sent = []

    async def record(domain, service, entity_id, **data):
        sent.append((domain, entity_id, data))

    with (
        patch.object(theater, "_call", record),
        patch.object(
            theater,
            "active",
            lambda: theater.configured[0].__class__(
                "receiver", "Media Player", remote="remote.box"
            ),
        ),
    ):
        hass.states.async_set("remote.box", "on")
        await theater.async_send_command(["up", "ok", "back", "KEYCODE_TV"])
    assert [d["command"] for _, _, d in sent] == ["DPAD_UP", "DPAD_CENTER", "BACK", "KEYCODE_TV"]


async def test_activities_are_sources(hass, room, entry):
    await setup(hass, entry)
    state = hass.states.get(REMOTE)
    assert state.attributes["activity_list"] == ["Chromecast", "PlayStation", "NRK TV", "Netflix"]
    assert state.attributes["current_activity"] == "Chromecast"
    await call(hass, "remote", "turn_on", REMOTE, activity="NRK TV")
    assert room.tv.calls == [("select_source", "NRK TV")]


async def test_tv_speakers_raise_a_problem_that_can_be_fixed(hass, room, entry):
    await setup(hass, entry)
    assert hass.states.get(AUDIO).state == "off"
    room.tv.set(extra_state_attributes={"sound_output": "tv_speaker"})
    await hass.async_block_till_done()
    assert hass.states.get(AUDIO).state == "on"
    assert hass.states.get(THEATER).attributes["audio_problem"] is True
    await call(hass, "home_theater", "use_receiver", THEATER)
    assert room.outputs == ["external_arc"]
    assert hass.states.get(AUDIO).state == "off"


async def test_unavailable_devices_make_the_room_unavailable(hass, room, entry):
    await setup(hass, entry)
    room.tv.set(available=False)
    room.receiver.set(available=False)
    await hass.async_block_till_done()
    assert hass.states.get(THEATER).state == "unavailable"
    assert hass.states.get(AUDIO).state == "unavailable"


async def test_unload(hass, room, entry):
    await setup(hass, entry)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(THEATER).state == "unavailable"
