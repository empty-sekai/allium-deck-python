import pytest

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


def test_mutable_config_roundtrip_and_unknown_fields():
    config = DeckRecommendCardConfig()
    assert config.disable is None
    config.level_max = True
    config.future_option = 17

    restored = DeckRecommendCardConfig.from_dict(config.to_dict())
    assert restored.level_max is True
    assert restored.future_option == 17


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
    assert options.to_native_dict().get("member") in (None, 5)


def test_native_payload_omits_unset_optional_fields():
    payload = DeckRecommendOptions().to_native_dict()
    assert "timeout_ms" not in payload
    assert "target_bonus_list" not in payload
    assert "custom_bonus_character_ids" not in payload
    assert "custom_bonus_character_support_units" not in payload


@pytest.mark.parametrize("member", [0, 1, 4, 6])
def test_other_member_counts_are_rejected_before_native(member):
    options = DeckRecommendOptions()
    options.member = member
    with pytest.raises(ValueError, match="5"):
        options.to_native_dict()


@pytest.mark.parametrize("algorithm", ["dfs", "ga", "dfs_ga", "rl", "sa"])
def test_legacy_algorithm_names_normalize_to_dfs(algorithm):
    options = DeckRecommendOptions()
    options.algorithm = algorithm
    assert options.to_native_dict()["algorithm"] == "dfs"


def test_result_objects_roundtrip_and_remain_mutable():
    result = DeckRecommendResult.from_dict(
        {
            "cost_ms": 1.25,
            "decks": [
                {
                    "score": 1000,
                    "live_score": 900,
                    "event_bonus_rate": 250.0,
                    "support_deck_bonus_rate": 12.5,
                    "cards": [
                        {
                            "card_id": 123,
                            "event_bonus_rate": 70.0,
                            "skill_level": 4,
                            "skill_score_up": 100.0,
                            "default_image": "special_training",
                        }
                    ],
                    "support_deck_cards": [
                        {"card_id": 456, "bonus": 5.5, "skill_level": 4}
                    ],
                }
            ],
        }
    )

    assert isinstance(result.decks[0], RecommendDeck)
    assert isinstance(result.decks[0].cards[0], RecommendCard)
    assert isinstance(result.decks[0].support_deck_cards[0], RecommendSupportDeckCard)
    result.decks = list(result.decks)
    assert DeckRecommendResult.from_dict(result.to_dict()).to_dict() == result.to_dict()
