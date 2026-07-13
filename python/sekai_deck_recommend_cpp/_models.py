from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any, ClassVar


def _safe_copy(value: Any) -> Any:
    try:
        return deepcopy(value)
    except (TypeError, ValueError):
        return value


def _drop_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _drop_none(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [_drop_none(item) for item in value]
    return value


class _CompatModel:
    _defaults: ClassVar[dict[str, Any]] = {}
    _nested: ClassVar[dict[str, tuple[type, bool]]] = {}

    def __init__(self, source: Any = None, **values: Any) -> None:
        for name, default in self._defaults.items():
            setattr(self, name, deepcopy(default))
        if source is not None:
            if isinstance(source, _CompatModel):
                self._load_dict(source.to_dict())
            elif isinstance(source, dict):
                self._load_dict(source)
            else:
                raise TypeError(f"expected {type(self).__name__} or dict")
        self._load_dict(values)

    def _load_dict(self, data: dict[str, Any]) -> None:
        for name, value in data.items():
            nested = self._nested.get(name)
            if nested is not None and value is not None:
                model, many = nested
                if many:
                    value = [item if isinstance(item, model) else model.from_dict(item) for item in value]
                elif not isinstance(value, model):
                    value = model.from_dict(value)
            setattr(self, name, _safe_copy(value))

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name, value in vars(self).items():
            if name.startswith("_"):
                continue
            if isinstance(value, _CompatModel):
                result[name] = value.to_dict()
            elif isinstance(value, list):
                result[name] = [item.to_dict() if isinstance(item, _CompatModel) else _safe_copy(item) for item in value]
            else:
                result[name] = _safe_copy(value)
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]):
        if not isinstance(data, dict):
            raise TypeError("data must be a dict")
        return cls(data)


_CARD_CONFIG_DEFAULTS = {
    "disable": None,
    "level_max": None,
    "episode_read": None,
    "master_max": None,
    "skill_max": None,
    "canvas": None,
    "level": None,
    "skill_level": None,
    "master_rank": None,
    "episode_read_count": None,
}


class DeckRecommendCardConfig(_CompatModel):
    _defaults = _CARD_CONFIG_DEFAULTS


class DeckRecommendSingleCardConfig(_CompatModel):
    _defaults = {"card_id": 0, **_CARD_CONFIG_DEFAULTS}


class DeckRecommendSaOptions(_CompatModel):
    _defaults = {
        "run_num": None,
        "seed": None,
        "max_iter": None,
        "max_no_improve_iter": None,
        "time_limit_ms": None,
        "start_temprature": None,
        "cooling_rate": None,
        "debug": None,
    }


class DeckRecommendGaOptions(_CompatModel):
    _defaults = {
        "seed": None,
        "debug": None,
        "max_iter": None,
        "max_no_improve_iter": None,
        "pop_size": None,
        "parent_size": None,
        "elite_size": None,
        "crossover_rate": None,
        "base_mutation_rate": None,
        "no_improve_iter_to_mutation_rate": None,
    }


class DeckRecommendOptions(_CompatModel):
    _defaults = {
        "target": "score",
        "algorithm": "dfs",
        "region": "jp",
        "user_data": None,
        "user_data_file_path": None,
        "user_data_str": None,
        "live_type": "solo",
        "music_id": None,
        "music_diff": "master",
        "event_id": None,
        "event_attr": None,
        "event_unit": None,
        "event_type": None,
        "world_bloom_event_turn": None,
        "world_bloom_character_id": None,
        "challenge_live_character_id": None,
        "limit": 10,
        "member": None,
        "timeout_ms": None,
        "rarity_1_config": None,
        "rarity_2_config": None,
        "rarity_3_config": None,
        "rarity_birthday_config": None,
        "rarity_4_config": None,
        "single_card_configs": None,
        "support_master_max": None,
        "support_skill_max": None,
        "filter_other_unit": None,
        "fixed_cards": None,
        "fixed_characters": None,
        "forcedLeaderCharacterId": None,
        "target_bonus_list": None,
        "custom_bonus_character_ids": None,
        "custom_bonus_attr": None,
        "custom_bonus_character_support_units": None,
        "skill_reference_choose_strategy": None,
        "keep_after_training_state": None,
        "multi_live_teammate_score_up": None,
        "multi_live_teammate_power": None,
        "best_skill_as_leader": None,
        "multi_live_score_up_lower_bound": None,
        "skill_order_choose_strategy": None,
        "specific_skill_order": None,
        "sa_options": None,
        "ga_options": None,
    }
    _nested = {
        "rarity_1_config": (DeckRecommendCardConfig, False),
        "rarity_2_config": (DeckRecommendCardConfig, False),
        "rarity_3_config": (DeckRecommendCardConfig, False),
        "rarity_birthday_config": (DeckRecommendCardConfig, False),
        "rarity_4_config": (DeckRecommendCardConfig, False),
        "single_card_configs": (DeckRecommendSingleCardConfig, True),
        "sa_options": (DeckRecommendSaOptions, False),
        "ga_options": (DeckRecommendGaOptions, False),
    }

    def to_native_dict(self) -> dict[str, Any]:
        if self.member not in (None, 5):
            raise ValueError("allium-deck only supports 5-member decks")
        result = _drop_none(self.to_dict())
        result["algorithm"] = "dfs"
        result.pop("user_data", None)
        return result


class RecommendCard(_CompatModel):
    _defaults = {
        "card_id": 0,
        "total_power": 0,
        "base_power": 0,
        "event_bonus_rate": 0.0,
        "master_rank": 0,
        "level": 0,
        "skill_level": 0,
        "skill_score_up": 0.0,
        "skill_life_recovery": 0.0,
        "episode1_read": None,
        "episode2_read": None,
        "after_training": False,
        "default_image": "original",
        "has_canvas_bonus": False,
    }


class RecommendSupportDeckCard(_CompatModel):
    _defaults = {
        "card_id": 0,
        "bonus": 0.0,
        "skill_level": 0,
        "master_rank": 0,
        "level": 0,
        "after_training": False,
        "default_image": "original",
    }


class RecommendDeck(_CompatModel):
    _defaults = {
        "score": 0,
        "live_score": 0,
        "mysekai_event_point": 0,
        "total_power": 0,
        "base_power": 0,
        "area_item_bonus_power": 0,
        "character_bonus_power": 0,
        "honor_bonus_power": 0,
        "fixture_bonus_power": 0,
        "gate_bonus_power": 0,
        "event_bonus_rate": 0.0,
        "support_deck_bonus_rate": 0.0,
        "multi_live_score_up": 0.0,
        "support_deck_cards": [],
        "cards": [],
    }
    _nested = {
        "cards": (RecommendCard, True),
        "support_deck_cards": (RecommendSupportDeckCard, True),
    }


class DeckRecommendResult(_CompatModel):
    _defaults = {"decks": [], "cost_ms": 0.0}
    _nested = {"decks": (RecommendDeck, True)}


class DeckRecommendUserData:
    def __init__(self) -> None:
        self._raw: bytes | None = None
        self._native = None

    def load_from_file(self, path: str) -> None:
        self.load_from_bytes(Path(path).read_bytes())

    def load_from_bytes(self, data: str | bytes) -> None:
        raw = data.encode("utf-8") if isinstance(data, str) else bytes(data)
        json.loads(raw)
        self._raw = raw
        try:
            from _allium_deck_native import NativeUserData
        except ImportError:
            self._native = None
        else:
            self._native = NativeUserData(raw)


__all__ = [name for name in globals() if name.startswith("DeckRecommend") or name.startswith("Recommend")]
