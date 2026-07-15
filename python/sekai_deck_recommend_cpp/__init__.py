from __future__ import annotations

import json
import os
from collections.abc import Sequence, Set
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ._models import (
    DeckRecommendCardConfig,
    DeckRecommendGaOptions,
    DeckRecommendOptions,
    DeckRecommendResult,
    DeckRecommendSaOptions,
    DeckRecommendSingleCardConfig,
    DeckRecommendUserData,
    RecommendCard,
    RecommendDeck,
    RecommendSupportDeckCard,
)

_VALID_REGIONS = {"jp", "en", "tw", "kr", "cn"}
_VALID_LIVE_TYPES = {
    "multi",
    "solo",
    "auto",
    "challenge",
    "challenge_auto",
    "mysekai",
}
_engine_thread_count = 0


def _native_sequence(value, name: str):
    if isinstance(value, (str, bytes)) or not isinstance(value, (Sequence, Set)):
        raise TypeError(f"{name} must be a sequence")
    return list(value)


def _raise_batch_error(index: int, error: Exception):
    if isinstance(error, RuntimeError):
        raise RuntimeError(f"batch item {index} failed: {error}") from error
    raise ValueError(f"batch item {index}: {error}") from error


def set_engine_thread_count(threads: int) -> None:
    global _engine_thread_count
    if not isinstance(threads, int):
        raise TypeError("threads must be an int")
    if threads < 0:
        raise ValueError("threads must be non-negative")
    _engine_thread_count = min(threads, os.cpu_count() or 1)


def _effective_engine_thread_count() -> int:
    if _engine_thread_count > 0:
        return _engine_thread_count
    raw = os.environ.get("DECK_ENGINE_THREADS", "")
    try:
        configured = int(raw)
    except ValueError:
        configured = 1
    if configured <= 0:
        return 1
    return min(configured, os.cpu_count() or 1)


class SekaiDeckRecommend:
    def __init__(self) -> None:
        try:
            from _allium_deck_native import NativeEngine
        except ImportError:
            self._native = None
        else:
            self._native = NativeEngine()

    def _require_native(self):
        if self._native is None:
            raise RuntimeError("_allium_deck_native is not installed")
        return self._native

    @staticmethod
    def _validate_region(region: str) -> str:
        if region not in _VALID_REGIONS:
            raise ValueError(f"Invalid region: {region}")
        return region

    @staticmethod
    def _resolve_user_data(options: DeckRecommendOptions) -> DeckRecommendUserData:
        user_data = options.user_data
        if user_data is None and options.user_data_file_path:
            user_data = DeckRecommendUserData()
            user_data.load_from_file(options.user_data_file_path)
        if user_data is None and options.user_data_str is not None:
            user_data = DeckRecommendUserData()
            user_data.load_from_bytes(options.user_data_str)
        if not isinstance(user_data, DeckRecommendUserData) or user_data._native is None:
            raise ValueError(
                "Either user_data / user_data_file_path / user_data_str is required."
            )
        return user_data

    @classmethod
    def _validate_options(cls, options: DeckRecommendOptions) -> str:
        if not isinstance(options, DeckRecommendOptions):
            raise TypeError("options must be DeckRecommendOptions")
        if options.region is None:
            raise ValueError("region is required.")
        return cls._validate_region(options.region)

    def update_masterdata(self, base_dir: str, region: str) -> None:
        self._require_native().update_masterdata(
            str(Path(base_dir)), self._validate_region(region)
        )

    def update_masterdata_from_strings(self, data, region: str) -> None:
        if not isinstance(data, dict):
            raise TypeError("data must be a dict")
        normalized = {
            (name if str(name).endswith(".json") else f"{name}.json"): (
                value.decode("utf-8") if isinstance(value, bytes) else str(value)
            )
            for name, value in data.items()
        }
        self._require_native().update_masterdata_from_strings(
            normalized, self._validate_region(region)
        )

    def update_musicmetas(self, path: str, region: str) -> None:
        self._require_native().update_musicmetas(
            Path(path).read_text("utf-8"), self._validate_region(region)
        )

    def update_musicmetas_from_string(self, data, region: str) -> None:
        text = data.decode("utf-8") if isinstance(data, bytes) else str(data)
        self._require_native().update_musicmetas(text, self._validate_region(region))

    def recommend(self, options: DeckRecommendOptions) -> DeckRecommendResult:
        region = self._validate_options(options)
        user_data = self._resolve_user_data(options)
        payload = self._require_native().recommend(
            region,
            json.dumps(options._to_native_dict(), separators=(",", ":")),
            user_data._native,
        )
        return DeckRecommendResult.from_dict(json.loads(payload))

    def recommend_batch(
        self, options_list: list[DeckRecommendOptions]
    ) -> list[DeckRecommendResult]:
        options_list = _native_sequence(options_list, "options_list")
        for index, options in enumerate(options_list):
            if not isinstance(options, DeckRecommendOptions):
                raise TypeError(f"batch item {index}: expected DeckRecommendOptions")
        workers = min(_effective_engine_thread_count(), max(1, len(options_list)))
        if workers <= 1 or len(options_list) <= 1:
            result = []
            for index, options in enumerate(options_list):
                try:
                    result.append(self.recommend(options))
                except Exception as error:
                    _raise_batch_error(index, error)
            return result
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(self.recommend, options) for options in options_list]
            result = []
            for index, future in enumerate(futures):
                try:
                    result.append(future.result())
                except Exception as error:
                    _raise_batch_error(index, error)
            return result

    def get_world_bloom_support_cards(
        self, options: DeckRecommendOptions
    ) -> list[RecommendSupportDeckCard]:
        region = self._validate_options(options)
        user_data = self._resolve_user_data(options)
        payload = self._require_native().get_world_bloom_support_cards(
            region,
            json.dumps(options._to_native_dict(), separators=(",", ":")),
            user_data._native,
        )
        return [RecommendSupportDeckCard.from_dict(item) for item in json.loads(payload)]

    def recommend_area_items(
        self, options: DeckRecommendOptions, card_ids: list[int]
    ) -> list[dict]:
        region = self._validate_options(options)
        user_data = self._resolve_user_data(options)
        card_ids = _native_sequence(card_ids, "card_ids")
        if not 1 <= len(card_ids) <= 5:
            raise ValueError("cardIds must contain 1 to 5 cards")
        payload = self._require_native().recommend_area_items(
            region, card_ids, user_data._native
        )
        return json.loads(payload)

    def recommend_music(
        self, options: DeckRecommendOptions, deck: RecommendDeck
    ) -> list[dict]:
        region = self._validate_options(options)
        if not isinstance(deck, RecommendDeck):
            raise TypeError("deck must be RecommendDeck")
        payload = self._require_native().recommend_music(
            region,
            json.dumps(options._to_native_dict(), separators=(",", ":")),
            json.dumps(deck.to_dict(), separators=(",", ":")),
        )
        return json.loads(payload)

    def calculate_exact_live(
        self,
        region: str,
        power: int,
        skills: list[float],
        live_type: str,
        music_score_json: str,
        multi_sum_power: int = 0,
        fever_music_score_json: str | None = None,
    ) -> dict:
        skills = _native_sequence(skills, "skills")
        if live_type not in _VALID_LIVE_TYPES or live_type == "mysekai":
            raise ValueError(f"Invalid live type: {live_type}")
        payload = self._require_native().calculate_exact_live(
            self._validate_region(region),
            power,
            skills,
            live_type,
            music_score_json,
            multi_sum_power,
            fever_music_score_json,
        )
        return json.loads(payload)


__all__ = [
    "DeckRecommendCardConfig",
    "DeckRecommendGaOptions",
    "DeckRecommendOptions",
    "DeckRecommendResult",
    "DeckRecommendSaOptions",
    "DeckRecommendSingleCardConfig",
    "DeckRecommendUserData",
    "RecommendCard",
    "RecommendDeck",
    "RecommendSupportDeckCard",
    "SekaiDeckRecommend",
    "set_engine_thread_count",
]
