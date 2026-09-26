"""The room's remote: arrow keys follow the active source; activities are sources."""

from homeassistant.components.remote import ATTR_ACTIVITY, RemoteEntity, RemoteEntityFeature

from .entity import TheaterEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([TheaterRemote(entry.runtime_data)])


class TheaterRemote(TheaterEntity, RemoteEntity):
    _attr_supported_features = RemoteEntityFeature.ACTIVITY

    def __init__(self, theater):
        super().__init__(theater, "remote")

    @property
    def is_on(self):
        return self.theater.on

    @property
    def current_activity(self):
        active = self.theater.active()
        return active.label if active else None

    @property
    def activity_list(self):
        return [s.label for s in self.theater.favourites()]

    async def async_turn_on(self, **kwargs):
        if activity := kwargs.get(ATTR_ACTIVITY):
            await self.theater.async_select_source(activity)
        else:
            await self.theater.async_turn_on()

    async def async_turn_off(self, **kwargs):
        await self.theater.async_turn_off()

    async def async_send_command(self, command, **kwargs):
        await self.theater.async_send_command(list(command), kwargs.get("num_repeats", 1))
