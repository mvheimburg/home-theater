"""Setup and settings run through Home Assistant's real flow manager."""

from homeassistant.components.media_player import MediaPlayerState
from homeassistant.data_entry_flow import FlowResultType

from .conftest import OPTIONS, setup


async def start(hass, **data):
    flow = await hass.config_entries.flow.async_init("home_theater", context={"source": "user"})
    assert flow["type"] == FlowResultType.FORM
    return await hass.config_entries.flow.async_configure(flow["flow_id"], data)


async def test_setup_with_tv_and_receiver_asks_how_they_connect(hass, room):
    flow = await start(
        hass,
        name="Stue",
        tv="media_player.lg",
        receiver="media_player.denon",
        wol_mac="aa:bb:cc:dd:ee:ff",
    )
    assert flow["step_id"] == "inputs"
    schema = flow["data_schema"].schema
    tv_input = next(k for k in schema if k == "tv_input")
    assert schema[tv_input].config["options"] == [
        "Apps",
        "Denon Hjemmekinoanlegg",
        "HDMI 3",
        "Live TV",
        "NRK TV",
        "Netflix",
        "YouTube",
    ]
    flow = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"tv_input": "Denon Hjemmekinoanlegg", "tv_audio": "TV Audio"}
    )
    assert flow["type"] == FlowResultType.CREATE_ENTRY
    assert flow["title"] == "Stue"
    assert flow["options"] == {
        "tv": "media_player.lg",
        "receiver": "media_player.denon",
        "wol_mac": "aa:bb:cc:dd:ee:ff",
        "tv_input": "Denon Hjemmekinoanlegg",
        "tv_audio": "TV Audio",
    }
    await hass.async_block_till_done()
    assert hass.states.get("media_player.stue_theater")


async def test_setup_with_only_a_tv(hass, room):
    flow = await start(hass, name="Soverom 1", tv="media_player.lg")
    assert flow["type"] == FlowResultType.CREATE_ENTRY
    assert flow["options"] == {"tv": "media_player.lg"}


async def test_setup_validation(hass, room):
    flow = await start(hass, name="Stue")
    assert flow["errors"] == {"base": "no_devices"}
    flow = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"name": "Stue", "tv": "media_player.lg", "receiver": "media_player.lg"}
    )
    assert flow["errors"] == {"receiver": "same_device"}
    flow = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"name": "Stue", "receiver": "media_player.denon", "wol_mac": "aa:bb"}
    )
    assert flow["errors"] == {"wol_mac": "mac_without_tv"}
    flow = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"name": "Stue", "tv": "media_player.lg", "wol_mac": "not a mac"}
    )
    assert flow["errors"] == {"wol_mac": "invalid_mac"}


async def menu(hass, flow, choice):
    return await hass.config_entries.options.async_configure(
        flow["flow_id"], {"next_step_id": choice}
    )


async def test_settings_are_a_draft_until_save(hass, room, entry):
    await setup(hass, entry)
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    assert flow["type"] == FlowResultType.MENU
    flow = await menu(hass, flow, "source")
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"source": "receiver:Game"}
    )
    assert flow["step_id"] == "link"
    assert flow["description_placeholders"] == {"source": "Game"}
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"name": "PS5", "player": "media_player.cast"}
    )
    assert flow["type"] == FlowResultType.MENU
    # Closing the dialog here discards the draft.
    hass.config_entries.options.async_abort(flow["flow_id"])
    assert entry.options == OPTIONS

    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await menu(hass, flow, "source")
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"source": "receiver:Game"}
    )
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"name": "PS5"})
    flow = await menu(hass, flow, "save")
    assert flow["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["sources"][1] == {"device": "receiver", "source": "Game", "name": "PS5"}
    assert "PS5" in hass.states.get("media_player.stue_theater").attributes["source_list"]


async def test_favourites_offer_sources_learned_while_on(hass, room, entry):
    await setup(hass, entry)
    room.tv.set(state=MediaPlayerState.OFF, source_list=None)
    await hass.async_block_till_done()
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await menu(hass, flow, "sources")
    field = next(iter(flow["data_schema"].schema))
    options = flow["data_schema"].schema[field].config["options"]
    values = [o["value"] for o in options]
    assert "tv:YouTube" in values
    assert "tv:Denon Hjemmekinoanlegg" not in values and "receiver:TV Audio" not in values
    assert {"value": "receiver:Game", "label": "Game (receiver)"} in options
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"sources": ["tv:YouTube", "receiver:Media Player"]}
    )
    flow = await menu(hass, flow, "save")
    assert entry.options["sources"] == [
        {"device": "tv", "source": "YouTube"},
        # Details of a kept favourite survive re-selection.
        OPTIONS["sources"][0],
    ]


async def test_device_changes_ask_for_inputs_again(hass, room, entry):
    await setup(hass, entry)
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await menu(hass, flow, "devices")
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"],
        {"tv": "media_player.lg", "receiver": "media_player.denon", "wol_mac": "AA-BB-CC-DD-EE-FF"},
    )
    assert flow["step_id"] == "inputs"
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"tv_input": "HDMI 3", "tv_audio": "TV Audio"}
    )
    flow = await menu(hass, flow, "save")
    assert entry.options["tv_input"] == "HDMI 3"
    assert entry.options["wol_mac"] == "AA-BB-CC-DD-EE-FF"
    assert hass.states.get("media_player.stue_theater").attributes["can_turn_on_tv"] is True
