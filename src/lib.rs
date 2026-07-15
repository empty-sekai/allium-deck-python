use std::collections::{BTreeMap, HashMap};
use std::fs;
use std::sync::{Arc, RwLock};
use std::time::Instant;

use allium_deck::engine::{
    parse_build_params_json, parse_user_profile_json, MasterdataSources, OwnedGameData,
};
use allium_deck::auxiliary::{
    recommend_music, AuxiliaryData, MusicDeck, MusicDeckCard, MusicRecommendOptions,
};
use allium_deck::handler::{
    build_card_pool_with_details, cultivated_user_cards, world_bloom_support_cards,
    FullPrecisionCard, UserCard, UserProfile,
};
use allium_deck::pool::{CardIdx, CardPool};
use allium_deck::search::{
    search, search_bonus_targets, summarize_deck, SearchContext, SearchParams,
};
use allium_deck::{DefaultImage, EventType, LiveType, PowerDetail, ScoreTarget, DECK_SIZE};
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use serde_json::{json, Value};

const MYSEKAI_EVENT_POINT: i32 = 2_500;

struct RegionData {
    tables: BTreeMap<String, String>,
    music_metas: String,
    loaded_music_metas: Arc<Vec<allium_deck::handler::MusicMeta>>,
    game: Arc<OwnedGameData>,
    auxiliary: Arc<AuxiliaryData>,
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
        let loaded_music_metas = Arc::new(
            parse_loaded_music_metas(music_metas).map_err(PyValueError::new_err)?,
        );
        let game = Arc::new(build_game(&tables, music_metas).map_err(PyValueError::new_err)?);
        let auxiliary = Arc::clone(&current.auxiliary);
        regions.insert(
            region.to_string(),
            RegionData {
                tables,
                music_metas: music_metas.to_string(),
                loaded_music_metas,
                game,
                auxiliary,
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

    fn get_world_bloom_support_cards(
        &self,
        py: Python<'_>,
        region: &str,
        options_json: &str,
        user_data: &NativeUserData,
    ) -> PyResult<String> {
        let game = self.region_game(region)?;
        let mut params = parse_build_params_json(options_json)
            .map_err(|error| PyValueError::new_err(error.to_string()))?;
        let raw: Value = serde_json::from_str(options_json)
            .map_err(|error| PyValueError::new_err(error.to_string()))?;
        if params.world_bloom_character_id.is_none() {
            params.world_bloom_character_id = raw
                .get("forcedLeaderCharacterId")
                .and_then(Value::as_i64)
                .and_then(|value| i32::try_from(value).ok());
        }
        let support_master_max = raw
            .get("support_master_max")
            .or_else(|| raw.get("supportMasterMax"))
            .and_then(Value::as_bool)
            .unwrap_or(false);
        let support_skill_max = raw
            .get("support_skill_max")
            .or_else(|| raw.get("supportSkillMax"))
            .and_then(Value::as_bool)
            .unwrap_or(false);
        let filter_other_unit = raw
            .get("filter_other_unit")
            .or_else(|| raw.get("filterOtherUnit"))
            .and_then(Value::as_bool)
            .unwrap_or(false);
        let user = Arc::clone(&user_data.profile);
        py.allow_threads(move || {
            let game_ref = game.as_ref().as_ref();
            let cards = world_bloom_support_cards(
                &user,
                &game_ref,
                &params,
                support_master_max,
                support_skill_max,
                filter_other_unit,
            )
            .map_err(|error| error.to_string())?;
            let output = cards
                .into_iter()
                .map(|card| {
                    json!({
                        "card_id": card.card_id,
                        "bonus": card.bonus,
                        "skill_level": card.skill_level,
                        "master_rank": card.master_rank,
                        "level": card.level,
                        "after_training": card.after_training,
                        "default_image": default_image(card.default_image),
                    })
                })
                .collect::<Vec<_>>();
            serde_json::to_string(&output).map_err(|error| error.to_string())
        })
        .map_err(PyRuntimeError::new_err)
    }

    fn recommend_area_items(
        &self,
        py: Python<'_>,
        region: &str,
        card_ids: Vec<i32>,
        user_data: &NativeUserData,
    ) -> PyResult<String> {
        let (game, auxiliary) = self.region_calculators(region)?;
        let user = Arc::clone(&user_data.profile);
        py.allow_threads(move || {
            let game_ref = game.as_ref().as_ref();
            let result = auxiliary.recommend_area_items(&user, &game_ref, &card_ids)?;
            serde_json::to_string(&result).map_err(|error| error.to_string())
        })
        .map_err(PyRuntimeError::new_err)
    }

    fn recommend_music(
        &self,
        py: Python<'_>,
        region: &str,
        options_json: &str,
        deck_json: &str,
    ) -> PyResult<String> {
        let (game, loaded_music_metas) = self.region_music(region)?;
        let params = parse_build_params_json(options_json)
            .map_err(|error| PyValueError::new_err(error.to_string()))?;
        let deck_value: Value = serde_json::from_str(deck_json)
            .map_err(|error| PyValueError::new_err(error.to_string()))?;
        let deck = music_deck_from_json(&deck_value).map_err(PyValueError::new_err)?;
        let event_type = resolve_event_type(&game, &params).map_err(PyValueError::new_err)?;
        let live_type = if matches!(params.live_type, LiveType::Multi)
            && matches!(event_type, EventType::CheerfulCarnival)
        {
            LiveType::Cheerful
        } else if matches!(params.live_type, LiveType::Mysekai) {
            LiveType::Multi
        } else {
            params.live_type
        };
        let options = MusicRecommendOptions {
            live_type,
            event_type,
            skill_order: params.live_skill_order,
            specific_skill_order: params
                .specific_skill_order
                .map(|order| order.into_iter().collect()),
            multi_teammate_score_up: params.multi_teammate_score_up,
            multi_teammate_power: params.multi_teammate_power,
        };
        py.allow_threads(move || {
            let result = recommend_music(&loaded_music_metas, &deck, &options)?;
            serde_json::to_string(&result).map_err(|error| error.to_string())
        })
        .map_err(PyRuntimeError::new_err)
    }

    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (
        region,
        power,
        skills,
        live_type,
        music_score_json,
        multi_sum_power = 0,
        fever_music_score_json = None
    ))]
    fn calculate_exact_live(
        &self,
        py: Python<'_>,
        region: &str,
        power: i32,
        skills: Vec<f64>,
        live_type: &str,
        music_score_json: &str,
        multi_sum_power: i32,
        fever_music_score_json: Option<&str>,
    ) -> PyResult<String> {
        let (_, auxiliary) = self.region_calculators(region)?;
        let live_type = parse_live_type(live_type).map_err(PyValueError::new_err)?;
        py.allow_threads(move || {
            let result = auxiliary.calculate_exact_live(
                power,
                &skills,
                live_type,
                music_score_json,
                multi_sum_power,
                fever_music_score_json,
            )?;
            serde_json::to_string(&result).map_err(|error| error.to_string())
        })
        .map_err(PyRuntimeError::new_err)
    }
}

impl NativeEngine {
    fn region_game(&self, region: &str) -> PyResult<Arc<OwnedGameData>> {
        self.regions
            .read()
            .map_err(lock_error)?
            .get(region)
            .map(|data| Arc::clone(&data.game))
            .ok_or_else(|| {
                PyRuntimeError::new_err(format!("masterdata for region {region} is not loaded"))
            })
    }

    fn region_calculators(
        &self,
        region: &str,
    ) -> PyResult<(Arc<OwnedGameData>, Arc<AuxiliaryData>)> {
        self.regions
            .read()
            .map_err(lock_error)?
            .get(region)
            .map(|data| (Arc::clone(&data.game), Arc::clone(&data.auxiliary)))
            .ok_or_else(|| {
                PyRuntimeError::new_err(format!("masterdata for region {region} is not loaded"))
            })
    }

    fn region_music(
        &self,
        region: &str,
    ) -> PyResult<(Arc<OwnedGameData>, Arc<Vec<allium_deck::handler::MusicMeta>>)> {
        self.regions
            .read()
            .map_err(lock_error)?
            .get(region)
            .map(|data| (Arc::clone(&data.game), Arc::clone(&data.loaded_music_metas)))
            .ok_or_else(|| {
                PyRuntimeError::new_err(format!("masterdata for region {region} is not loaded"))
            })
    }

    fn replace_tables(&self, region: &str, tables: BTreeMap<String, String>) -> PyResult<()> {
        let mut regions = self.regions.write().map_err(lock_error)?;
        let music_metas = regions
            .get(region)
            .map(|data| data.music_metas.clone())
            .unwrap_or_else(|| "[]".to_string());
        let loaded_music_metas = Arc::new(
            parse_loaded_music_metas(&music_metas).map_err(PyValueError::new_err)?,
        );
        let game = Arc::new(build_game(&tables, &music_metas).map_err(PyValueError::new_err)?);
        let auxiliary = Arc::new(
            AuxiliaryData::from_strings(&tables).map_err(PyValueError::new_err)?,
        );
        regions.insert(
            region.to_string(),
            RegionData {
                tables,
                music_metas,
                loaded_music_metas,
                game,
                auxiliary,
            },
        );
        Ok(())
    }
}

fn parse_loaded_music_metas(text: &str) -> Result<Vec<allium_deck::handler::MusicMeta>, String> {
    let rows: Vec<Value> =
        serde_json::from_str(text).map_err(|error| format!("invalid music metas: {error}"))?;
    rows.iter()
        .map(|row| {
            let event_rate = value_i32(row, "event_rate")?;
            Ok(allium_deck::handler::MusicMeta {
                music_id: value_i32(row, "music_id")?,
                difficulty: row
                    .get("difficulty")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                event_rate_solo: event_rate,
                event_rate_multi: event_rate,
                event_rate_auto: event_rate,
                base_score: value_f64(row, "base_score")?,
                base_score_auto: value_f64(row, "base_score_auto")?,
                fever_score: value_f64(row, "fever_score")?,
                solo_skill_scores: value_f64_array(row, "skill_score_solo")?,
                multi_skill_scores: value_f64_array(row, "skill_score_multi")?,
                auto_skill_scores: value_f64_array(row, "skill_score_auto")?,
                music_time: value_f64(row, "music_time")?,
                tap_count: value_i32(row, "tap_count")?,
            })
        })
        .collect()
}

fn value_i32(value: &Value, key: &str) -> Result<i32, String> {
    value
        .get(key)
        .and_then(Value::as_i64)
        .and_then(|value| i32::try_from(value).ok())
        .ok_or_else(|| format!("music meta field {key} is required"))
}

fn value_f64(value: &Value, key: &str) -> Result<f64, String> {
    value
        .get(key)
        .and_then(Value::as_f64)
        .ok_or_else(|| format!("music meta field {key} is required"))
}

fn value_f64_array(value: &Value, key: &str) -> Result<[f64; 6], String> {
    let values = value
        .get(key)
        .and_then(Value::as_array)
        .ok_or_else(|| format!("music meta field {key} is required"))?;
    if values.len() != 6 {
        return Err(format!("music meta field {key} must contain 6 values"));
    }
    let mut result = [0.0; 6];
    for (index, item) in values.iter().enumerate() {
        result[index] = item
            .as_f64()
            .ok_or_else(|| format!("music meta field {key}[{index}] must be numeric"))?;
    }
    Ok(result)
}

fn music_deck_from_json(value: &Value) -> Result<MusicDeck, String> {
    let cards = value
        .get("cards")
        .and_then(Value::as_array)
        .ok_or_else(|| "deck.cards is required".to_string())?
        .iter()
        .map(|card| MusicDeckCard {
            skill_score_up: card
                .get("skill_score_up")
                .and_then(Value::as_f64)
                .unwrap_or(0.0),
            skill_life_recovery: card
                .get("skill_life_recovery")
                .and_then(Value::as_f64)
                .unwrap_or(0.0),
        })
        .collect::<Vec<_>>();
    Ok(MusicDeck {
        total_power: json_i32(value, "total_power")?,
        event_bonus_rate: value
            .get("event_bonus_rate")
            .and_then(Value::as_f64)
            .unwrap_or(0.0),
        support_deck_bonus_rate: value
            .get("support_deck_bonus_rate")
            .and_then(Value::as_f64)
            .unwrap_or(0.0),
        cards,
    })
}

fn json_i32(value: &Value, key: &str) -> Result<i32, String> {
    value
        .get(key)
        .and_then(Value::as_i64)
        .and_then(|value| i32::try_from(value).ok())
        .ok_or_else(|| format!("deck.{key} is required"))
}

fn resolve_event_type(
    game: &OwnedGameData,
    params: &allium_deck::handler::BuildParams,
) -> Result<EventType, String> {
    let value = params.event_id.and_then(|event_id| {
        game.events
            .iter()
            .find(|event| event.id == event_id)
            .map(|event| event.event_type.as_str())
    });
    parse_event_type(value.or(params.event_type.as_deref()).unwrap_or("marathon"))
}

fn parse_event_type(value: &str) -> Result<EventType, String> {
    match value.trim().to_ascii_lowercase().as_str() {
        "marathon" => Ok(EventType::Marathon),
        "cheerful" | "cheerful_carnival" | "cheerfulcarnival" => {
            Ok(EventType::CheerfulCarnival)
        }
        "world_bloom" | "worldbloom" | "wl" => Ok(EventType::WorldBloom),
        _ => Err(format!("invalid event type: {value}")),
    }
}

fn parse_live_type(value: &str) -> Result<LiveType, String> {
    match value.trim().to_ascii_lowercase().as_str() {
        "solo" => Ok(LiveType::Solo),
        "auto" => Ok(LiveType::Auto),
        "multi" => Ok(LiveType::Multi),
        "cheerful" | "cheerful_live" => Ok(LiveType::Cheerful),
        "challenge" => Ok(LiveType::Challenge),
        "challenge_auto" => Ok(LiveType::ChallengeAuto),
        _ => Err(format!("invalid live type: {value}")),
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
    if results.is_empty() && params.target_bonus_list.is_empty() {
        return Err(format!(
            "Cannot recommend any deck in {} cards",
            user.user_cards.len()
        ));
    }
    let cultivated = cultivated_user_cards(user, &game, params)
        .into_iter()
        .map(|card| (card.card_id, card))
        .collect::<HashMap<_, _>>();
    let decks = results
        .iter()
        .filter_map(|result| {
            materialize_deck(
                result.cards,
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
            "after_training": user_card.is_some_and(user_card_after_training),
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
                "skill_score_up": summary.card_skill_score_up[position] as i32,
                "skill_life_recovery": detail.skill.life_recovery as i32,
                "episode1_read": episodes >= 1,
                "episode2_read": episodes >= 2,
                "after_training": detail.after_training,
                "default_image": if detail.skill_state_controls_image {
                    default_image(detail.default_image)
                } else {
                    user_card.map_or_else(
                        || default_image(detail.default_image),
                        |card| card.default_image.as_str(),
                    )
                },
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
    let mysekai_event_point = if matches!(ctx.live_type, LiveType::Mysekai)
        || matches!(target, ScoreTarget::Mysekai)
    {
        MYSEKAI_EVENT_POINT
    } else {
        0
    };
    let score = if matches!(target, ScoreTarget::Mysekai) {
        0
    } else {
        summary.event_point.unwrap_or(summary.live_score)
    };

    Some(json!({
        "score": score,
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
        "multi_live_score_up": if matches!(ctx.live_type, LiveType::Mysekai) {
            0.0
        } else {
            summary.multi_live_score_up
        },
        "support_deck_cards": support_cards,
        "cards": cards,
    }))
}

fn user_card_after_training(card: &UserCard) -> bool {
    matches!(
        card.special_training_status
            .trim()
            .to_ascii_lowercase()
            .as_str(),
        "done" | "special_training" | "trained" | "after_training"
    )
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
