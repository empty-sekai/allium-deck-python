use std::collections::{BTreeMap, HashMap};
use std::fs;
use std::sync::{Arc, RwLock};
use std::time::Instant;

use allium_deck::engine::{
    parse_build_params_json, parse_user_profile_json, MasterdataSources, OwnedGameData,
};
use allium_deck::handler::{
    build_card_pool_with_details, cultivated_user_cards, FullPrecisionCard, UserCard, UserProfile,
};
use allium_deck::pool::{CardIdx, CardPool};
use allium_deck::search::{
    search, search_bonus_targets, summarize_deck, SearchContext, SearchParams,
};
use allium_deck::{DefaultImage, PowerDetail, ScoreTarget, DECK_SIZE};
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use serde_json::{json, Value};

struct RegionData {
    tables: BTreeMap<String, String>,
    music_metas: String,
    game: Arc<OwnedGameData>,
}

#[pyclass]
struct NativeUserData {
    profile: Arc<UserProfile>,
}

#[pymethods]
impl NativeUserData {
    #[new]
    fn new(data: &[u8]) -> PyResult<Self> {
        let text =
            std::str::from_utf8(data).map_err(|error| PyValueError::new_err(error.to_string()))?;
        let profile = parse_user_profile_json(text)
            .map_err(|error| PyValueError::new_err(error.to_string()))?;
        Ok(Self {
            profile: Arc::new(profile),
        })
    }
}

#[pyclass]
struct NativeEngine {
    regions: RwLock<HashMap<String, RegionData>>,
}

#[pymethods]
impl NativeEngine {
    #[new]
    fn new() -> Self {
        Self {
            regions: RwLock::new(HashMap::new()),
        }
    }

    fn update_masterdata(&self, base_dir: &str, region: &str) -> PyResult<()> {
        let mut tables = BTreeMap::new();
        for entry in fs::read_dir(base_dir).map_err(py_runtime)? {
            let entry = entry.map_err(py_runtime)?;
            let path = entry.path();
            if path.extension().and_then(|value| value.to_str()) != Some("json") {
                continue;
            }
            let Some(name) = path.file_name().and_then(|value| value.to_str()) else {
                continue;
            };
            tables.insert(
                name.to_string(),
                fs::read_to_string(&path).map_err(py_runtime)?,
            );
        }
        self.replace_tables(region, tables)
    }

    fn update_masterdata_from_strings(
        &self,
        tables: HashMap<String, String>,
        region: &str,
    ) -> PyResult<()> {
        self.replace_tables(region, tables.into_iter().collect())
    }

    fn update_musicmetas(&self, music_metas: &str, region: &str) -> PyResult<()> {
        let mut regions = self.regions.write().map_err(lock_error)?;
        let current = regions.get(region).ok_or_else(|| {
            PyRuntimeError::new_err(format!("masterdata for region {region} is not loaded"))
        })?;
        let tables = current.tables.clone();
        let game = Arc::new(build_game(&tables, music_metas).map_err(PyValueError::new_err)?);
        regions.insert(
            region.to_string(),
            RegionData {
                tables,
                music_metas: music_metas.to_string(),
                game,
            },
        );
        Ok(())
    }

    fn recommend(
        &self,
        py: Python<'_>,
        region: &str,
        options_json: &str,
        user_data: &NativeUserData,
    ) -> PyResult<String> {
        let game = self
            .regions
            .read()
            .map_err(lock_error)?
            .get(region)
            .map(|data| Arc::clone(&data.game))
            .ok_or_else(|| {
                PyRuntimeError::new_err(format!("masterdata for region {region} is not loaded"))
            })?;
        let params = parse_build_params_json(options_json)
            .map_err(|error| PyValueError::new_err(error.to_string()))?;
        let user = Arc::clone(&user_data.profile);
        py.allow_threads(move || recommend_json(&user, &game, &params))
            .map_err(PyRuntimeError::new_err)
    }
}

impl NativeEngine {
    fn replace_tables(&self, region: &str, tables: BTreeMap<String, String>) -> PyResult<()> {
        let mut regions = self.regions.write().map_err(lock_error)?;
        let music_metas = regions
            .get(region)
            .map(|data| data.music_metas.clone())
            .unwrap_or_else(|| "[]".to_string());
        let game = Arc::new(build_game(&tables, &music_metas).map_err(PyValueError::new_err)?);
        regions.insert(
            region.to_string(),
            RegionData {
                tables,
                music_metas,
                game,
            },
        );
        Ok(())
    }
}

fn build_game(
    tables: &BTreeMap<String, String>,
    music_metas: &str,
) -> Result<OwnedGameData, String> {
    let sources = MasterdataSources::from_strings(tables.clone(), music_metas.to_string());
    OwnedGameData::from_sources(&sources)
}

fn recommend_json(
    user: &UserProfile,
    owned: &OwnedGameData,
    params: &allium_deck::handler::BuildParams,
) -> Result<String, String> {
    let game = owned.as_ref();
    let (pool, ctx, details) =
        build_card_pool_with_details(user, &game, params).map_err(|error| error.to_string())?;
    let search_params = SearchParams {
        top_k: params.limit,
        timeout_ms: params.timeout_ms,
    };
    let search_started = Instant::now();
    let results = if params.target_bonus_list.is_empty() {
        search(&pool, &ctx, &search_params)
    } else {
        search_bonus_targets(&pool, &ctx, &search_params, &params.target_bonus_list).0
    };
    let cost_ms = search_started.elapsed().as_secs_f64() * 1000.0;
    let cultivated = cultivated_user_cards(user, &game, params)
        .into_iter()
        .map(|card| (card.card_id, card))
        .collect::<HashMap<_, _>>();
    let decks = results
        .iter()
        .filter_map(|result| {
            materialize_deck(
                result.cards,
                result.score,
                &pool,
                &ctx,
                &details,
                &cultivated,
                user,
                params.target,
            )
        })
        .collect::<Vec<_>>();
    serde_json::to_string(&json!({
        "decks": decks,
        "cost_ms": cost_ms,
    }))
    .map_err(|error| error.to_string())
}

#[allow(clippy::too_many_arguments)]
fn materialize_deck(
    deck: [CardIdx; DECK_SIZE],
    target_score: u64,
    pool: &CardPool,
    ctx: &SearchContext,
    details: &[FullPrecisionCard],
    cultivated: &HashMap<i32, UserCard>,
    user: &UserProfile,
    target: ScoreTarget,
) -> Option<Value> {
    let summary = summarize_deck(pool, ctx, &deck)?;
    let ordered = summary.ordered_cards;
    let power_details = resolve_power_details(pool, details, &ordered);
    let support = ctx.support_deck_for_leader(pool.char_id(ordered[0]));
    let main_ids = ordered.map(|card| pool.game_id(card));
    let mut support_cards = Vec::new();
    let mut support_bonus = 0.0;
    for &(card_id, bonus) in &support.cards {
        if support_cards.len() >= support.count as usize {
            break;
        }
        if main_ids.contains(&card_id) {
            continue;
        }
        support_bonus += bonus;
        let user_card = cultivated.get(&(card_id as i32));
        support_cards.push(json!({
            "card_id": card_id,
            "bonus": bonus,
            "skill_level": user_card.map_or(0, |card| card.skill_level),
            "master_rank": user_card.map_or(0, |card| card.master_rank),
            "level": user_card.map_or(0, |card| card.level),
            "after_training": user_card.is_some_and(|card| card.special_training_status != "none"),
            "default_image": user_card.map_or("original", |card| card.default_image.as_str()),
        }));
    }

    let cards = ordered
        .iter()
        .enumerate()
        .map(|(position, card)| {
            let dense = card.raw();
            let detail = &details[dense];
            let user_card = cultivated.get(&(detail.game_card_id as i32));
            let episodes = user_card.map(|card| card.episodes_read.len()).unwrap_or(0);
            let has_canvas = user_card
                .and_then(|card| card.has_canvas_bonus_override)
                .unwrap_or_else(|| {
                    user.user_mysekai_canvas_bonus_cards
                        .contains(&(detail.game_card_id as i32))
                });
            json!({
                "card_id": detail.game_card_id,
                "total_power": summary.card_power_total[position],
                "base_power": power_details[position].base,
                "event_bonus_rate": summary.card_event_bonus_rates[position],
                "master_rank": detail.master_rank,
                "level": user_card.map_or(0, |card| card.level),
                "skill_level": detail.skill_level,
                "skill_score_up": summary.card_skill_score_up[position],
                "skill_life_recovery": detail.skill.life_recovery,
                "episode1_read": episodes >= 1,
                "episode2_read": episodes >= 2,
                "after_training": ctx.skill_is_after_training_at(dense),
                "default_image": default_image(detail.default_image),
                "has_canvas_bonus": has_canvas,
            })
        })
        .collect::<Vec<_>>();

    let base_power = power_details.iter().map(|detail| detail.base).sum::<i32>();
    let area_item_bonus_power = power_details
        .iter()
        .map(|detail| detail.area_item_bonus)
        .sum::<i32>();
    let character_bonus_power = power_details
        .iter()
        .map(|detail| detail.character_bonus)
        .sum::<i32>();
    let fixture_bonus_power = power_details
        .iter()
        .map(|detail| detail.fixture_bonus)
        .sum::<i32>();
    let gate_bonus_power = power_details
        .iter()
        .map(|detail| detail.gate_bonus)
        .sum::<i32>();
    let total_bonus = summary.event_bonus_total.unwrap_or(0.0);
    let event_bonus = (total_bonus - support_bonus).max(0.0);
    let mysekai_event_point = if matches!(target, ScoreTarget::Mysekai) {
        target_score.min(i32::MAX as u64) as i32
    } else {
        0
    };
    let score = summary.event_point.unwrap_or(summary.live_score);

    Some(json!({
        "score": if matches!(target, ScoreTarget::Mysekai) { mysekai_event_point } else { score },
        "live_score": summary.live_score,
        "mysekai_event_point": mysekai_event_point,
        "total_power": summary.total_power,
        "base_power": base_power,
        "area_item_bonus_power": area_item_bonus_power,
        "character_bonus_power": character_bonus_power,
        "honor_bonus_power": ctx.honor_bonus,
        "fixture_bonus_power": fixture_bonus_power,
        "gate_bonus_power": gate_bonus_power,
        "event_bonus_rate": event_bonus,
        "support_deck_bonus_rate": support_bonus,
        "multi_live_score_up": summary.multi_live_score_up,
        "support_deck_cards": support_cards,
        "cards": cards,
    }))
}

fn resolve_power_details(
    pool: &CardPool,
    details: &[FullPrecisionCard],
    deck: &[CardIdx; DECK_SIZE],
) -> [PowerDetail; DECK_SIZE] {
    let mut attr_counts = [0u8; 6];
    let mut unit_counts = [0u8; 6];
    for &card in deck {
        attr_counts[pool.attr(card) as usize] += 1;
        let mask = pool.unit_mask_raw(card);
        for unit in 0..6 {
            if mask & (1u8 << unit) != 0 {
                unit_counts[unit] += 1;
            }
        }
    }
    std::array::from_fn(|position| {
        let card = deck[position];
        let detail = &details[card.raw()];
        let attr_all = attr_counts[pool.attr(card) as usize] == DECK_SIZE as u8;
        let mut best = PowerDetail::default();
        for unit in 0..6 {
            if pool.unit_mask_raw(card) & (1u8 << unit) == 0 {
                continue;
            }
            let unit_all = unit_counts[unit] == DECK_SIZE as u8;
            let key = (unit_all as usize) * 2 + attr_all as usize;
            let candidate = detail.power[unit][key];
            if candidate.total > best.total {
                best = candidate;
            }
        }
        best
    })
}

fn default_image(image: DefaultImage) -> &'static str {
    match image {
        DefaultImage::Original => "original",
        DefaultImage::SpecialTraining => "special_training",
    }
}

fn py_runtime(error: std::io::Error) -> PyErr {
    PyRuntimeError::new_err(error.to_string())
}

fn lock_error<T>(error: std::sync::PoisonError<T>) -> PyErr {
    PyRuntimeError::new_err(error.to_string())
}

#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<NativeEngine>()?;
    module.add_class::<NativeUserData>()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::thread;
    use std::time::Duration;

    fn empty_tables(cards: String) -> BTreeMap<String, String> {
        let mut tables = [
            "gameCharacterUnits.json",
            "events.json",
            "cardRarities.json",
            "cardEpisodes.json",
            "masterLessons.json",
            "skills.json",
            "areaItemLevels.json",
            "characterRanks.json",
            "cardMysekaiCanvasBonuses.json",
            "eventCards.json",
            "eventDeckBonuses.json",
            "eventCardBonusLimits.json",
            "eventHonorBonuses.json",
            "worldBloomDifferentAttributeBonuses.json",
            "eventSkillScoreUpLimits.json",
            "eventRarityBonusRates.json",
        ]
        .into_iter()
        .map(|name| (name.to_string(), "[]".to_string()))
        .collect::<BTreeMap<_, _>>();
        tables.insert("cards.json".to_string(), cards);
        tables
    }

    #[test]
    fn concurrent_table_and_music_updates_preserve_both_successes() {
        pyo3::prepare_freethreaded_python();
        let engine = Arc::new(NativeEngine::new());
        engine
            .replace_tables("cn", empty_tables("[]".to_string()))
            .expect("initial tables");

        let slow_cards = format!("[{}]", " ".repeat(32 * 1024 * 1024));
        let updater = Arc::clone(&engine);
        let table_thread = thread::spawn(move || {
            updater
                .replace_tables("cn", empty_tables(slow_cards))
                .expect("table update")
        });
        thread::sleep(Duration::from_millis(20));
        engine.update_musicmetas("[ ]", "cn").expect("music update");
        table_thread.join().expect("table thread");

        let regions = engine.regions.read().expect("regions");
        let current = regions.get("cn").expect("cn region");
        assert_eq!(current.music_metas, "[ ]");
        assert!(current.tables["cards.json"].len() > 32 * 1024 * 1024);
    }
}
