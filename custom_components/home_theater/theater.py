"""One room: a TV, an AV receiver and the players behind their inputs.

The TV and receiver integrations stay authoritative. This follows their states,
works out what is on screen, and sequences both devices for power and source
changes. It never writes their states.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.media_player import MediaPlayerEntityFeature as F
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    STATE_OFF,
    STATE_STANDBY,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store

from .const import (
    CONF_MAC,
    CONF_RECEIVER,
    CONF_SOURCES,
    CONF_TV,
    CONF_TV_AUDIO,
    CONF_TV_INPUT,
    DEFAULT_TV_AUDIO,
    DOMAIN,
    LIVE_TV,
    RECEIVER,
    RECEIVER_OUTPUT,
    SWITCH_ATTEMPTS,
    SWITCH_TIMEOUT,
    TV,
    WAKE_TIMEOUT,
)
from .wol import async_wake

OFF = {STATE_OFF, STATE_STANDBY}
MISSING = {STATE_UNAVAILABLE, STATE_UNKNOWN}
# Remote keys by the integration behind a remote entity; other commands pass through.
KEYS = {
    "webostv": {
        "up": "UP",
        "down": "DOWN",
        "left": "LEFT",
        "right": "RIGHT",
        "ok": "ENTER",
        "select": "ENTER",
        "back": "BACK",
        "home": "HOME",
        "menu": "MENU",
        "info": "INFO",
    },
    "androidtv_remote": {
        "up": "DPAD_UP",
        "down": "DPAD_DOWN",
        "left": "DPAD_LEFT",
        "right": "DPAD_RIGHT",
        "ok": "DPAD_CENTER",
        "select": "DPAD_CENTER",
        "back": "BACK",
        "home": "HOME",
        "menu": "MENU",
        "info": "INFO",
    },
    "apple_tv": {
        "ok": "select",
        "back": "menu",
    },
}


@dataclass(frozen=True)
class Source:
    """A receiver input or a TV input/app, with the player linked to it."""

    device: str
    source: str
    name: str | None = None
    player: str | None = None
    remote: str | None = None

    @property
    def label(self) -> str:
        return self.name or self.source

    @property
    def key(self) -> str:
        return f"{self.device}:{self.source}"

    @classmethod
    def load(cls, data: dict) -> Source:
        return cls(
            device=data["device"],
            source=data["source"],
            name=data.get("name") or None,
            player=data.get("player") or None,
            remote=data.get("remote") or None,
        )


def source_key(device: str, source: str) -> str:
    return f"{device}:{source}"


class Theater:
    def __init__(self, hass: HomeAssistant, entry) -> None:
        self.hass = hass
        self.entry = entry
        options = entry.options
        self.tv: str | None = options.get(CONF_TV) or None
        self.receiver: str | None = options.get(CONF_RECEIVER) or None
        self.tv_input: str | None = options.get(CONF_TV_INPUT) or None
        self.tv_audio: str | None = (
            (options.get(CONF_TV_AUDIO) or DEFAULT_TV_AUDIO) if self.receiver else None
        )
        self.mac: str | None = options.get(CONF_MAC) or None
        self.configured = [Source.load(s) for s in options.get(CONF_SOURCES, [])]
        self.listeners: set[Callable[[], None]] = set()
        # Source lists as last reported: players drop them while they are off.
        self.known: dict[str, list[str]] = {TV: [], RECEIVER: []}
        self._store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self._waiters: list[tuple[Callable[[], bool], asyncio.Future]] = []
        self._unsub: Callable[[], None] | None = None

    # ----- lifecycle

    async def load(self) -> None:
        data = await self._store.async_load() or {}
        for device in (TV, RECEIVER):
            self.known[device] = list(data.get(device, []))
        self._remember()

    def start(self) -> None:
        watched = {self.tv, self.receiver}
        for source in self.configured:
            watched |= {source.player, source.remote}
        watched.discard(None)
        self._unsub = async_track_state_change_event(self.hass, sorted(watched), self._changed)

    def stop(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None
        for _, future in self._waiters:
            if not future.done():
                future.cancel()
        self._waiters.clear()

    @callback
    def _changed(self, event: Event) -> None:
        self._remember()
        for test, future in list(self._waiters):
            if not future.done() and test():
                future.set_result(None)
        for listener in list(self.listeners):
            listener()

    @callback
    def _remember(self) -> None:
        changed = False
        for device, entity_id in ((TV, self.tv), (RECEIVER, self.receiver)):
            listed = self.attr(entity_id, "source_list")
            if isinstance(listed, list) and listed and listed != self.known[device]:
                self.known[device] = [str(s) for s in listed]
                changed = True
        if changed:
            self._store.async_delay_save(lambda: dict(self.known), 5)

    # ----- reading states

    def state(self, entity_id: str | None) -> State | None:
        return self.hass.states.get(entity_id) if entity_id else None

    def attr(self, entity_id: str | None, key: str):
        state = self.state(entity_id)
        return state.attributes.get(key) if state else None

    def available(self, entity_id: str | None) -> bool:
        state = self.state(entity_id)
        return state is not None and state.state not in MISSING

    def is_on(self, entity_id: str | None) -> bool:
        state = self.state(entity_id)
        return state is not None and state.state not in OFF | MISSING

    def supports(self, entity_id: str | None, feature: int) -> bool:
        features = self.attr(entity_id, ATTR_SUPPORTED_FEATURES)
        return isinstance(features, int) and features & feature == feature

    @property
    def any_available(self) -> bool:
        return self.available(self.tv) or self.available(self.receiver)

    @property
    def on(self) -> bool:
        return self.is_on(self.tv) or self.is_on(self.receiver)

    @property
    def can_wake_tv(self) -> bool:
        return bool(self.tv) and (self.supports(self.tv, F.TURN_ON) or bool(self.mac))

    # ----- sources

    def _details(self, device: str, source: str) -> Source:
        for configured in self.configured:
            if configured.device == device and configured.source == source:
                return configured
        return Source(device, source)

    def all_sources(self) -> list[Source]:
        """Every source both players offer, receiver inputs first."""
        receiver = [s for s in self.known[RECEIVER] if s != self.tv_audio] if self.receiver else []
        tv = [s for s in self.known[TV] if s != self.tv_input] if self.tv else []
        return [self._details(RECEIVER, s) for s in receiver] + [self._details(TV, s) for s in tv]

    def favourites(self) -> list[Source]:
        """Configured sources, or the receiver's inputs and Live TV."""
        if self.configured:
            return list(self.configured)
        every = self.all_sources()
        if not self.receiver:
            return every
        return [s for s in every if s.device == RECEIVER or s.source == LIVE_TV]

    def find(self, label: str) -> Source | None:
        candidates = self.favourites() + self.all_sources() + self.configured
        for match in (lambda s: s.label == label, lambda s: s.source == label):
            for source in candidates:
                if match(source):
                    return source
        return None

    def active(self) -> Source | None:
        """What is on screen: a receiver input other than TV audio, else the TV's app."""
        if not self.on:
            return None
        receiver_input = self.attr(self.receiver, "source") if self.is_on(self.receiver) else None
        if receiver_input and receiver_input != self.tv_audio:
            return self._details(RECEIVER, receiver_input)
        tv_source = self.attr(self.tv, "source") if self.is_on(self.tv) else None
        if tv_source and tv_source != self.tv_input:
            return self._details(TV, tv_source)
        if receiver_input:
            return self._details(RECEIVER, receiver_input)
        return None

    def playing_entity(self) -> str | None:
        """The player that knows what is playing: a linked player, else the TV for its apps."""
        active = self.active()
        if active is None:
            return None
        if active.player and self.available(active.player):
            return active.player
        if active.device == TV:
            return self.tv
        return None

    def arc_problem(self) -> bool:
        output = self.attr(self.tv, "sound_output")
        return (
            bool(self.receiver)
            and self.is_on(self.tv)
            and isinstance(output, str)
            and (output.startswith("tv_speaker") or output == "headphone")
        )

    @property
    def volume_entity(self) -> str | None:
        return self.receiver or self.tv

    # ----- actions

    async def _call(self, domain: str, service: str, entity_id: str, **data) -> None:
        await self.hass.services.async_call(
            domain, service, {ATTR_ENTITY_ID: entity_id, **data}, blocking=True
        )

    async def _wait(self, test: Callable[[], bool], timeout: float, device: str) -> None:
        if test():
            return
        future = self.hass.loop.create_future()
        waiter = (test, future)
        self._waiters.append(waiter)
        try:
            async with asyncio.timeout(timeout):
                await future
        except TimeoutError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="no_response",
                translation_placeholders={"device": device},
            ) from err
        finally:
            if waiter in self._waiters:
                self._waiters.remove(waiter)

    async def _wake(self, entity_id: str) -> None:
        if self.is_on(entity_id):
            return
        if not self.available(entity_id) and entity_id != self.tv:
            raise self._unavailable(entity_id)
        if self.supports(entity_id, F.TURN_ON):
            await self._call("media_player", "turn_on", entity_id)
        elif entity_id == self.tv and self.mac:
            await async_wake(self.hass, self.mac)

    async def _switch(self, entity_id: str, source: str) -> None:
        """Select a source, retrying while a freshly woken TV settles."""
        for attempt in range(SWITCH_ATTEMPTS):
            try:
                await self._call("media_player", "select_source", entity_id, source=source)
                await self._wait(
                    lambda: self.attr(entity_id, "source") == source, SWITCH_TIMEOUT, entity_id
                )
                return
            except HomeAssistantError:
                if attempt == SWITCH_ATTEMPTS - 1:
                    raise
                await asyncio.sleep(1)

    def _unavailable(self, entity_id: str | None) -> HomeAssistantError:
        return HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="unavailable",
            translation_placeholders={"device": entity_id or "-"},
        )

    async def async_turn_on(self) -> None:
        if not self.any_available and not self.can_wake_tv:
            raise self._unavailable(self.tv or self.receiver)
        if self.receiver and self.available(self.receiver):
            await self._wake(self.receiver)
        if self.tv and self.can_wake_tv:
            await self._wake(self.tv)

    async def async_turn_off(self) -> None:
        for entity_id in (self.tv, self.receiver):
            if entity_id and self.is_on(entity_id):
                await self._call("media_player", "turn_off", entity_id)

    async def async_select_source(self, label: str) -> None:
        source = self.find(label)
        if source is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="unknown_source",
                translation_placeholders={"source": label},
            )
        if source.device == RECEIVER:
            await self._select_receiver_source(source)
        else:
            await self._select_tv_source(source)

    async def _select_receiver_source(self, source: Source) -> None:
        receiver = self.receiver
        if not receiver or not self.available(receiver):
            raise self._unavailable(receiver)
        await self._wake(receiver)
        await self._wait(lambda: self.is_on(receiver), WAKE_TIMEOUT, receiver)
        await self._switch(receiver, source.source)
        if self.tv and self.tv_input:
            if not self.is_on(self.tv):
                if not self.can_wake_tv:
                    return  # The receiver's HDMI control may wake the TV on its own.
                await self._wake(self.tv)
                await self._wait(lambda: self.is_on(self.tv), WAKE_TIMEOUT, self.tv)
            await self._switch(self.tv, self.tv_input)

    async def _select_tv_source(self, source: Source) -> None:
        tv = self.tv
        if not tv:
            raise self._unavailable(tv)
        if self.receiver and self.available(self.receiver):
            await self._wake(self.receiver)
            await self._wait(lambda: self.is_on(self.receiver), WAKE_TIMEOUT, self.receiver)
            if self.tv_audio:
                await self._switch(self.receiver, self.tv_audio)
        if not self.is_on(tv):
            # Without Wake-on-LAN, the receiver's HDMI control may still wake the TV.
            await self._wake(tv)
            await self._wait(lambda: self.is_on(tv), WAKE_TIMEOUT, tv)
        await self._switch(tv, source.source)

    async def async_volume(self, service: str, **data) -> None:
        entity_id = self.volume_entity
        if not entity_id or not self.is_on(entity_id):
            raise self._unavailable(entity_id)
        await self._call("media_player", service, entity_id, **data)

    async def async_media(self, service: str, feature: int) -> None:
        """Play/pause/skip on whatever is playing."""
        entity_id = self.playing_entity()
        if not entity_id or not self.supports(entity_id, feature):
            entity_id = self.tv if self.supports(self.tv, feature) else None
        if not entity_id:
            raise self._unavailable(self.tv)
        await self._call("media_player", service, entity_id)

    async def async_send_command(self, commands: list[str], repeats: int = 1) -> None:
        """Remote keys go to the active source's remote, else to the TV."""
        active = self.active()
        remote = active.remote if active and self.available(active.remote) else None
        platform = None
        if remote:
            entry = er.async_get(self.hass).async_get(remote)
            platform = entry.platform if entry else None
        elif not self.tv or not self.is_on(self.tv):
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="no_remote_target")
        # Unknown remotes get the commands as given; the TV gets webOS key names.
        keys = KEYS.get(platform, {}) if remote else KEYS["webostv"]
        for _ in range(max(1, repeats)):
            for command in commands:
                key = keys.get(command.lower(), command)
                if remote:
                    await self._call("remote", "send_command", remote, command=key)
                else:
                    await self._call("webostv", "button", self.tv, button=key.upper())

    async def async_use_receiver(self) -> None:
        if not self.tv or not self.is_on(self.tv):
            raise self._unavailable(self.tv)
        await self._call("webostv", "select_sound_output", self.tv, sound_output=RECEIVER_OUTPUT)
