# Library Packs / 资料库协议

## What A Library Pack Is / 什么是 Library Pack

A library pack is the unit that makes an external corpus usable inside advisor-memory.  
Library pack 是把外部语料接入 advisor-memory 的基本单位。

Examples / 例子:

- Lenny newsletter and podcast archive / Lenny 的 newsletter 与播客库
- your own notes export / 你自己的笔记导出
- a product interview archive / 产品访谈库
- a research paper collection / 论文或研究资料集
- customer call transcripts / 客户访谈或电话转录

Each pack is queryable and updateable without flattening raw files into one blob.  
每个 pack 都可查询、可更新，同时不把原文压扁成单一大文本。

Each pack should also remain legible to a human reader.  
每个 pack 也应该保持对人可读。

That means / 这意味着:

- `raw/` stays visible
- the pack root exposes `index.md`
- machine routing data stays under `_system/`

## Required Properties / 必备属性

Every pack should provide / 每个 pack 至少应提供:

- preserved originals / 原始资料保留
- stable file paths / 稳定文件路径
- metadata manifest / 元数据 manifest
- searchable indexes / 可检索索引
- summaries for routing / 供路由用的摘要
- backlinks from durable memory to raw files / 从长期记忆回链到原文

## Recommended Structure / 推荐目录结构

```text
sources/libraries/<pack-name>/
├── index.md
├── raw/
└── _system/
    ├── manifest.json
    ├── indexes/
    │   ├── by_date.json
    │   ├── by_tag.json
    │   ├── by_entity.json
    │   ├── by_type.json
    │   └── by_domain.json
    ├── summaries/
    │   ├── file-level/
    │   └── theme-level/
    └── domain_suggestions.json
```

### `index.md`

This is the human-facing entrypoint for a pack.  
这是给人读的 pack 入口页。

It should surface / 它应暴露:

- what this pack contains / 这个 pack 里有什么
- recommended first reads / 推荐先读
- key questions / 关键问题入口
- representative files by domain / 各领域代表文件

### `raw/`

Store originals here.  
原始文件存这里。

- keep filenames stable / 保持文件名稳定
- if upstream changes, overwrite with checksum tracking or explicit versioning / 上游变更时用 checksum 或版本记录
- preserve provenance / 保留来源和上下文

### `_system/manifest.json`

Track one row per source item.  
每个源文件对应一条记录。

Typical fields / 常见字段:

- `id`
- `title`
- `type`
- `source_root`
- `raw_rel_path`
- `source_checksum`
- `imported_at`
- `updated_at`
- `tags`
- `guest` or `entities`
- `domain`
- `abstract`

### `_system/indexes/`

Indexes are routing aids, not the final truth.  
索引是路由层，不是最终真相层。

Use them to answer / 用来回答:

- what files talk about pricing / 哪些文件在讲 pricing
- what sources mention a person / 哪些资料提到某个人
- what changed this month / 本月新增了什么
- what belongs to a domain / 哪些内容属于某领域

### `_system/summaries/`

Keep two levels / 保持两层:

- file-level summaries / 单文件摘要
- theme-level map / 主题级地图与轻量导航

These are routing layers, not mandatory substitutes for the source.  
这些层是导航层，不是原文替代品。

When context allows, final reasoning should prefer full raw files.  
只要 context 允许，最终推理应优先回到完整原文。

The library map should include / `library-map` 至少应包含:

- recommended first reads / 推荐先读
- key entry questions / 关键提问入口
- representative files by domain / 每个领域的代表文件

### `_system/domain_suggestions.json`

Keep auto-generated classification suggestions here.  
自动生成的分类建议放这里。

This is system metadata, not a human-facing page.  
这是系统元数据，不是给人直接浏览的主页面。

## Lenny As A Library Pack / 把 Lenny 当作一个 Pack

Lenny should be treated as a proper library pack, not a one-off search hack.  
Lenny 不该被当作一次性的搜索 skill，而应是标准化资料库。

Lenny already gives you / Lenny 原本就有:

- preserved raw markdown
- metadata index
- search and fulltext access
- direct file reading

Advisor-memory adds / advisor-memory 额外补上:

- named pack registration / 命名 pack 注册
- a shared routing protocol / 统一路由协议
- promotion rules into durable memory / 进入长期记忆的提升规则
- dream-cycle maintenance / dream cycle 维护
- cross-pack search / 跨 pack 联搜

## Promotion Rule / 提升规则

Not everything in a pack belongs in durable memory.  
不是 pack 里的所有内容都应该进入长期记忆。

Promote only when / 仅在以下情况下提升:

- the idea affected a real decision / 观点影响了真实决策
- the same idea was used repeatedly / 同一观点被重复使用
- the user meaningfully adapted or critiqued it / 用户对其做了明显吸收或批判
- the idea fills a durable gap / 它填补了长期记忆中的真实空白

When promoting, store backlinks to / 提升时保留回链:

- pack name
- source title
- date
- raw file path

## Update Protocol / 更新协议

When a pack changes / 当 pack 收到新文件或旧文件发生变化:

1. preserve the raw file / 保留原文
2. update checksum and metadata / 更新 checksum 和元数据
3. infer or extend domains / 推断或扩展 domain
4. refresh `_system/indexes/` / 刷新 `_system/indexes/`
5. refresh `_system/summaries/` and pack `index.md` / 刷新 `_system/summaries/` 和 pack 根目录 `index.md`
6. flag durable pages for consolidation / 标记需要巩固的长期页面

After each successful refresh, update GBrain.  
每次成功刷新后，都应更新 GBrain。

- git-backed brain: `gbrain sync --repo ... --no-pull --no-embed`
- non-git brain: `gbrain import <brain-root> --no-embed`
- then / 然后: `gbrain embed --stale` only when an OpenAI key is configured / 仅在已配置 OpenAI key 时执行

## Retrieval Contract / 检索契约

When the agent chooses a pack, it should / 当 agent 选择一个 pack 时应:

1. hit metadata or indexes first / 先查元数据或索引
2. use summaries only to narrow candidates / 用 summary 缩小候选
3. read full raw sources for the best candidates / 对最相关候选读取完整原文
4. cite the exact source item when answering / 回答时引用精确来源

For multi-pack questions, use `search_library_pack.py --all-packs`.  
对于多库问题，使用 `search_library_pack.py --all-packs`。
