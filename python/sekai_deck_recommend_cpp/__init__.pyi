from typing import Optional, Dict, Any, List, Union

class DeckRecommendUserData:
    def __init__(self) -> None: ...
    def load_from_file(self, path: str) -> None: ...
    def load_from_bytes(self, data: Union[str, bytes]) -> None: ...

class DeckRecommendCardConfig:
    disable: Optional[bool]
    level_max: Optional[bool]
    episode_read: Optional[bool]
    master_max: Optional[bool]
    skill_max: Optional[bool]
    canvas: Optional[bool]
    level: Optional[int]
    skill_level: Optional[int]
    master_rank: Optional[int]
    episode_read_count: Optional[int]
    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DeckRecommendCardConfig': ...

class DeckRecommendSingleCardConfig:
    card_id: int
    disable: Optional[bool]
    level_max: Optional[bool]
    episode_read: Optional[bool]
    master_max: Optional[bool]
    skill_max: Optional[bool]
    canvas: Optional[bool]
    level: Optional[int]
    skill_level: Optional[int]
    master_rank: Optional[int]
    episode_read_count: Optional[int]
    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DeckRecommendSingleCardConfig': ...

class DeckRecommendSaOptions:
    run_num: Optional[int]
    seed: Optional[int]
    max_iter: Optional[int]
    max_no_improve_iter: Optional[int]
    time_limit_ms: Optional[int]
    start_temprature: Optional[float]
    cooling_rate: Optional[float]
    debug: Optional[bool]
    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DeckRecommendSaOptions': ...

class DeckRecommendGaOptions:
    seed: Optional[int]
    debug: Optional[bool]
    max_iter: Optional[int]
    max_no_improve_iter: Optional[int]
    pop_size: Optional[int]
    parent_size: Optional[int]
    elite_size: Optional[int]
    crossover_rate: Optional[float]
    base_mutation_rate: Optional[float]
    no_improve_iter_to_mutation_rate: Optional[float]
    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DeckRecommendGaOptions': ...

class DeckRecommendOptions:
    target: Optional[str]
    algorithm: Optional[str]
    region: str
    user_data: Optional[DeckRecommendUserData]
    user_data_file_path: Optional[str]
    user_data_str: Optional[Union[str, bytes]]
    live_type: str
    music_id: int
    music_diff: str
    event_id: Optional[int]
    event_attr: Optional[str]
    event_unit: Optional[str]
    event_type: Optional[str]
    world_bloom_event_turn: int
    world_bloom_character_id: Optional[int]
    challenge_live_character_id: Optional[int]
    limit: Optional[int]
    member: Optional[int]
    timeout_ms: Optional[int]
    rarity_1_config: Optional[DeckRecommendCardConfig]
    rarity_2_config: Optional[DeckRecommendCardConfig]
    rarity_3_config: Optional[DeckRecommendCardConfig]
    rarity_birthday_config: Optional[DeckRecommendCardConfig]
    rarity_4_config: Optional[DeckRecommendCardConfig]
    single_card_configs: Optional[List[DeckRecommendSingleCardConfig]]
    support_master_max: Optional[bool]
    support_skill_max: Optional[bool]
    filter_other_unit: Optional[bool]
    fixed_cards: Optional[List[int]]
    fixed_characters: Optional[List[int]]
    forcedLeaderCharacterId: Optional[int]
    target_bonus_list: Optional[List[int]]
    custom_bonus_character_ids: Optional[List[int]]
    custom_bonus_attr: Optional[str]
    custom_bonus_character_support_units: Optional[Dict[int, str]]
    skill_reference_choose_strategy: Optional[str]
    keep_after_training_state: Optional[bool]
    multi_live_teammate_score_up: Optional[int]
    multi_live_teammate_power: Optional[int]
    best_skill_as_leader: Optional[bool]
    multi_live_score_up_lower_bound: Optional[float]
    skill_order_choose_strategy: Optional[str]
    specific_skill_order: Optional[List[int]]
    sa_options: Optional[DeckRecommendSaOptions]
    ga_options: Optional[DeckRecommendGaOptions]
    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DeckRecommendOptions': ...

class RecommendCard:
    card_id: int
    total_power: int
    base_power: int
    event_bonus_rate: float
    master_rank: int
    level: int
    skill_level: int
    skill_score_up: int
    skill_life_recovery: int
    episode1_read: bool
    episode2_read: bool
    after_training: bool
    default_image: str
    has_canvas_bonus: bool
    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RecommendCard': ...

class RecommendSupportDeckCard:
    card_id: int
    bonus: float
    skill_level: int
    master_rank: int
    level: int
    after_training: bool
    default_image: str
    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RecommendSupportDeckCard': ...

class RecommendDeck:
    score: int
    live_score: int
    mysekai_event_point: int
    total_power: int
    base_power: int
    area_item_bonus_power: int
    character_bonus_power: int
    honor_bonus_power: int
    fixture_bonus_power: int
    gate_bonus_power: int
    event_bonus_rate: float
    support_deck_bonus_rate: float
    multi_live_score_up: float
    support_deck_cards: List['RecommendSupportDeckCard']
    cards: List[RecommendCard]
    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RecommendDeck': ...

class DeckRecommendResult:
    decks: List[RecommendDeck]
    cost_ms: float
    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DeckRecommendResult': ...

class SekaiDeckRecommend:
    def __init__(self) -> None: ...
    def update_masterdata(self, base_dir: str, region: str) -> None: ...
    def update_masterdata_from_strings(
        self, data: Dict[str, Union[str, bytes]], region: str
    ) -> None: ...
    def update_musicmetas(self, file_path: str, region: str) -> None: ...
    def update_musicmetas_from_string(self, data: Union[str, bytes], region: str) -> None: ...
    def recommend(self, options: DeckRecommendOptions) -> DeckRecommendResult: ...
    def recommend_batch(
        self, options_list: List[DeckRecommendOptions]
    ) -> List[DeckRecommendResult]: ...
    def get_world_bloom_support_cards(
        self, options: DeckRecommendOptions
    ) -> List[RecommendSupportDeckCard]: ...
    def recommend_area_items(
        self, options: DeckRecommendOptions, card_ids: List[int]
    ) -> List[Dict[str, Any]]: ...
    def recommend_music(
        self, options: DeckRecommendOptions, deck: RecommendDeck
    ) -> List[Dict[str, Any]]: ...
    def calculate_exact_live(
        self,
        region: str,
        power: int,
        skills: List[float],
        live_type: str,
        music_score_json: str,
        multi_sum_power: int = 0,
        fever_music_score_json: Optional[str] = None,
    ) -> Dict[str, Any]: ...

def set_engine_thread_count(threads: int) -> None: ...
