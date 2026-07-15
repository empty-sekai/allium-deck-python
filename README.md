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

## License

MIT
