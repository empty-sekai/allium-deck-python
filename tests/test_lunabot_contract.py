import pytest
import sekai_deck_recommend_cpp as api

from sekai_deck_recommend_cpp import (
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
    SekaiDeckRecommend,
)


def test_lunabot_import_surface_is_available():
    assert SekaiDeckRecommend is not None
    assert DeckRecommendUserData is not None


def test_public_module_exports_the_complete_deck_api():
    assert set(api.__all__) == {
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
    }


def test_mutable_config_roundtrip_omits_unset_fields_and_rejects_unknown_fields():
    config = DeckRecommendCardConfig()
    assert config.disable is None
    assert config.to_dict() == {}
    config.level_max = True
    with pytest.raises(AttributeError):
        config.future_option = 17

    restored = DeckRecommendCardConfig.from_dict(config.to_dict())
    assert restored.level_max is True


def test_options_copy_constructor_is_independent_and_preserves_nested_types():
    options = DeckRecommendOptions()
    options.algorithm = "ga"
    options.region = "cn"
    options.member = 5
    options.rarity_4_config = DeckRecommendCardConfig.from_dict({"level_max": True})
    options.single_card_configs = [
        DeckRecommendSingleCardConfig.from_dict({"card_id": 123, "skill_max": True})
    ]
    options.ga_options = DeckRecommendGaOptions.from_dict({"pop_size": 100})
    options.sa_options = DeckRecommendSaOptions.from_dict({"run_num": 3})

    copied = DeckRecommendOptions(options)
    copied.rarity_4_config.level_max = False
    copied.single_card_configs[0].skill_max = False

    assert options.rarity_4_config.level_max is True
    assert options.single_card_configs[0].skill_max is True
    assert copied.ga_options.pop_size == 100
    assert copied.sa_options.run_num == 3


@pytest.mark.parametrize("member", [None, 5])
def test_only_five_member_compat_values_are_accepted(member):
    options = DeckRecommendOptions()
    options.member = member
    assert options._to_native_dict().get("member") in (None, 5)


def test_native_payload_omits_unset_optional_fields():
    payload = DeckRecommendOptions()._to_native_dict()
    assert "timeout_ms" not in payload
    assert "target_bonus_list" not in payload
    assert "custom_bonus_character_ids" not in payload
    assert "custom_bonus_character_support_units" not in payload


def test_native_payload_maps_lunabot_constraints_to_rust_keys():
    options = DeckRecommendOptions.from_dict(
        {
            "fixed_cards": [1],
            "fixed_characters": [2],
            "filter_other_unit": True,
            "keep_after_training_state": True,
            "best_skill_as_leader": False,
            "skill_reference_choose_strategy": "max",
            "skill_order_choose_strategy": "average",
            "multi_live_teammate_score_up": 200,
            "multi_live_teammate_power": 250000,
        }
    )

    payload = options._to_native_dict()
    assert payload["fixedCards"] == [1]
    assert payload["fixedCharacters"] == [2]
    assert payload["filterOtherUnit"] is True
    assert payload["keepAfterTrainingState"] is True
    assert payload["bestSkillAsLeader"] is False
    assert payload["skillReferenceChooseStrategy"] == "max"
    assert payload["skillOrderChooseStrategy"] == "average"
    assert payload["multiLiveTeammateScoreUp"] == 200
    assert payload["multiLiveTeammatePower"] == 250000
    assert "fixed_cards" not in payload
    assert "multi_live_teammate_power" not in payload


@pytest.mark.parametrize("member", [0, 1, 4, 6])
def test_other_member_counts_are_rejected_before_native(member):
    options = DeckRecommendOptions()
    options.member = member
    with pytest.raises(ValueError, match="5"):
        options._to_native_dict()


@pytest.mark.parametrize("algorithm", ["dfs", "ga", "dfs_ga", "rl", "sa"])
def test_legacy_algorithm_names_normalize_to_dfs(algorithm):
    options = DeckRecommendOptions()
    options.algorithm = algorithm
    assert options._to_native_dict()["algorithm"] == "dfs"


def test_unknown_algorithm_is_rejected():
    options = DeckRecommendOptions()
    options.algorithm = "typo"
    with pytest.raises(ValueError, match="algorithm"):
        options._to_native_dict()


def test_result_objects_roundtrip_and_remain_mutable():
    card = RecommendCard().to_dict()
    card.update(
        {
            "card_id": 123,
            "event_bonus_rate": 70.0,
            "skill_level": 4,
            "skill_score_up": 100,
            "default_image": "special_training",
        }
    )
    deck = RecommendDeck().to_dict()
    deck.update(
        {
            "score": 1000,
            "live_score": 900,
            "event_bonus_rate": 250.0,
            "support_deck_bonus_rate": 12.5,
            "cards": [card],
            "support_deck_cards": [
                {"card_id": 456, "bonus": 5.5, "skill_level": 4}
            ],
        }
    )
    result = DeckRecommendResult.from_dict(
        {
            "cost_ms": 1.25,
            "decks": [deck],
        }
    )

    assert isinstance(result.decks[0], RecommendDeck)
    assert isinstance(result.decks[0].cards[0], RecommendCard)
    assert isinstance(result.decks[0].support_deck_cards[0], RecommendSupportDeckCard)
    result.decks = list(result.decks)
    assert DeckRecommendResult.from_dict(result.to_dict()).to_dict() == result.to_dict()


def test_options_defaults_copy_and_serialization_boundary():
    options = DeckRecommendOptions()
    assert options.to_dict() == {}
    assert options.target is None
    assert options.algorithm is None
    assert options.region is None

    copied = DeckRecommendOptions(options)
    assert copied.to_dict() == {}

    options.user_data = DeckRecommendUserData()
    with pytest.raises(RuntimeError, match="user_data"):
        options.to_dict()


def test_required_result_fields_are_enforced():
    with pytest.raises(KeyError, match="card_id"):
        RecommendCard.from_dict({})
    with pytest.raises(KeyError, match="score"):
        RecommendDeck.from_dict({})
    with pytest.raises(KeyError, match="decks"):
        DeckRecommendResult.from_dict({})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("event_id", 1.5),
        ("event_id", "1"),
        ("region", 1),
        ("support_master_max", "true"),
        ("fixed_cards", "1,2"),
        ("custom_bonus_character_support_units", {"1": "idol"}),
    ],
)
def test_option_properties_reject_values_the_native_contract_cannot_convert(field, value):
    options = DeckRecommendOptions()
    with pytest.raises(TypeError):
        setattr(options, field, value)


def test_option_properties_apply_native_compatible_conversions():
    options = DeckRecommendOptions()
    options.region = b"cn"
    options.support_master_max = 1
    options.fixed_cards = (1, 2)
    assert options.region == "cn"
    assert options.support_master_max is True
    assert options.fixed_cards == [1, 2]


def test_result_cost_is_non_negative_and_roundtrips():
    result = DeckRecommendResult.from_dict({"decks": [], "cost_ms": 0.125})
    assert result.cost_ms >= 0
    assert result.to_dict()["cost_ms"] == 0.125


@pytest.mark.parametrize(
    ("model", "field"),
    [
        (DeckRecommendCardConfig, "level_max"),
        (DeckRecommendSingleCardConfig, "card_id"),
        (DeckRecommendGaOptions, "pop_size"),
        (DeckRecommendSaOptions, "run_num"),
        (DeckRecommendOptions, "region"),
    ],
)
def test_from_dict_rejects_explicit_none_for_known_fields(model, field):
    with pytest.raises(TypeError):
        model.from_dict({field: None})


def test_options_from_dict_ignores_user_data_like_the_native_contract():
    user = DeckRecommendUserData()
    options = DeckRecommendOptions.from_dict({"user_data": user, "region": "cn"})
    assert options.region == "cn"
    assert options.user_data is None


def test_internal_payload_conversion_is_not_part_of_the_public_surface():
    assert "to_native_dict" not in dir(DeckRecommendOptions())


def test_user_data_loaders_preserve_public_exception_boundaries(tmp_path):
    user = DeckRecommendUserData()

    with pytest.raises(RuntimeError):
        user.load_from_bytes("{")
    with pytest.raises(TypeError):
        user.load_from_bytes(1)
    with pytest.raises(TypeError):
        user.load_from_bytes(memoryview(b"{}"))
    with pytest.raises(RuntimeError):
        user.load_from_file(str(tmp_path / "missing.json"))
    with pytest.raises(TypeError):
        user.load_from_file(tmp_path / "missing.json")
