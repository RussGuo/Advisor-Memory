# Advisor Memory

A bilingual 中英混合 advisor-style memory skill for Codex and Claude-style agents.

`advisor-memory` turns external corpora, project notes, and durable judgment pages into one shared knowledge base for both humans and agents. It uses [GBrain](https://github.com/garrytan/gbrain) as the durable memory substrate, but keeps the source library human-readable and usable even without embeddings.

## What It Is

This is not just a search wrapper around a document folder.

It is a memory system with three jobs:

- preserve raw source material
- route questions across multiple registered corpora
- accumulate durable project and concept memory over time

It is designed for cases like:

- “Lenny 怎么说 onboarding / PMF / pricing?”
- “把这批访谈资料吸收到记忆里”
- “结合我当前项目，给我一个带参考依据的建议”
- “跨多个库一起搜，不要让我先选 pack”

## Product Model

The core design rule is simple:

- one canonical knowledge base
- human-readable by default
- agent-optimized routing on top

So this system does **not** create one memory base for humans and another for agents.

Instead, it keeps:

- human-facing entrypoints in normal markdown pages and pack `index.md`
- machine-facing metadata under `_system/`
- raw files preserved in `raw/`

## Core Capabilities

- Layered memory: `working/` for short-term context, durable pages for long-term memory, `sources/libraries/` for registered corpora.
- Human-readable packs: every pack exposes an `index.md`; metadata and routing artifacts live under `_system/`.
- Broad advisory retrieval by default: users should not need to choose a pack first.
- Project-aware consults: if a known project is mentioned, the project page becomes the primary frame and external libraries become evidence.
- Raw-first reasoning: summaries are used for routing; full raw documents are preferred for real reasoning whenever possible.
- Automatic pack registration: new corpora can be ingested and indexed without hand-building the structure.
- Cross-pack search: the system can route across multiple packs instead of treating each corpus as a separate workflow.
- Dream cycle maintenance: stale summaries, maps, and promotion queues can be refreshed automatically.
- Embedding-optional day one: without an OpenAI embedding key, the system still works in keyword/fulltext/raw mode.

## Directory Model

```text
brain/
├── people/
├── companies/
├── projects/
├── concepts/
├── ideas/
├── working/
│   ├── active-topics/
│   ├── recent-conversations/
│   ├── pending-promotions/
│   └── project-memory-reviews/
├── sources/
│   ├── domain_taxonomy.json
│   ├── domain_taxonomy.generated.json
│   └── libraries/
│       ├── index.md
│       └── <pack>/
│           ├── index.md
│           ├── raw/
│           └── _system/
│               ├── manifest.json
│               ├── indexes/
│               ├── summaries/
│               └── domain_suggestions.json
└── inbox/
```

Human-facing knowledge usually starts from:

- `projects/`, `concepts/`, `people/`, `companies/`, `ideas/`
- `sources/libraries/index.md`
- each pack’s `index.md`
- `raw/` when deeper reading is needed

## How It Works

### 1. Ingest

You give the system a file or a corpus.

It preserves the raw source, registers it as a library pack, builds indexes and summaries, creates a human-facing `index.md`, and keeps machine metadata under `_system/`.

### 2. Consult

You ask a question.

The default behavior is:

1. read durable memory first
2. detect relevant domains
3. route across the most relevant packs
4. drill into the best raw sources
5. produce an advisory answer instead of a corpus summary

If the question mentions a known project, the project page becomes the primary context.

### 3. Write Back

If a consult produces a durable insight, the system can:

- emit a candidate project-memory review
- ask for confirmation
- write confirmed updates back into `projects/...`

### 4. Consolidate

During a dream cycle, the system can:

- refresh stale routing artifacts
- emit promotion queues
- refresh GBrain

## Quick Start

### Prerequisites

- Python 3
- `gbrain`
- a local corpus to ingest, for example the Lenny archive

Install `gbrain`:

```bash
bun add -g github:garrytan/gbrain
gbrain --version
```

### Initialize a Lenny-first brain

```bash
python3 scripts/init_lenny_first_memory.py \
  --brain-root /absolute/path/to/brain \
  --lenny-root /absolute/path/to/lennys-podcast-newsletter
```

### Ask a broad advisory question

```bash
python3 scripts/consult_advisor_memory.py \
  --brain-root /absolute/path/to/brain \
  "How should we improve onboarding and PMF?"
```

### Ingest a new corpus

```bash
python3 scripts/smart_ingest_library_pack.py \
  --brain-root /absolute/path/to/brain \
  --source /absolute/path/to/new-corpus
```

### Search across all packs

```bash
python3 scripts/search_library_pack.py \
  --brain-root /absolute/path/to/brain \
  --all-packs search "onboarding product-market fit" --limit 10
```

### Run a dream cycle

```bash
python3 scripts/dream_cycle.py --brain-root /absolute/path/to/brain --apply
```

## No Embedding Required

This repo is designed to be useful on day one without an OpenAI embedding key.

Without embeddings, it still supports:

- pack registration
- raw preservation
- `search / fulltext / read`
- cross-pack consult
- GBrain keyword retrieval

If you later add an OpenAI key, `gbrain embed --stale` enables stronger semantic retrieval on top of the same workflow.

## Project Memory

Project pages are intended to grow naturally.

The system does **not** force a rigid project dashboard template. Instead:

- `projects/project-a.md` acts as the durable project memory page
- consults can generate candidate updates
- confirmed updates can be written back
- external libraries serve as evidence, not as the primary project memory

This keeps project memory useful without over-structuring it.

## Human Use vs Agent Use

This repository deliberately keeps the knowledge base usable for both:

- Humans can browse markdown pages, pack indexes, and raw files directly.
- Agents can use `_system/manifest.json`, `_system/indexes/`, and `_system/summaries/` for routing and automation.

No separate viewer product is required for the system to be usable by humans.

## Repository Contents

- `SKILL.md` — the skill contract and operating rules
- `agents/openai.yaml` — skill metadata for OpenAI/Codex-style environments
- `references/` — architecture, init, pack protocol, workflows
- `scripts/` — deterministic runtime and maintenance scripts

## Recommended Entry Points

- Setup: `scripts/init_lenny_first_memory.py`
- Ingest: `scripts/smart_ingest_library_pack.py`
- Broad consult: `scripts/consult_advisor_memory.py`
- Low-level pack search: `scripts/search_library_pack.py`
- Consolidation: `scripts/dream_cycle.py`
- Durable promotion: `scripts/promote.py`
- Project-memory writeback: `scripts/update_project_memory.py`

## Status

`advisor-memory` is a production-usable skill focused on:

- long/short-term layered memory
- human-readable source libraries
- broad advisory retrieval
- project-aware recommendations

Current scope is intentionally narrow:

- no standalone UI product
- no built-in transcript/audio transcription layer
- domain extension is heuristic-first rather than fully semantic

## Read More

- [SKILL.md](./SKILL.md)
- [references/architecture.md](./references/architecture.md)
- [references/init.md](./references/init.md)
- [references/library-packs.md](./references/library-packs.md)
- [references/workflows.md](./references/workflows.md)
