# Advisor Memory Architecture / 顾问型记忆架构

## Goal / 目标

Build a memory system that behaves like a long-running advisor.  
构建一个像长期顾问一样工作的记忆系统。

It should:

- remember durable facts and evolving judgments / 记住长期事实和持续演化的判断
- keep recent working context hot / 保持最近工作上下文是热的
- preserve raw source material / 保留原始资料
- retrieve by domain and depth / 按领域和深度检索，而不是整库硬塞进 context

It should also remain readable as a knowledge base in its own right, not only as an agent backend.  
它还必须本身就是一套可读的知识库，而不只是 agent 背后的后端。

## Product Boundary / 产品边界

This system should not split into separate human and agent knowledge bases.  
这套系统不应该拆成一套给人、一套给 agent 的双份知识库。

Use one canonical file-based memory substrate, then expose different read patterns on top of it.  
正确做法是使用同一套基于文件的 canonical memory substrate，再在其上提供不同的读取方式。

Human-facing / 面向人的部分:

- durable pages
- library catalog and pack `index.md`
- raw files

System-facing / 面向系统的部分:

- manifests
- indexes
- routing summaries
- dream-cycle and promotion artifacts

## Two Axes / 两条主轴

The system is organized on two axes at once.  
系统同时沿两条轴组织。

### Axis 1: Durability / 轴一：耐久度

- `raw` — original files / 原始文件
- `working` — recent, active, unresolved material / 最近、活跃、未解决内容
- `distilled` — reusable summaries and concept pages / 可复用的摘要、概念页、项目页
- `canonical` — the few pages that define current truth / 定义当前核心事实的少数页面

### Axis 2: Domain / 轴二：领域

Example domains / 示例领域:

- `product`
- `growth`
- `leadership`
- `ai`
- `engineering`
- `people`
- `companies`
- `projects`
- `personal`

The design is a matrix, not one flat hierarchy.  
设计是一个矩阵，而不是单一树形层级。

## Recommended Memory Layers / 推荐记忆层

### 1. Source Layer / 原始资料层

Store originals here / 原文放在这一层:

- markdown
- transcripts / 转录稿
- PDFs
- exports / 导出文件
- newsletters
- podcast transcripts / 播客转录
- user notes / 用户笔记

This layer must stay easy to read, diff, update, and re-import.  
这一层必须保持易读、可 diff、可更新、可重新导入。

### 2. Index Layer / 索引层

This is the routing layer.  
这是检索路由层。

Keep lightweight metadata / 保持轻量元数据:

- title / 标题
- source / 来源
- date / 日期
- tags / 标签
- entities / 实体
- domain / 领域
- file path / 文件路径
- checksum or version / 校验值或版本
- short abstract / 短摘要

This layer should live in system metadata, not in the main human-facing surface.  
这一层应放在系统元数据里，而不是人类默认浏览的主界面。

### 3. Working Memory Layer / 工作记忆层

This is the short-term layer.  
这是短期层。

Store / 存放:

- current project state / 当前项目状态
- active threads / 活跃话题
- recent conversations / 最近对话
- unresolved questions / 未解决问题
- recent source digests / 最近资料摘要

### 4. Distilled Memory Layer / 蒸馏记忆层

This is the reusable long-term layer.  
这是可复用的长期层。

Store / 存放:

- concept pages / 概念页
- person and company pages / 人物与公司页
- project strategy pages / 项目策略页
- recurring heuristics / 反复复用的方法论
- the user's judgments and adapted frameworks / 用户自己的判断与改造后的框架

### 5. Advisor View Layer / 顾问视图层

This is not a separate store. It is a read pattern.  
这不是单独的存储层，而是一种读取视图。

It assembles / 它会组合:

- relevant distilled memory / 相关长期记忆
- recent working memory / 最近工作记忆
- supporting raw evidence / 支撑性的原始资料

Because durable recall rides on GBrain, the system must refresh the GBrain index after writes.  
因为长期召回依赖 GBrain，所以写入后必须刷新 GBrain 索引。

- git-backed brains: `gbrain sync --repo ... --no-pull --no-embed`
- non-git brains: `gbrain import <brain-root> --no-embed`
- then / 然后: `gbrain embed --stale` only when an OpenAI key is configured / 仅在已配置 OpenAI key 时执行

## Progressive Disclosure / 渐进披露

Progressive disclosure is for routing, not for hiding the source forever.  
渐进披露是为了路由，不是为了永久用摘要替代原文。

Use this ladder / 使用这个梯子:

1. domain router / 领域路由
2. distilled page or index abstract / 长期记忆页或索引摘要
3. working-memory delta if active / 如果主题活跃，再读 working delta
4. locate the best source documents / 定位最相关原文
5. load full raw documents when possible / 尽量加载完整原文
6. use snippets or summaries only when necessary / 只有在必要时才退回片段或摘要

## Automatic Extension / 自动扩展

The user should not hand-author categories for every new corpus.  
用户不应该每来一个新语料就手工建分类。

Expected ingest behavior / 理想导入行为:

1. preserve raw files / 保留原文
2. build manifest and indexes / 建 manifest 和索引
3. infer domains from metadata and content signals / 根据元数据和内容信号推断领域
4. extend taxonomy when coverage is insufficient / 分类不够时自动扩展 taxonomy
5. rebuild indexes with the expanded map / 用扩展后的 taxonomy 重建索引

Recommended split / 推荐拆分:

- `sources/domain_taxonomy.json` — stable base taxonomy / 稳定基础分类
- `sources/domain_taxonomy.generated.json` — auto-induced domains / 自动归纳出来的新分类

## GBrain's Role / GBrain 的角色

Use `gbrain` for / 用于:

- durable page storage / 长期页面存储
- cross-linking / 交叉链接
- hybrid retrieval / 混合检索
- source attribution / 来源归因
- sync and embedding refresh / 同步与 embedding 刷新
- agent-facing operations / agent 操作接口

GBrain is not only a vector store.  
GBrain 不只是向量库。

Without embeddings, GBrain still provides keyword retrieval and durable page operations.  
没有 embeddings 时，GBrain 仍然提供关键词检索和长期页面操作。

## What This Skill Adds / 这个 Skill 额外补了什么

GBrain itself does not fully define a first-class external-library protocol.  
GBrain 本身没有完整定义外部资料库协议。

This skill adds library packs / 这个 skill 补上了 library pack 协议:

- raw sources stay preserved / 原始资料保留
- manifest/index layers sit above raw / 在原文之上构建 manifest 和索引
- distilled memory links back to raw / 长期记忆能回链到原文
- multiple corpora share one routing model / 多个语料共享一套路由模型

## Recommended Layout / 推荐目录结构

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
│   └── libraries/
│       ├── index.md
│       ├── lenny/
│       │   ├── index.md
│       │   ├── raw/
│       │   └── _system/
│       │       ├── manifest.json
│       │       ├── indexes/
│       │       ├── summaries/
│       │       └── domain_suggestions.json
│       ├── personal-notes/
│       └── custom-corpus/
└── inbox/
```

Durable advisor memory lives in normal GBrain page directories.  
长期记忆放在标准 GBrain 页面目录里。

Libraries under `sources/libraries/` are the raw-plus-index substrate.  
`sources/libraries/` 下的内容是原文加索引层。

Human-facing knowledge should prefer / 给人看的知识入口应优先看:

- durable pages such as `projects/`, `concepts/`, `people/`, `companies/`, `ideas/`
- `sources/libraries/index.md`
- each pack's `index.md`
- `raw/` when deeper reading is needed

System-facing metadata should stay under `_system/` so the knowledge base remains readable to humans.  
系统元数据应放在 `_system/` 之下，这样整套知识库对人仍然保持可读。

## Design Rule / 设计原则

Do not think “add another step for another corpus.”  
不要用“每加一个语料就加一步流程”的方式思考。

Think / 应该这样思考:

- one memory substrate / 一个底座
- many registered library packs / 多个已注册资料库
- one shared routing and consolidation protocol / 一套统一的路由与巩固协议
