from __future__ import annotations

import json
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

    def update_masterdata(self, base_dir: str, region: str) -> None:
        self._require_native().update_masterdata(str(Path(base_dir)), region)

    def update_masterdata_from_strings(self, data, region: str) -> None:
        normalized = {
            (name if str(name).endswith(".json") else f"{name}.json"): (
                value.decode("utf-8") if isinstance(value, bytes) else str(value)
            )
            for name, value in data.items()
        }
        self._require_native().update_masterdata_from_strings(normalized, region)

    def update_musicmetas(self, path: str, region: str) -> None:
        self._require_native().update_musicmetas(Path(path).read_text("utf-8"), region)

    def update_musicmetas_from_string(self, data, region: str) -> None:
        text = data.decode("utf-8") if isinstance(data, bytes) else str(data)
        self._require_native().update_musicmetas(text, region)

    def recommend(self, options: DeckRecommendOptions) -> DeckRecommendResult:
        if not isinstance(options, DeckRecommendOptions):
            raise TypeError("options must be DeckRecommendOptions")
        user_data = options.user_data
        if user_data is None and options.user_data_file_path:
            user_data = DeckRecommendUserData()
            user_data.load_from_file(options.user_data_file_path)
        if user_data is None and options.user_data_str is not None:
            user_data = DeckRecommendUserData()
            user_data.load_from_bytes(options.user_data_str)
        if not isinstance(user_data, DeckRecommendUserData) or user_data._native is None:
            raise ValueError("options.user_data is required")
        payload = self._require_native().recommend(
            options.region,
            json.dumps(options.to_native_dict(), separators=(",", ":")),
            user_data._native,
        )
        return DeckRecommendResult.from_dict(json.loads(payload))

    def recommend_area_items(self, *args, **kwargs):
        raise NotImplementedError("recommend_area_items is not available in 0.0.1")

    def recommend_music(self, *args, **kwargs):
        raise NotImplementedError("recommend_music is not available in 0.0.1")

    def calculate_exact_live(self, *args, **kwargs):
        raise NotImplementedError("calculate_exact_live is not available in 0.0.1")


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
]
