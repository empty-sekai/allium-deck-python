import json
import os
from pathlib import Path

import pytest

from sekai_deck_recommend_cpp import (
    DeckRecommendOptions,
    DeckRecommendUserData,
    RecommendDeck,
    SekaiDeckRecommend,
    set_engine_thread_count,
)


def _fixture_paths():
    keys = ("ALLIUM_MASTERDATA", "ALLIUM_MUSIC_METAS", "ALLIUM_USER_DATA")
    if not all(os.environ.get(key) for key in keys):
        pytest.skip("native integration fixture paths are not configured")
    return tuple(Path(os.environ[key]) for key in keys)


def _ready_engine_and_options():
    masterdata, music_metas, user_path = _fixture_paths()
    engine = SekaiDeckRecommend()
    engine.update_masterdata(str(masterdata), "cn")
    engine.update_musicmetas(str(music_metas), "cn")
    user = DeckRecommendUserData()
    user.load_from_file(str(user_path))
    options = DeckRecommendOptions.from_dict(
        {
            "region": "cn",
            "algorithm": "dfs",
            "live_type": "multi",
            "event_id": 133,
            "music_id": 1,
            "music_diff": "master",
            "target": "score",
            "limit": 1,
        }
    )
    options.user_data = user
    return engine, options, masterdata, music_metas


def test_batch_support_area_and_music_methods_execute_with_loaded_data():
    engine, options, _, music_metas = _ready_engine_and_options()
    result = engine.recommend(options)
    assert result.cost_ms >= 0.0
    assert result.to_dict()["cost_ms"] == result.cost_ms
    deck = result.decks[0]

    set_engine_thread_count(2)
    batch = engine.recommend_batch([DeckRecommendOptions(options), DeckRecommendOptions(options)])
    assert len(batch) == 2
    assert all(item.cost_ms >= 0.0 for item in batch)
    assert [card.card_id for card in batch[0].decks[0].cards] == [
        card.card_id for card in batch[1].decks[0].cards
    ]

    support_options = DeckRecommendOptions(options)
    support_options.event_id = None
    support_options.world_bloom_event_turn = 1
    support_options.world_bloom_character_id = 1
    support = engine.get_world_bloom_support_cards(support_options)
    assert support
    assert all(
        (left.bonus, -left.card_id) >= (right.bonus, -right.card_id)
        for left, right in zip(support, support[1:])
    )

    card_ids = [card.card_id for card in deck.cards]
    area_items = engine.recommend_area_items(options, card_ids)
    assert all(
        {
            "area_id",
            "area_type",
            "area_view_type",
            "area_item_id",
            "next_level",
            "shop_item_id",
            "cost",
            "power",
            "power_per_coin",
        }
        <= item.keys()
        for item in area_items
    )

    music = engine.recommend_music(options, deck)
    expected_rows = len(json.loads(music_metas.read_text("utf-8")))
    assert len(music) == expected_rows
    assert all(item["event_point"] is not None for item in music)
    assert all(
        (left["event_point"], left["live_score"])
        >= (right["event_point"], right["live_score"])
        for left, right in zip(music, music[1:])
    )


def test_exact_live_returns_complete_note_details():
    engine, _, masterdata, _ = _ready_engine_and_options()
    notes = json.loads((masterdata / "ingameNotes.json").read_text("utf-8"))
    note_type = notes[0]["id"]
    score = json.dumps(
        {
            "notes": [
                {"time": 1.0, "type": note_type, "longId": 0},
                {"time": 7.0, "type": note_type, "longId": 0},
            ],
            "skills": [{"time": 1.0}],
            "fevers": [],
        }
    )
    detail = engine.calculate_exact_live(
        "cn", 100_000, [100.0], "multi", score, multi_sum_power=500_000
    )
    assert set(detail) == {"total", "active_bonus", "notes"}
    assert detail["active_bonus"] == pytest.approx(37_500.0)
    assert len(detail["notes"]) == 2
    assert set(detail["notes"][0]) == {
        "note_coefficient",
        "combo_coefficient",
        "judge_coefficient",
        "effect_bonuses",
        "score",
    }


def test_auxiliary_methods_validate_public_inputs():
    engine = SekaiDeckRecommend()
    options = DeckRecommendOptions()
    with pytest.raises(ValueError, match="region"):
        engine.recommend_music(options, RecommendDeck())
    with pytest.raises(ValueError, match="region"):
        engine.calculate_exact_live("invalid", 1, [], "solo", "{}")


def test_native_sequence_arguments_accept_sequence_and_set_inputs():
    engine, options, masterdata, _ = _ready_engine_and_options()
    result = engine.recommend(options)
    card_ids = [card.card_id for card in result.decks[0].cards]
    assert len(engine.recommend_batch((options,))) == 1
    assert engine.recommend_area_items(options, tuple(card_ids))

    notes = json.loads((masterdata / "ingameNotes.json").read_text("utf-8"))
    score = json.dumps(
        {
            "notes": [{"time": 1.0, "type": notes[0]["id"], "longId": 0}],
            "skills": [{"time": 1.0}],
            "fevers": [],
        }
    )
    assert engine.calculate_exact_live("cn", 100_000, (100.0,), "multi", score)
    with pytest.raises(TypeError):
        engine.calculate_exact_live("cn", 100_000, iter([100.0]), "multi", score)


def test_non_trainable_fixed_card_reports_original_training_state():
    engine, options, _, _ = _ready_engine_and_options()
    fixed = DeckRecommendOptions(options)
    fixed.fixed_cards = [1]
    card = next(card for card in engine.recommend(fixed).decks[0].cards if card.card_id == 1)
    assert card.after_training is False
    assert card.default_image == "original"


def test_skill_state_can_select_original_art_for_a_trained_card():
    engine, options, _, _ = _ready_engine_and_options()
    world_bloom = DeckRecommendOptions(options)
    world_bloom.event_id = 179
    world_bloom.world_bloom_character_id = 23
    world_bloom.fixed_cards = [617, 761, 798, 953, 1145]
    card = next(
        card
        for card in engine.recommend(world_bloom).decks[0].cards
        if card.card_id == 1145
    )
    assert card.after_training is True
    assert card.default_image == "original"


@pytest.mark.parametrize("target", ["score", "mysekai"])
def test_mysekai_result_fields_use_the_dedicated_event_point(target):
    engine, options, _, _ = _ready_engine_and_options()
    mysekai = DeckRecommendOptions(options)
    mysekai.live_type = "mysekai"
    mysekai.target = target
    mysekai.fixed_cards = [162, 664, 666, 938, 939]

    deck = engine.recommend(mysekai).decks[0]
    assert deck.mysekai_event_point == 2500
    assert deck.multi_live_score_up == 0.0
    assert deck.score == 0


def test_string_and_bytes_data_loading_match_file_loading():
    file_engine, file_options, masterdata, music_metas = _ready_engine_and_options()
    file_options.fixed_cards = [162, 664, 666, 938, 939]
    expected = file_engine.recommend(file_options).to_dict()
    expected.pop("cost_ms")

    tables = {
        path.stem: path.read_bytes()
        for path in masterdata.iterdir()
        if path.suffix == ".json"
    }
    memory_engine = SekaiDeckRecommend()
    memory_engine.update_masterdata_from_strings(tables, "cn")
    memory_engine.update_musicmetas_from_string(music_metas.read_bytes(), "cn")
    actual = memory_engine.recommend(file_options).to_dict()
    actual.pop("cost_ms")
    assert actual == expected


def test_semantic_option_errors_are_value_errors():
    engine, options, _, _ = _ready_engine_and_options()

    wrong_target = DeckRecommendOptions(options)
    wrong_target.target_bonus_list = [300]
    with pytest.raises(ValueError):
        engine.recommend(wrong_target)

    solo_bound = DeckRecommendOptions(options)
    solo_bound.live_type = "solo"
    solo_bound.multi_live_score_up_lower_bound = 100.0
    with pytest.raises(ValueError):
        engine.recommend(solo_bound)

    missing_specific = DeckRecommendOptions(options)
    missing_specific.skill_order_choose_strategy = "specific"
    with pytest.raises(ValueError):
        engine.recommend(missing_specific)
