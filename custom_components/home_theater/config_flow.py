"""Set up a room: its TV and receiver, how they connect, and the favourite sources."""

import copy

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_MAC,
    CONF_RECEIVER,
    CONF_SOURCES,
    CONF_TV,
    CONF_TV_AUDIO,
    CONF_TV_INPUT,
    DEFAULT_TV_AUDIO,
    DOMAIN,
    RECEIVER,
    TV,
)
from .theater import source_key
from .wol import valid_mac

DEVICE_WORDS = {
    "en": {TV: "TV", RECEIVER: "receiver"},
    "nb": {TV: "TV", RECEIVER: "forsterker"},
}


def player(**config):
    return selector.EntitySelector(selector.EntitySelectorConfig(domain="media_player", **config))


def choice(options, custom=True):
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options, custom_value=custom, mode=selector.SelectSelectorMode.DROPDOWN
        )
    )


def optional(key, values):
    """An optional field that keeps its saved value, or starts empty."""
    value = values.get(key)
    return vol.Optional(key, description={"suggested_value": value} if value else None)


def device_schema(values, name=None):
    fields = {}
    if name is not None:
        fields[vol.Required("name", default=name)] = selector.TextSelector()
    fields[optional(CONF_TV, values)] = player(integration="webostv")
    fields[optional(CONF_RECEIVER, values)] = player()
    fields[optional(CONF_MAC, values)] = selector.TextSelector()
    return vol.Schema(fields)


def validate_devices(user_input):
    tv = user_input.get(CONF_TV) or None
    receiver = user_input.get(CONF_RECEIVER) or None
    mac = (user_input.get(CONF_MAC) or "").strip() or None
    if not tv and not receiver:
        return None, {"base": "no_devices"}
    if tv and tv == receiver:
        return None, {CONF_RECEIVER: "same_device"}
    if mac and not tv:
        return None, {CONF_MAC: "mac_without_tv"}
    if mac and not valid_mac(mac):
        return None, {CONF_MAC: "invalid_mac"}
    return {CONF_TV: tv, CONF_RECEIVER: receiver, CONF_MAC: mac}, {}


def listed(hass, entry, device, entity_id):
    """A player's sources: live, or as last reported while it was on."""
    state = hass.states.get(entity_id) if entity_id else None
    live = state.attributes.get("source_list") if state else None
    if isinstance(live, list) and live:
        return [str(s) for s in live]
    theater = getattr(entry, "runtime_data", None) if entry else None
    if theater is not None and getattr(theater, device, None) == entity_id:
        return list(theater.known[device])
    return []


def input_schema(hass, entry, values):
    tv_sources = listed(hass, entry, TV, values.get(CONF_TV))
    receiver_sources = listed(hass, entry, RECEIVER, values.get(CONF_RECEIVER))
    audio = values.get(CONF_TV_AUDIO) or DEFAULT_TV_AUDIO
    return vol.Schema(
        {
            optional(CONF_TV_INPUT, values): choice(tv_sources),
            vol.Required(CONF_TV_AUDIO, default=audio): choice(
                sorted({*receiver_sources, audio}, key=str.casefold)
            ),
        }
    )


def clean(options):
    return {key: value for key, value in options.items() if value not in (None, "", [])}


class HomeTheaterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self.title = None
        self.options = {}

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            options, errors = validate_devices(user_input)
            if not errors:
                self.title = user_input["name"].strip() or "TV"
                self.options = options
                if options[CONF_TV] and options[CONF_RECEIVER]:
                    return await self.async_step_inputs()
                return self.async_create_entry(title=self.title, data={}, options=clean(options))
        values = user_input or {}
        return self.async_show_form(
            step_id="user",
            data_schema=device_schema(values, values.get("name", "TV")),
            errors=errors,
        )

    async def async_step_inputs(self, user_input=None):
        if user_input is not None:
            options = {**self.options, **user_input}
            return self.async_create_entry(title=self.title, data={}, options=clean(options))
        return self.async_show_form(
            step_id="inputs", data_schema=input_schema(self.hass, None, self.options)
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return HomeTheaterOptionsFlow()


class HomeTheaterOptionsFlow(config_entries.OptionsFlow):
    """Edits a draft; nothing is saved until Save. Closing keeps the saved settings."""

    def __init__(self):
        self.draft = None
        self.editing = None

    def _draft(self):
        if self.draft is None:
            self.draft = copy.deepcopy(dict(self.config_entry.options))
        return self.draft

    def _word(self, device):
        language = (self.hass.config.language or "en").lower().replace("_", "-").split("-")[0]
        words = DEVICE_WORDS["nb" if language in ("nb", "no", "nn") else "en"]
        return words[device]

    def _available(self):
        """Every receiver input and TV source, except the inputs that connect the two."""
        draft = self._draft()
        audio = draft.get(CONF_TV_AUDIO) or DEFAULT_TV_AUDIO
        result = []
        if draft.get(CONF_RECEIVER):
            for source in listed(self.hass, self.config_entry, RECEIVER, draft[CONF_RECEIVER]):
                if source != audio:
                    result.append((RECEIVER, source))
        if draft.get(CONF_TV):
            for source in listed(self.hass, self.config_entry, TV, draft[CONF_TV]):
                if source != draft.get(CONF_TV_INPUT):
                    result.append((TV, source))
        return result

    async def async_step_init(self, user_input=None):
        self._draft()
        return self.async_show_menu(
            step_id="init", menu_options=["devices", "sources", "source", "save"]
        )

    async def async_step_devices(self, user_input=None):
        errors = {}
        draft = self._draft()
        if user_input is not None:
            options, errors = validate_devices(user_input)
            if not errors:
                for key, value in options.items():
                    if value:
                        draft[key] = value
                    else:
                        draft.pop(key, None)
                if draft.get(CONF_TV) and draft.get(CONF_RECEIVER):
                    return await self.async_step_inputs()
                for key in (CONF_TV_INPUT, CONF_TV_AUDIO):
                    draft.pop(key, None)
                return await self.async_step_init()
        return self.async_show_form(
            step_id="devices", data_schema=device_schema(user_input or draft), errors=errors
        )

    async def async_step_inputs(self, user_input=None):
        draft = self._draft()
        if user_input is not None:
            draft.pop(CONF_TV_INPUT, None)
            draft.update(clean(user_input))
            return await self.async_step_init()
        return self.async_show_form(
            step_id="inputs", data_schema=input_schema(self.hass, self.config_entry, draft)
        )

    async def async_step_sources(self, user_input=None):
        draft = self._draft()
        available = self._available()
        saved = {source_key(s["device"], s["source"]): s for s in draft.get(CONF_SOURCES, [])}
        if user_input is not None:
            chosen = []
            for key in user_input.get(CONF_SOURCES, []):
                device, _, source = key.partition(":")
                chosen.append(saved.get(key, {"device": device, "source": source}))
            if chosen:
                draft[CONF_SOURCES] = chosen
            else:
                draft.pop(CONF_SOURCES, None)
            return await self.async_step_init()
        keys = [source_key(d, s) for d, s in available]
        missing = [key for key in saved if key not in keys]
        options = [
            selector.SelectOptionDict(value=source_key(d, s), label=f"{s} ({self._word(d)})")
            for d, s in available
        ] + [
            selector.SelectOptionDict(
                value=key, label=f"{saved[key]['source']} ({self._word(saved[key]['device'])})"
            )
            for key in missing
        ]
        return self.async_show_form(
            step_id="sources",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_SOURCES, default=list(saved)): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=options, multiple=True)
                    )
                }
            ),
        )

    async def async_step_source(self, user_input=None):
        """Choose a favourite to name, or to link to the player behind it."""
        draft = self._draft()
        saved = draft.get(CONF_SOURCES, [])
        if not saved:
            return self.async_show_form(
                step_id="source", data_schema=vol.Schema({}), errors={"base": "no_sources"}
            )
        if user_input is not None:
            if "source" in user_input:
                self.editing = user_input["source"]
                return await self.async_step_link()
            return await self.async_step_init()
        options = [
            selector.SelectOptionDict(
                value=source_key(s["device"], s["source"]),
                label=s.get("name") or s["source"],
            )
            for s in saved
        ]
        return self.async_show_form(
            step_id="source",
            data_schema=vol.Schema({vol.Required("source"): choice(options, custom=False)}),
        )

    async def async_step_link(self, user_input=None):
        draft = self._draft()
        source = next(
            s for s in draft[CONF_SOURCES] if source_key(s["device"], s["source"]) == self.editing
        )
        if user_input is not None:
            for key in ("name", "player", "remote"):
                value = (user_input.get(key) or "").strip()
                if value:
                    source[key] = value
                else:
                    source.pop(key, None)
            return await self.async_step_init()
        return self.async_show_form(
            step_id="link",
            description_placeholders={"source": source["source"]},
            data_schema=vol.Schema(
                {
                    optional("name", source): selector.TextSelector(),
                    optional("player", source): player(),
                    optional("remote", source): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="remote")
                    ),
                }
            ),
        )

    async def async_step_save(self, user_input=None):
        return self.async_create_entry(data=clean(self._draft()))
