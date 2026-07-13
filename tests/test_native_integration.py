import os
from pathlib import Path

import pytest

from sekai_deck_recommend_cpp import (
    DeckRecommendOptions,
    DeckRecommendResult,
    DeckRecommendUserData,
    SekaiDeckRecommend,
)


def _fixture_paths():
    keys = ("ALLIUM_MASTERDATA", "ALLIUM_MUSIC_METAS", "ALLIUM_USER_DATA")
    if not all(os.environ.get(key) for key in keys):
        pytest.skip("native integration fixture paths are not configured")
    return tuple(Path(os.environ[key]) for key in keys)


def test_native_score_recommendation_materializes_lunabot_fields():
    masterdata, music_metas, user_path = _fixture_paths()
    engine = SekaiDeckRecommend()
    engine.update_masterdata(str(masterdata), "cn")
    engine.update_musicmetas(str(music_metas), "cn")

    user = DeckRecommendUserData()
    user.load_from_file(str(user_path))
    options = DeckRecommendOptions()
    options.region = "cn"
    options.algorithm = "ga"
    options.user_data = user
    options.live_type = "multi"
    options.event_id = 133
    options.music_id = 1
    options.music_diff = "master"
    options.target = "score"
    options.limit = 2

    result = engine.recommend(options)
    assert isinstance(result, DeckRecommendResult)
    assert 1 <= len(result.decks) <= 2
    deck = result.decks[0]
    assert len(deck.cards) == 5
    assert deck.score > 0
    assert deck.live_score > 0
    assert deck.total_power > 0
    assert deck.event_bonus_rate > 0
    assert all(card.card_id > 0 for card in deck.cards)
    assert all(card.total_power > 0 for card in deck.cards)
    assert all(card.default_image in ("original", "special_training") for card in deck.cards)

    with pytest.raises(ValueError):
        engine.update_masterdata_from_strings({"cards": "[]"}, "cn")
    assert engine.recommend(options).decks


def test_native_bonus_target_returns_exact_requested_bucket():
    masterdata, music_metas, user_path = _fixture_paths()
    engine = SekaiDeckRecommend()
    engine.update_masterdata(str(masterdata), "cn")
    engine.update_musicmetas(str(music_metas), "cn")
    user = DeckRecommendUserData()
    user.load_from_file(str(user_path))

    baseline = DeckRecommendOptions.from_dict(
        {
            "region": "cn",
            "user_data": user,
            "live_type": "multi",
            "event_id": 133,
            "music_id": 1,
            "music_diff": "master",
            "target": "bonus",
            "limit": 1,
        }
    )
    maximum = engine.recommend(baseline).decks[0].event_bonus_rate
    baseline.target_bonus_list = [int(maximum)]
    exact = engine.recommend(baseline)
    assert exact.decks
    assert exact.decks[0].event_bonus_rate == pytest.approx(int(maximum), abs=0.01)
