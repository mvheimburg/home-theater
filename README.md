<img src="docs/icon.png" alt="" width="96" align="right">

# Home Theater

One Home Assistant device per room for a TV, an AV receiver and the players behind their inputs: power, sources on both devices, what is actually playing, and arrow keys that follow the source.

A TV and a receiver each know only half of the story. The receiver knows it is on its *Media Player* input; the TV knows it is on the receiver's HDMI input or running Netflix; the Chromecast behind that input knows the title. Home Theater follows the signal path and turns the room into one device with one source: *Chromecast · Episode 4*, *PlayStation*, *Netflix*. Choosing a source switches both devices, and wakes them first when the room is off.

It builds on the integrations that already talk to your devices: **LG webOS TV** for the TV, a receiver `media_player` such as **Denon AVR**, and optionally **Google Cast**, **Music Assistant**, **Apple TV** or **Android TV Remote** for the players. They stay authoritative; Home Theater never writes their states. Tested with Home Assistant 2026.9.

## Entities

For a room named **Stue**:

| Entity | What it is |
| --- | --- |
| `media_player.stue_theater` | The room. On while the TV or receiver is on; *playing*/*paused* from the player on screen. `source` is the friendly source, `source_list` your favourites. Title, series, artist, app and picture come from the linked player (or the TV app). Volume goes to the receiver. Turn on/off, select source, volume, play/pause. |
| `sensor.stue_source` | What is on: a source name, or `off`. Its `source_list` and `all_sources` attributes stay available while the devices are off. |
| `remote.stue_remote` | Arrow keys: `up`, `down`, `left`, `right`, `ok`, `back`, `home`, `menu`, `info`, sent to the active source's remote or else to the TV. Activities are the favourite sources. |
| `binary_sensor.stue_audio` | Problem sensor: on when the TV plays through its own speakers instead of the receiver (only with both a TV and a receiver). |

Entity IDs are `<room>_<key>` in English whatever language Home Assistant uses, and are never renamed after they are created.

## Install

Add `https://github.com/mvheimburg/home-theater` to HACS as an **Integration** custom repository, install **Home Theater** and restart Home Assistant. Then add it under **Settings → Devices & services → Add integration → Home Theater**, once per room.

## Set up a room

1. **Room name, TV and receiver.** The TV must be an LG webOS media player; the receiver can be any media player with sources. Either is optional, but not both.
2. **TV MAC address** (optional): Home Theater sends the Wake-on-LAN packet itself, so no separate automation is needed. Enable *Turn on via Wi-Fi* (or *Mobile TV On*) on the TV; a wired connection is the most reliable. Without it, only the receiver is turned on, and its HDMI control may wake the TV.
3. **How they connect** (with both a TV and a receiver):
   - *TV input the receiver is connected to*: the TV's HDMI input for the receiver, often renamed by the TV (for example *Denon Hjemmekinoanlegg*).
   - *Receiver input for the TV's own sound*: usually *TV Audio*, played over HDMI ARC.

   The lists come from the devices; while one is off, type the name instead.

Later changes live under **Settings → Devices & services → Home Theater → Configure**, as a menu:

- **TV, receiver and Wake-on-LAN**, then how they connect.
- **Favourite sources**: pick the sources to offer, in order. Leave empty for the receiver's inputs and Live TV. Home Theater remembers each device's source list, so this works while the TV is off.
- **Name or link a source**: give a source a display name (the receiver's *Media Player* as *Chromecast*), link the **player** on that input (a Chromecast or its Music Assistant player) for titles and pictures, and a **remote** (Android TV Remote, Apple TV) for its arrow keys.
- **Save** stores the draft. Closing the dialog keeps the saved settings. Saving reloads the room; it never switches a device.

## How choosing a source works

- A **receiver source** (Chromecast, PlayStation): wake the receiver, select its input, then put the TV on the receiver's input (waking it if Home Theater can).
- A **TV source** (Netflix, NRK TV, Live TV): wake the receiver and select *TV Audio*, wake the TV and wait for it, then start the app.

Each step waits for the device to confirm and retries a TV that is still settling. A device that does not respond is reported as an error rather than silently skipped.

## Examples

```yaml
# Dim the lights when the PlayStation comes on.
triggers:
  - trigger: state
    entity_id: sensor.stue_source
    to: PlayStation
actions:
  - action: light.turn_on
    target: { area_id: stue }
    data: { brightness_pct: 20 }
```

```yaml
# Start NRK TV: wakes both devices, sets the receiver to TV Audio, then opens the app.
action: media_player.select_source
target: { entity_id: media_player.stue_theater }
data: { source: NRK TV }
```

```yaml
action: remote.send_command
target: { entity_id: remote.stue_remote }
data: { command: [down, down, ok] }
```

`home_theater.use_receiver` (target: the room's media player) switches the TV's sound output back to the receiver, the fix for `binary_sensor.<room>_audio`.

## Home Theater Card

[Home Theater Card](https://github.com/mvheimburg/lovelace-home-theater) is the matching dashboard card. Version 0.1 binds the TV and receiver directly and works without this integration; a later card version will use the room's entities.

## ARC checklist

When TV apps play but the receiver is silent: connect the receiver's **HDMI MONITOR (ARC)** output to the TV's **ARC/eARC** input; on the receiver turn on **HDMI Control**, **ARC** and **TV Audio Switching**; on the LG turn on **SIMPLINK (HDMI-CEC)** and set **Sound Out** to **HDMI (ARC) Device**. With ARC-only receivers (such as the Denon AVR-X2200W and X3300W), try **eARC Support** off on the TV.

## Development

```sh
python -m venv .venv && .venv/bin/pip install -r requirements_test.txt
.venv/bin/python -m pytest -q
.venv/bin/ruff check custom_components tests
```

Bump the version in both `pyproject.toml` and `custom_components/home_theater/manifest.json`; a push to `main` with a new version is released as `v<version>`.
