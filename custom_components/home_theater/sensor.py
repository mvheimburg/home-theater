"""What is on: the room's source, readable while the players are off."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity

from .entity import TheaterEntity

OFF = "off"


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([SourceSensor(entry.runtime_data)])


class SourceSensor(TheaterEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM

    def __init__(self, theater):
        super().__init__(theater, "source")

    @property
    def options(self):
        labels = [s.label for s in self.theater.favourites() + self.theater.all_sources()]
        active = self.theater.active()
        if active:
            labels.append(active.label)
        return [OFF, *dict.fromkeys(labels)]

    @property
    def native_value(self):
        if not self.theater.on:
            return OFF
        active = self.theater.active()
        return active.label if active else None

    @property
    def extra_state_attributes(self):
        theater = self.theater
        active = theater.active()
        return {
            "device": active.device if active else None,
            "input": active.source if active else None,
            "linked_player": theater.playing_entity(),
            # A media player drops its source list while off; this one stays.
            "source_list": [s.label for s in theater.favourites()],
            "all_sources": [s.label for s in theater.all_sources()],
        }
