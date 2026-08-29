import os
from pathlib import Path

import pytest
from sekai_deck_recommend_cpp import (
    DeckRecommendOptions,
    DeckRecommendResult,
    DeckRecommendUserData,
    PreparedCardPool,
    SekaiDeckRecommend,
)


def _fixture_paths():
    keys = ("ALLIUM_MASTERDATA", "ALLIUM_MUSIC_METAS", "ALLIUM_USER_DATA")
    if not all(os.environ.get(key) for key in keys):
        pytest.skip("native integration fixture paths are not configured")
    return tuple(Path(os.environ[key]) for key in keys)


def _engine_and_options():
    masterdata, music_metas, user_path = _fixture_paths()
    engine = SekaiDeckRecommend()
    engine.update_masterdata(str(masterdata), "cn")
    engine.update_musicmetas(str(music_metas), "cn")

    user = DeckRecommendUserData()
    user.load_from_file(str(user_path))
    options = DeckRecommendOptions()
    options.region = "cn"
    options.algorithm = "dfs"
    options.user_data = user
    options.live_type = "multi"
    options.event_id = 133
    options.music_id = 1
    options.music_diff = "master"
    options.target = "score"
    options.limit = 1
    return engine, options


def test_pool_search_matches_direct_recommend():
    engine, options = _engine_and_options()
    direct = engine.recommend(options)
    pool = engine.build_pool(options)

    assert isinstance(pool, PreparedCardPool)
    assert pool.card_count > 0
    assert pool.limit == options.limit

    via_pool = pool.recommend()
    assert isinstance(via_pool, DeckRecommendResult)
    assert len(via_pool.decks) == len(direct.decks)

    expected, actual = direct.decks[0], via_pool.decks[0]
    assert actual.score == expected.score
    assert actual.total_power == expected.total_power
    assert actual.event_bonus_rate == expected.event_bonus_rate
    assert [card.card_id for card in actual.cards] == [
        card.card_id for card in expected.cards
    ]


def test_pool_is_reusable_across_searches():
    engine, options = _engine_and_options()
    pool = engine.build_pool(options)
    first = pool.recommend()
    second = pool.recommend()
    assert [card.card_id for card in first.decks[0].cards] == [
        card.card_id for card in second.decks[0].cards
    ]
    assert first.decks[0].score == second.decks[0].score


def test_pool_search_stage_options_are_overridable():
    engine, options = _engine_and_options()
    options.limit = 1
    pool = engine.build_pool(options)
    assert len(pool.recommend().decks) == 1

    widened = pool.recommend(limit=3)
    assert 1 < len(widened.decks) <= 3

    options.limit = 3
    direct = engine.recommend(options)
    assert [card.card_id for card in widened.decks[0].cards] == [
        card.card_id for card in direct.decks[0].cards
    ]


def test_pool_rejects_unknown_region():
    masterdata, music_metas, user_path = _fixture_paths()
    engine = SekaiDeckRecommend()
    engine.update_masterdata(str(masterdata), "cn")
    engine.update_musicmetas(str(music_metas), "cn")
    user = DeckRecommendUserData()
    user.load_from_file(str(user_path))
    options = DeckRecommendOptions()
    options.region = "jp"
    options.user_data = user
    options.live_type = "multi"
    options.event_id = 133
    options.music_id = 1
    options.music_diff = "master"
    options.target = "score"
    with pytest.raises(RuntimeError):
        engine.build_pool(options)
