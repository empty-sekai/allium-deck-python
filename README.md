# allium-sekai-deck

Precompiled Python bindings for the Allium Sekai deck recommendation engine.
The package includes the Rust card-pool, rule evaluation, and DFS search logic,
so users do not need Rust, Cargo, or a local compiler.

It provides two Python interfaces:

- `allium_deck`: a compact API for new integrations.
- `sekai_deck_recommend_cpp`: the object and import surface used by LunaBot's
  C++ deck recommendation integration.

## Installation

```bash
pip install allium-sekai-deck
```

Precompiled `abi3` wheels support CPython 3.10 and newer on:

- Linux x86_64 and aarch64
- Windows x86_64
- macOS x86_64 and Apple Silicon

## Imports

```python
from allium_deck import Engine, RecommendOptions, RecommendResult, UserData
```

Existing LunaBot integrations can keep their current namespace:

```python
from sekai_deck_recommend_cpp import (
    DeckRecommendOptions,
    DeckRecommendUserData,
    SekaiDeckRecommend,
)
```

Masterdata, music metadata, and user data remain runtime inputs and are not
bundled into the wheel. The recommendation engine uses Allium's DFS search.

Version `0.0.5` tracks allium-deck `0.0.8`, including the optimized pool
construction path, explicit AVX-512 dispatch on supported x86-64 CPUs, and
portable scalar fallbacks for other targets. `0.0.8` also reads masterdata
that ships `cardParameters` as the game's original per-level rows, in
addition to the grouped per-parameter arrays. Performance depends on the CPU,
account data, activity rules, and candidate pool shape.

## API coverage

The `sekai_deck_recommend_cpp` interface includes the complete LunaBot deck
workflow:

- mutable option, user-data, card, deck, support-deck, and result objects
- single and batch recommendation
- World Bloom support-deck calculation
- area-item upgrade recommendation
- per-music score and event-point calculation
- note-level exact live calculation
- configurable batch worker count

Each recommendation result includes `cost_ms`, the wall-clock time spent in the
native search itself. Batch results report this value independently for every
request.

## Pool reuse

A `recommend` call spends most of its time building the candidate pool and only
a small fraction searching it. When the same user, masterdata and options are
queried repeatedly, build the pool once and search it many times:

```python
pool = engine.build_pool(options)
result = pool.recommend()          # search only
top5 = pool.recommend(limit=5)     # limit and timeout_ms may be overridden
print(pool.card_count)             # candidates in the pool
```

Measured on one dataset (672-card account, `multi` / `score`, 194 candidates):
`engine.recommend()` 4549 us versus `pool.recommend()` 448 us at the median,
about 10x, saving roughly 4.1 ms per call. Both paths return identical decks.

### What a pool is bound to

A pool captures the user data, the masterdata and the options it was built from.
**It does not observe later changes to any of them**, so reusing a stale pool
silently returns results computed from outdated inputs. Rebuild when:

| Change | Effect |
|---|---|
| `update_masterdata` / `update_musicmetas` | every pool for that region is stale |
| the user's cards change (new cards, levels, master ranks) | that user's pools are stale |
| any option other than `limit` / `timeout_ms` | needs its own pool |

`limit` and `timeout_ms` affect only the search stage and can be passed per call.

### Memory

A pool holds its candidate set, search context and resolved card details until
it is released. Measured per pool:

| Account cards | Candidates | Per pool |
|---|---|---|
| 672 | 141-194 | 221-257 KB |
| 1249 | 156-260 | 391-465 KB |

Roughly 0.2-0.5 MB each, so keeping 100 pools costs about 22-47 MB.

### Caller-owned cache

No pool cache is built in: the right bound and the right invalidation depend on
the caller, and pools cost memory that the library should not claim on its own.
A bounded LRU is a few lines:

```python
from collections import OrderedDict


class PoolCache:
    def __init__(self, engine, max_pools=64):
        self._engine = engine
        self._max = max_pools
        self._pools = OrderedDict()

    def recommend(self, key, options, limit=None):
        pool = self._pools.pop(key, None)
        if pool is None:
            pool = self._engine.build_pool(options)
        self._pools[key] = pool                 # newest last
        while len(self._pools) > self._max:
            self._pools.popitem(last=False)     # evict oldest
        return pool.recommend(limit=limit)

    def drop_user(self, user_id):
        for key in [k for k in self._pools if k[0] == user_id]:
            del self._pools[key]

    def clear(self):
        self._pools.clear()
```

`key` must cover everything the pool is bound to; a workable one is
`(user_id, user_data_revision, options_fingerprint)`. Call `drop_user` when that
user's cards change and `clear` after reloading masterdata.

## License

MIT
