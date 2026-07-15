from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any, ClassVar


class _CompatModel:
    __slots__ = ()

    _defaults: ClassVar[dict[str, Any]] = {}
    _nested: ClassVar[dict[str, tuple[type, bool]]] = {}
    _omit_none: ClassVar[bool] = False
    _required: ClassVar[tuple[str, ...]] = ()
    _field_kinds: ClassVar[dict[str, Any]] = {}
    _reject_none_from_dict: ClassVar[bool] = False
    _from_dict_ignored: ClassVar[tuple[str, ...]] = ()

    def __setattr__(self, name: str, value: Any) -> None:
        kind = self._field_kinds.get(name)
        if kind is not None:
            value = _convert_field(name, value, kind)
        object.__setattr__(self, name, value)

    def __init__(self, source: Any = None) -> None:
        for name, default in self._defaults.items():
            setattr(self, name, deepcopy(default))
        if source is not None:
            if type(source) is not type(self):
                raise TypeError(f"expected {type(self).__name__}")
            self._load_dict(source._as_dict(include_user_data=True))

    def _load_dict(self, data: dict[str, Any]) -> None:
        for name in self._defaults:
            if name not in data:
                continue
            value = data[name]
            nested = self._nested.get(name)
            if nested is not None and value is not None:
                model, many = nested
                if many:
                    value = [
                        item if isinstance(item, model) else model.from_dict(item)
                        for item in value
                    ]
                elif not isinstance(value, model):
                    value = model.from_dict(value)
            setattr(self, name, value if name == "user_data" else deepcopy(value))

    def _as_dict(self, *, include_user_data: bool = False) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name in self._defaults:
            if name == "user_data" and not include_user_data:
                continue
            value = getattr(self, name)
            if self._omit_none and value is None:
                continue
            if isinstance(value, _CompatModel):
                value = value.to_dict()
            elif isinstance(value, list):
                value = [
                    item.to_dict() if isinstance(item, _CompatModel) else deepcopy(item)
                    for item in value
                ]
            elif name != "user_data":
                value = deepcopy(value)
            result[name] = value
        return result

    def to_dict(self) -> dict[str, Any]:
        return self._as_dict()

    @classmethod
    def from_dict(cls, data: dict[str, Any]):
        if not isinstance(data, dict):
            raise TypeError("data must be a dict")
        for name in cls._required:
            if name not in data:
                raise KeyError(name)
        instance = cls()
        filtered = {key: value for key, value in data.items() if key not in cls._from_dict_ignored}
        if cls._reject_none_from_dict:
            for name, value in filtered.items():
                if name in cls._field_kinds and value is None:
                    raise TypeError(f"{name} cannot be None in from_dict")
        instance._load_dict(filtered)
        return instance


def _conversion_error(name: str, expected: str, value: Any) -> TypeError:
    return TypeError(
        f"incompatible value for {name}: expected {expected}, got {type(value).__name__}"
    )


def _convert_field(name: str, value: Any, kind: Any) -> Any:
    optional = isinstance(kind, tuple) and kind[0] == "optional"
    if optional:
        if value is None:
            return None
        kind = kind[1]

    if kind == "bool":
        if not isinstance(value, (bool, int)):
            raise _conversion_error(name, "bool", value)
        return bool(value)
    if kind == "int":
        if not isinstance(value, int):
            raise _conversion_error(name, "int", value)
        return int(value)
    if kind == "float":
        if not isinstance(value, (int, float)):
            raise _conversion_error(name, "float", value)
        return float(value)
    if kind == "str":
        if isinstance(value, bytes):
            return value.decode("utf-8")
        if not isinstance(value, str):
            raise _conversion_error(name, "str", value)
        return value
    if isinstance(kind, tuple) and kind[0] == "model":
        model = globals()[kind[1]]
        if not isinstance(value, model):
            raise _conversion_error(name, kind[1], value)
        return value
    if isinstance(kind, tuple) and kind[0] == "list":
        if not isinstance(value, (list, tuple)):
            raise _conversion_error(name, "list", value)
        item_kind = kind[1]
        return [_convert_field(name, item, item_kind) for item in value]
    if kind == "int_str_dict":
        if not isinstance(value, dict):
            raise _conversion_error(name, "dict[int, str]", value)
        return {
            _convert_field(name, key, "int"): _convert_field(name, item, "str")
            for key, item in value.items()
        }
    raise RuntimeError(f"unknown field conversion: {kind!r}")


def _optional(kind: Any) -> tuple[str, Any]:
    return ("optional", kind)


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
    __slots__ = tuple(_CARD_CONFIG_DEFAULTS)
    _defaults = _CARD_CONFIG_DEFAULTS
    _omit_none = True
    _reject_none_from_dict = True
    _field_kinds = {
        **{name: _optional("bool") for name in (
            "disable", "level_max", "episode_read", "master_max", "skill_max", "canvas"
        )},
        **{name: _optional("int") for name in (
            "level", "skill_level", "master_rank", "episode_read_count"
        )},
    }


class DeckRecommendSingleCardConfig(_CompatModel):
    __slots__ = ("card_id", *tuple(_CARD_CONFIG_DEFAULTS))
    _defaults = {"card_id": 0, **_CARD_CONFIG_DEFAULTS}
    _omit_none = True
    _required = ("card_id",)
    _reject_none_from_dict = True
    _field_kinds = {"card_id": "int", **DeckRecommendCardConfig._field_kinds}


class DeckRecommendSaOptions(_CompatModel):
    __slots__ = (
        "run_num",
        "seed",
        "max_iter",
        "max_no_improve_iter",
        "time_limit_ms",
        "start_temprature",
        "cooling_rate",
        "debug",
    )
    _defaults = dict.fromkeys(__slots__)
    _omit_none = True
    _reject_none_from_dict = True
    _field_kinds = {
        **{name: _optional("int") for name in (
            "run_num", "seed", "max_iter", "max_no_improve_iter", "time_limit_ms"
        )},
        **{name: _optional("float") for name in ("start_temprature", "cooling_rate")},
        "debug": _optional("bool"),
    }


class DeckRecommendGaOptions(_CompatModel):
    __slots__ = (
        "seed",
        "debug",
        "max_iter",
        "max_no_improve_iter",
        "pop_size",
        "parent_size",
        "elite_size",
        "crossover_rate",
        "base_mutation_rate",
        "no_improve_iter_to_mutation_rate",
    )
    _defaults = dict.fromkeys(__slots__)
    _omit_none = True
    _reject_none_from_dict = True
    _field_kinds = {
        **{name: _optional("int") for name in (
            "seed", "max_iter", "max_no_improve_iter", "pop_size", "parent_size", "elite_size"
        )},
        **{name: _optional("float") for name in (
            "crossover_rate", "base_mutation_rate", "no_improve_iter_to_mutation_rate"
        )},
        "debug": _optional("bool"),
    }


class DeckRecommendOptions(_CompatModel):
    __slots__ = (
        "target",
        "algorithm",
        "region",
        "user_data",
        "user_data_file_path",
        "user_data_str",
        "live_type",
        "music_id",
        "music_diff",
        "event_id",
        "event_attr",
        "event_unit",
        "event_type",
        "world_bloom_event_turn",
        "world_bloom_character_id",
        "challenge_live_character_id",
        "limit",
        "member",
        "timeout_ms",
        "rarity_1_config",
        "rarity_2_config",
        "rarity_3_config",
        "rarity_birthday_config",
        "rarity_4_config",
        "single_card_configs",
        "support_master_max",
        "support_skill_max",
        "filter_other_unit",
        "fixed_cards",
        "fixed_characters",
        "forcedLeaderCharacterId",
        "target_bonus_list",
        "custom_bonus_character_ids",
        "custom_bonus_attr",
        "custom_bonus_character_support_units",
        "skill_reference_choose_strategy",
        "keep_after_training_state",
        "multi_live_teammate_score_up",
        "multi_live_teammate_power",
        "best_skill_as_leader",
        "multi_live_score_up_lower_bound",
        "skill_order_choose_strategy",
        "specific_skill_order",
        "sa_options",
        "ga_options",
    )
    _defaults = dict.fromkeys(__slots__)
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
    _omit_none = True
    _native_key_aliases = {
        "fixed_cards": "fixedCards",
        "fixed_characters": "fixedCharacters",
        "filter_other_unit": "filterOtherUnit",
        "keep_after_training_state": "keepAfterTrainingState",
        "best_skill_as_leader": "bestSkillAsLeader",
        "skill_reference_choose_strategy": "skillReferenceChooseStrategy",
        "skill_order_choose_strategy": "skillOrderChooseStrategy",
        "multi_live_teammate_score_up": "multiLiveTeammateScoreUp",
        "multi_live_teammate_power": "multiLiveTeammatePower",
    }
    _algorithm_aliases = {"dfs", "ga", "dfs_ga", "rl", "sa"}
    _reject_none_from_dict = True
    _from_dict_ignored = ("user_data",)
    _field_kinds = {
        **{name: _optional("str") for name in (
            "target", "algorithm", "region", "user_data_file_path", "user_data_str",
            "live_type", "music_diff", "event_attr", "event_unit", "event_type",
            "custom_bonus_attr", "skill_reference_choose_strategy", "skill_order_choose_strategy",
        )},
        **{name: _optional("int") for name in (
            "music_id", "event_id", "world_bloom_event_turn", "world_bloom_character_id",
            "challenge_live_character_id", "limit", "member", "timeout_ms",
            "forcedLeaderCharacterId", "multi_live_teammate_score_up", "multi_live_teammate_power",
        )},
        **{name: _optional("bool") for name in (
            "support_master_max", "support_skill_max", "filter_other_unit",
            "keep_after_training_state", "best_skill_as_leader",
        )},
        "multi_live_score_up_lower_bound": _optional("float"),
        "user_data": _optional(("model", "DeckRecommendUserData")),
        **{name: _optional(("model", "DeckRecommendCardConfig")) for name in (
            "rarity_1_config", "rarity_2_config", "rarity_3_config",
            "rarity_birthday_config", "rarity_4_config",
        )},
        "single_card_configs": _optional(("list", ("model", "DeckRecommendSingleCardConfig"))),
        **{name: _optional(("list", "int")) for name in (
            "fixed_cards", "fixed_characters", "target_bonus_list",
            "custom_bonus_character_ids", "specific_skill_order",
        )},
        "custom_bonus_character_support_units": _optional("int_str_dict"),
        "sa_options": _optional(("model", "DeckRecommendSaOptions")),
        "ga_options": _optional(("model", "DeckRecommendGaOptions")),
    }

    def to_dict(self) -> dict[str, Any]:
        if self.user_data is not None:
            raise RuntimeError("Cannot be converted to dict when user_data is set.")
        return self._as_dict()

    def _to_native_dict(self) -> dict[str, Any]:
        if self.member not in (None, 5):
            raise ValueError("allium-deck only supports 5-member decks")
        algorithm = "ga" if self.algorithm is None else str(self.algorithm).strip().lower()
        if algorithm not in self._algorithm_aliases:
            raise ValueError(f"unsupported algorithm: {self.algorithm}")
        result = self._as_dict(include_user_data=False)
        for source, target in self._native_key_aliases.items():
            if source in result:
                result[target] = result.pop(source)
        result["algorithm"] = "dfs"
        result.setdefault("skillOrderChooseStrategy", "average")
        if "event_id" not in result and self.live_type not in ("challenge", "challenge_auto"):
            result.setdefault("event_type", "marathon")
        return result


class RecommendCard(_CompatModel):
    __slots__ = (
        "card_id",
        "total_power",
        "base_power",
        "event_bonus_rate",
        "master_rank",
        "level",
        "skill_level",
        "skill_score_up",
        "skill_life_recovery",
        "episode1_read",
        "episode2_read",
        "after_training",
        "default_image",
        "has_canvas_bonus",
    )
    _defaults = {
        "card_id": 0,
        "total_power": 0,
        "base_power": 0,
        "event_bonus_rate": 0.0,
        "master_rank": 0,
        "level": 0,
        "skill_level": 0,
        "skill_score_up": 0,
        "skill_life_recovery": 0,
        "episode1_read": False,
        "episode2_read": False,
        "after_training": False,
        "default_image": "",
        "has_canvas_bonus": False,
    }
    _required = tuple(_defaults)
    _field_kinds = {
        **{name: "int" for name in (
            "card_id", "total_power", "base_power", "master_rank", "level", "skill_level",
            "skill_score_up", "skill_life_recovery",
        )},
        "event_bonus_rate": "float",
        **{name: "bool" for name in (
            "episode1_read", "episode2_read", "after_training", "has_canvas_bonus"
        )},
        "default_image": "str",
    }


class RecommendSupportDeckCard(_CompatModel):
    __slots__ = (
        "card_id",
        "bonus",
        "skill_level",
        "master_rank",
        "level",
        "after_training",
        "default_image",
    )
    _defaults = {
        "card_id": 0,
        "bonus": 0.0,
        "skill_level": 1,
        "master_rank": 0,
        "level": 1,
        "after_training": False,
        "default_image": "",
    }
    _required = ("card_id", "bonus")
    _field_kinds = {
        "card_id": "int",
        "bonus": "float",
        "skill_level": "int",
        "master_rank": "int",
        "level": "int",
        "after_training": "bool",
        "default_image": "str",
    }


class RecommendDeck(_CompatModel):
    __slots__ = (
        "score",
        "live_score",
        "mysekai_event_point",
        "total_power",
        "base_power",
        "area_item_bonus_power",
        "character_bonus_power",
        "honor_bonus_power",
        "fixture_bonus_power",
        "gate_bonus_power",
        "event_bonus_rate",
        "support_deck_bonus_rate",
        "multi_live_score_up",
        "support_deck_cards",
        "cards",
    )
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
    _required = (
        "score",
        "live_score",
        "mysekai_event_point",
        "total_power",
        "base_power",
        "area_item_bonus_power",
        "character_bonus_power",
        "honor_bonus_power",
        "fixture_bonus_power",
        "gate_bonus_power",
        "event_bonus_rate",
        "support_deck_bonus_rate",
        "multi_live_score_up",
        "cards",
    )
    _field_kinds = {
        **{name: "int" for name in (
            "score", "live_score", "mysekai_event_point", "total_power", "base_power",
            "area_item_bonus_power", "character_bonus_power", "honor_bonus_power",
            "fixture_bonus_power", "gate_bonus_power",
        )},
        **{name: "float" for name in (
            "event_bonus_rate", "support_deck_bonus_rate", "multi_live_score_up"
        )},
        "support_deck_cards": ("list", ("model", "RecommendSupportDeckCard")),
        "cards": ("list", ("model", "RecommendCard")),
    }


class DeckRecommendResult(_CompatModel):
    __slots__ = ("decks", "cost_ms")
    _defaults = {"decks": [], "cost_ms": 0.0}
    _nested = {"decks": (RecommendDeck, True)}
    _required = ("decks",)
    _field_kinds = {"decks": ("list", ("model", "RecommendDeck")), "cost_ms": "float"}


class DeckRecommendUserData:
    __slots__ = ("_raw", "_native")

    def __init__(self, source: DeckRecommendUserData | None = None) -> None:
        if source is not None and not isinstance(source, DeckRecommendUserData):
            raise TypeError("expected DeckRecommendUserData")
        self._raw = None if source is None else source._raw
        self._native = None if source is None else source._native

    def load_from_file(self, path: str) -> None:
        if not isinstance(path, str):
            raise TypeError("path must be a str")
        try:
            raw = Path(path).read_bytes()
        except OSError as error:
            raise RuntimeError(f"Failed to load user data from file: {path}") from error
        self.load_from_bytes(raw)

    def load_from_bytes(self, data: str | bytes) -> None:
        if isinstance(data, str):
            raw = data.encode("utf-8")
        elif isinstance(data, (bytes, bytearray)):
            raw = bytes(data)
        else:
            raise TypeError("data must be str or bytes")
        try:
            json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeError("Failed to load user data from bytes") from error
        self._raw = raw
        try:
            from _allium_deck_native import NativeUserData
        except ImportError:
            self._native = None
        else:
            try:
                self._native = NativeUserData(raw)
            except (TypeError, ValueError) as error:
                raise RuntimeError("Failed to load user data from bytes") from error


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
]
