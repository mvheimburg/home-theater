"""Shared entity plumbing for one room."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN


class TheaterEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, theater, key):
        self.theater = theater
        self.key = key
        self._attr_unique_id = f"{theater.entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, theater.entry.entry_id)},
            name=theater.entry.title,
            manufacturer="Home Theater",
            model="TV and receiver",
        )

    @property
    def suggested_object_id(self):
        # "<name>_<key>" in any UI language: "Stue" -> media_player.stue_theater.
        return self.key

    @property
    def available(self):
        return self.theater.any_available or self.theater.can_wake_tv

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.theater.listeners.add(self.async_write_ha_state)
        self.async_on_remove(lambda: self.theater.listeners.discard(self.async_write_ha_state))
