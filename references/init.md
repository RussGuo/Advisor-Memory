# Initialization / 初始化

## Goal / 目标

Stand up a usable Lenny-first advisor memory system in one pass.  
一次性搭起一个可用的、以 Lenny 为第一库的顾问型记忆系统。

## Choose The Mode First / 先确认运行模式

Do this before setup so expectations are correct from day one.  
在开始初始化前先确认这一点，避免从第一天就误解系统能力。

- pack-first mode / pack 优先模式: no OpenAI embedding key required. advisor-memory still works as a Lenny-style source memory system with pack registration, raw preservation, `search/fulltext/read`, cross-pack consult, and GBrain keyword search. / 不需要 OpenAI embedding key。此时 advisor-memory 仍然可以作为一个 Lenny 风格的资料记忆系统正常工作，支持 pack 注册、原文保留、`search/fulltext/read`、跨 pack 咨询以及 GBrain 关键词检索。
- semantic mode / 语义模式: if you add an OpenAI key, `gbrain embed --stale` unlocks stronger `gbrain query` semantic retrieval for durable memory. / 如果配置 OpenAI key，`gbrain embed --stale` 会为长期记忆解锁更强的 `gbrain query` 语义检索。

The system must not fail just because embeddings are unavailable.  
系统不能因为没有 embeddings 就失效。

Expected result / 结果应包括:

- `gbrain` is initialized / `gbrain` 已初始化
- the brain directory exists / brain 目录已创建
- Lenny is registered as the first library pack / Lenny 已注册为第一个 pack
- raw files remain directly accessible / 原文可直接访问
- index and summary layers are generated / 索引和摘要层已生成
- an agent snippet is produced / 已生成 agent 指令片段
- the knowledge base is immediately human-browsable / 这套知识库从第一天起就应能被人直接浏览

## Preconditions / 前置条件

- `gbrain` is installed and runnable / `gbrain` 已安装且可运行
- the Lenny repo exists locally / 本地已有 Lenny 仓库
- you have chosen a brain root directory / 已确定 brain root
- optional: an OpenAI key if you want semantic retrieval on day one / 可选：如果你希望第一天就有语义检索，再准备 OpenAI key

Install `gbrain` / 安装 `gbrain`:

```bash
bun add -g github:garrytan/gbrain
gbrain --version
```

## Installation Targets / 安装位置

This skill works in both Codex and Claude-style setups.  
这个 skill 同时兼容 Codex 和 Claude 风格的本地 skill 目录。

Typical locations / 常见位置:

- Codex: `${CODEX_HOME:-$HOME/.codex}/skills/advisor-memory`
- Claude: `~/.claude/skills/advisor-memory`

You can run scripts from the skill root, or call them by absolute path.  
可以在 skill 根目录执行脚本，也可以用绝对路径执行。

Optional default config / 可选默认配置:

- `ADVISOR_BRAIN_ROOT=/absolute/path/to/brain`
- `~/.advisor-memory/config.json`

Example / 示例:

```json
{
  "brain_root": "/absolute/path/to/brain",
  "gbrain_cmd": "gbrain"
}
```

If `gbrain` is not on `PATH`, you can point advisor-memory at it with:

- `ADVISOR_GBRAIN_CMD="gbrain"`
- or `~/.advisor-memory/config.json`

## One-Time Sequence / 一次性初始化流程

### 1. Initialize GBrain / 初始化 GBrain

```bash
gbrain init
gbrain doctor --json
```

Use the normal GBrain flow for DB setup.  
数据库初始化走正常 GBrain 流程。

Embeddings are optional at setup time.  
初始化阶段 embedding 是可选的。

If no OpenAI key is configured yet, advisor-memory will still import text, register packs, and answer via keyword/fulltext/raw retrieval. It will only return an embedding warning instead of failing hard.  
如果暂时没有 OpenAI key，advisor-memory 仍然会导入文本、注册 pack，并通过 keyword/fulltext/raw 检索正常工作，只会返回 embedding warning，不会直接失败。

### 2. Bootstrap the Lenny-first layout / 建立 Lenny-first 布局

```bash
python3 scripts/init_lenny_first_memory.py \
  --brain-root /absolute/path/to/brain \
  --lenny-root /absolute/path/to/lennys-podcast-newsletter
```

If `gbrain` is missing but `bun` exists, bootstrap can try installing it:

```bash
python3 scripts/init_lenny_first_memory.py \
  --brain-root /absolute/path/to/brain \
  --lenny-root /absolute/path/to/lennys-podcast-newsletter \
  --install-gbrain
```

By default this will / 默认会做这些事:

- create `working/` and `sources/libraries/`
- create `working/project-memory-reviews/` for consult-generated project update proposals
- register `lenny` in `sources/libraries/registry.json`
- create `sources/libraries/index.md` as the human-facing library catalog / 创建 `sources/libraries/index.md` 作为给人看的资料库目录
- create a symlinked `raw/` pointing at Lenny `references/`
- generate `lenny/index.md` as the human-facing pack entry / 生成 `lenny/index.md` 作为给人看的 pack 入口
- generate `_system/manifest.json`
- generate `_system/indexes/` by date, tag, guest, entity, type, and domain
- generate `_system/summaries/` file-level stubs and theme map
- generate:
  - `AGENTS.advisor-memory.snippet.md`
  - `CLAUDE.advisor-memory.snippet.md`
  - `advisor-memory.instructions.snippet.md`
- refresh GBrain after bootstrap
- attempt `gbrain embed --stale` only when an OpenAI key is configured / 只有在配置了 OpenAI key 时才尝试执行 `gbrain embed --stale`

After initialization, future corpora should usually enter through:

```bash
python3 scripts/smart_ingest_library_pack.py \
  --brain-root /absolute/path/to/brain \
  --source /absolute/path/to/new-corpus
```

If you want a physical copy instead of a symlink:

```bash
python3 scripts/init_lenny_first_memory.py \
  --brain-root /absolute/path/to/brain \
  --lenny-root /absolute/path/to/lennys-podcast-newsletter \
  --copy-raw
```

### 3. Attach the agent rules / 挂载 agent 规则

Review:

- `/absolute/path/to/brain/AGENTS.advisor-memory.snippet.md`
- `/absolute/path/to/brain/CLAUDE.advisor-memory.snippet.md`
- `/absolute/path/to/brain/advisor-memory.instructions.snippet.md`

Copy the relevant rules into `AGENTS.md`, `CLAUDE.md`, or the active harness instructions.  
把合适的片段拷到当前 agent 的指令文件里。

### 4. Verify the pack / 验证 pack 是否就绪

Check / 检查:

- `sources/libraries/registry.json`
- `sources/libraries/index.md`
- `sources/libraries/lenny/index.md`
- `sources/libraries/lenny/_system/manifest.json`
- `sources/libraries/lenny/_system/indexes/by_tag.json`
- `sources/libraries/lenny/_system/indexes/by_entity.json`
- `sources/libraries/lenny/_system/summaries/file-level/`
- `sources/libraries/lenny/_system/summaries/theme-level/library-map.md`

Human browsing path / 人工浏览路径:

- start with `sources/libraries/index.md`
- then open `sources/libraries/lenny/index.md`
- then open `raw/` files when deeper reading is needed

This skill does not require a separate viewer product in order to be useful to humans.  
这个 skill 不需要额外的人类界面产品，光靠文件系统入口就应该对人有用。

Integrated query path / 集成查询方式:

```bash
python3 scripts/search_library_pack.py \
  --brain-root /absolute/path/to/brain \
  --pack-name lenny \
  search "product-market fit" --limit 5
```

Cross-pack query path / 跨 pack 联合搜索:

```bash
python3 scripts/search_library_pack.py \
  --brain-root /absolute/path/to/brain \
  --all-packs \
  search "onboarding" --limit 10
```

Default advisory consult path / 默认顾问检索路径:

```bash
python3 scripts/consult_advisor_memory.py \
  --brain-root /absolute/path/to/brain \
  "How should we improve onboarding and PMF?"
```

If the query mentions a known project page, advisor-memory should automatically use that project as the primary context.  
如果问题里提到了一个已知项目页，advisor-memory 应自动把该项目作为主上下文。

Project-bound advisory consult path / 绑定项目页的咨询路径:

```bash
python3 scripts/consult_advisor_memory.py \
  --brain-root /absolute/path/to/brain \
  --project-target projects/project-a.md \
  "How should we improve onboarding and PMF?"
```

If the consult emits a project-memory review, confirm with the user before applying:

```bash
python3 scripts/update_project_memory.py \
  --brain-root /absolute/path/to/brain \
  --review-file /absolute/path/to/brain/working/project-memory-reviews/review.json \
  --accept default
```

## What Bootstrap Does Not Do / Bootstrap 不会做什么

It does not / 它不会:

- summarize full transcripts with an LLM / 用 LLM 深度总结整库全文
- decide all durable promotions for you / 自动决定所有长期记忆提升
- rewrite `AGENTS.md` automatically / 自动改写你的 `AGENTS.md`
- import private notes into canonical pages by itself / 自动把私有笔记写成 canonical pages

Those are still agent decisions after initialization.  
这些仍然属于初始化完成后的 agent 决策。

## Next Step / 初始化后的下一步

After Lenny is live, add one more pack.  
Lenny 接好以后，再接一个你自己的 pack。

Examples / 例如:

- personal notes / 个人笔记
- interview archive / 访谈归档
- project docs / 项目文档
- research dump / 研究资料

Use the same contract / 保持同一协议:

- preserve raw / 保留原文
- generate manifest / 生成 manifest
- generate indexes / 生成索引
- extend domains automatically / 自动扩展 domain
- create summary and map layers / 生成 summary 和 library map
- promote selectively into durable memory / 有选择地提升到长期记忆
