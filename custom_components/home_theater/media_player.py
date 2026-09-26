"""The room as one media player: power, sources, volume and what is playing."""

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerState,
)
from homeassistant.components.media_player import MediaPlayerEntityFeature as F

from .const import TV
from .entity import TheaterEntity

VOLUME = F.VOLUME_STEP | F.VOLUME_SET | F.VOLUME_MUTE
MEDIA = (F.PLAY, F.PAUSE, F.STOP, F.NEXT_TRACK, F.PREVIOUS_TRACK)
PLAYING = {
    "playing": MediaPlayerState.PLAYING,
    "paused": MediaPlayerState.PAUSED,
    "buffering": MediaPlayerState.BUFFERING,
}


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([TheaterMediaPlayer(entry.runtime_data)])


class TheaterMediaPlayer(TheaterEntity, MediaPlayerEntity):
    _attr_device_class = MediaPlayerDeviceClass.TV

    def __init__(self, theater):
        super().__init__(theater, "theater")

    @property
    def state(self):
        theater = self.theater
        if not theater.on:
            return MediaPlayerState.OFF
        playing = theater.state(theater.playing_entity())
        if playing and playing.state in PLAYING:
            return PLAYING[playing.state]
        return MediaPlayerState.ON

    @property
    def supported_features(self):
        theater = self.theater
        features = F.TURN_ON | F.TURN_OFF | F.SELECT_SOURCE
        volume = theater.volume_entity
        for feature in (F.VOLUME_STEP, F.VOLUME_SET, F.VOLUME_MUTE):
            if theater.supports(volume, feature):
                features |= feature
        for feature in MEDIA:
            if theater.supports(theater.playing_entity(), feature) or theater.supports(
                theater.tv, feature
            ):
                features |= feature
        return features

    @property
    def source(self):
        active = self.theater.active()
        return active.label if active else None

    @property
    def source_list(self):
        return [s.label for s in self.theater.favourites()]

    @property
    def volume_level(self):
        value = self.theater.attr(self.theater.volume_entity, "volume_level")
        return value if isinstance(value, int | float) else None

    @property
    def is_volume_muted(self):
        value = self.theater.attr(self.theater.volume_entity, "is_volume_muted")
        return value if isinstance(value, bool) else None

    @property
    def app_name(self):
        theater = self.theater
        active = theater.active()
        if active and active.device == TV:
            return active.source
        return theater.attr(theater.playing_entity(), "app_name")

    def _media(self, key):
        return self.theater.attr(self.theater.playing_entity(), key)

    @property
    def media_title(self):
        return self._media("media_title")

    @property
    def media_artist(self):
        return self._media("media_artist")

    @property
    def media_album_name(self):
        return self._media("media_album_name")

    @property
    def media_series_title(self):
        return self._media("media_series_title")

    @property
    def media_season(self):
        return self._media("media_season")

    @property
    def media_episode(self):
        return self._media("media_episode")

    @property
    def media_content_type(self):
        return self._media("media_content_type")

    @property
    def media_duration(self):
        return self._media("media_duration")

    @property
    def media_position(self):
        return self._media("media_position")

    @property
    def media_position_updated_at(self):
        return self._media("media_position_updated_at")

    @property
    def entity_picture(self):
        # The playing player's own proxied picture, with its own access token.
        picture = self._media("entity_picture")
        return picture if isinstance(picture, str) else None

    @property
    def extra_state_attributes(self):
        theater = self.theater
        active = theater.active()
        return {
            "active_device": active.device if active else None,
            "active_input": active.source if active else None,
            "linked_player": theater.playing_entity(),
            "tv_sound_output": theater.attr(theater.tv, "sound_output"),
            "can_turn_on_tv": theater.can_wake_tv,
            "audio_problem": theater.arc_problem(),
            "tv": theater.tv,
            "receiver": theater.receiver,
            # A media player drops source_list while off; these stay for dashboards.
            "sources": [s.label for s in theater.favourites()],
            "all_sources": [s.label for s in theater.all_sources()],
        }

    async def async_turn_on(self):
        await self.theater.async_turn_on()

    async def async_turn_off(self):
        await self.theater.async_turn_off()

    async def async_select_source(self, source):
        await self.theater.async_select_source(source)

    async def async_volume_up(self):
        await self.theater.async_volume("volume_up")

    async def async_volume_down(self):
        await self.theater.async_volume("volume_down")

    async def async_set_volume_level(self, volume):
        await self.theater.async_volume("volume_set", volume_level=volume)

    async def async_mute_volume(self, mute):
        await self.theater.async_volume("volume_mute", is_volume_muted=mute)

    async def async_media_play(self):
        await self.theater.async_media("media_play", F.PLAY)

    async def async_media_pause(self):
        await self.theater.async_media("media_pause", F.PAUSE)

    async def async_media_stop(self):
        await self.theater.async_media("media_stop", F.STOP)

    async def async_media_next_track(self):
        await self.theater.async_media("media_next_track", F.NEXT_TRACK)

    async def async_media_previous_track(self):
        await self.theater.async_media("media_previous_track", F.PREVIOUS_TRACK)

    async def async_use_receiver(self):
        await self.theater.async_use_receiver()
