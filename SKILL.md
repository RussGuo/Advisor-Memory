---
name: advisor-memory
description: >-
  Build and operate a bilingual 中英混合 advisor-style memory system on top of
  GBrain. Use it to initialize layered long/short-term memory, ingest and
  register new corpora like Lenny, preserve raw sources, generate indexes and
  library maps, expose a human-readable knowledge base, run cross-pack search,
  and run dream cycle maintenance. Also use it as the default broad advisory
  retrieval layer: when the user asks for advice, synthesis, or “what does my
  memory/library say”, search durable memory plus the most relevant packs
  automatically unless the user explicitly narrows scope. No OpenAI embedding
  key is required for day-one operation; the skill must still work in
  keyword/fulltext/raw mode. 常见触发包括 “X 怎么说”, “这个库里有没有提到”,
  “把这批资料喂进去”, “跨多个库一起搜”, “结合这个知识库回答”, “这个项目该怎么做”,
  and “跑一遍 dream cycle”.
---

# Advisor Memory / 顾问型记忆系统

## Overview / 总览

Use this skill to run one unified advisor-style memory system.  
用这个 skill 把多个知识库、长期记忆、短期工作记忆统一成一个顾问型系统。

Core properties / 核心特性:

- layered memory / 分层记忆，不是一个平的知识桶
- domain routing / 领域路由，产品问题不会扫全库
- raw preservation / 原文保留，原始资料始终可读可回溯
- progressive disclosure for routing / 渐进披露只用于路由
- full-document recall for reasoning / 真正推理时优先加载完整原文
- automatic pack registration / 新语料自动注册为 library pack
- cross-pack search / 支持跨 pack 联合搜索
- dream-cycle maintenance / 支持夜间巩固与修复

This skill uses `gbrain` as the durable memory substrate.  
这个 skill 以 `gbrain` 作为长期记忆底座。

## Product Definition / 产品定义

Treat this as a production skill with one shared knowledge base for both humans and agents.  
把它当成一个可发布的生产级 skill：人和 agent 共享同一套知识库，而不是各维护一份。

Product promise / 产品承诺:

- one canonical knowledge base / 一套 canonical knowledge，而不是两套副本
- human-readable by default / 默认对人可读，不需要额外 viewer 才能使用
- agent-optimized routing without hiding the source / agent 可以高效路由，但不把原文藏起来
- broad advisory retrieval by default / 默认做全局顾问检索，不要求用户先选 pack

Human-facing entrypoints / 面向人的入口:

- durable pages such as `projects/`, `concepts/`, `people/`, `companies/`, `ideas/`
- `sources/libraries/index.md`
- each pack's `index.md`
- `raw/` files when deeper reading is needed

## Startup Modes / 启动模式

Choose the operating mode first.  
先确认你现在处于哪种模式。

- day-one pack mode / 首日 pack 模式: no OpenAI embedding key required. The system still imports text, registers packs, preserves raw files, supports `search/fulltext/read`, cross-pack consult, and GBrain keyword search. / 不需要 OpenAI embedding key，系统仍然可以导入文本、注册 pack、保留原文、执行 `search/fulltext/read`、跨库咨询，以及使用 GBrain 关键词检索。
- full semantic mode / 完整语义模式: add an OpenAI key and run `gbrain embed --stale` to unlock stronger `gbrain query` semantic retrieval on top of the same pack workflow. / 配置 OpenAI key 并运行 `gbrain embed --stale` 后，在同一套 pack 工作流上额外获得更强的 `gbrain query` 语义检索。

If embeddings are missing, advisor-memory must still behave like a stronger Lenny-style skill, not fail closed.  
如果没有 embedding，advisor-memory 也必须像一个更强的 Lenny 类 skill 一样正常工作，而不是直接失效。

## Read This First / 优先阅读

- System model and storage layout / 系统模型与目录结构: [references/architecture.md](references/architecture.md)
- Initialization / 初始化流程: [references/init.md](references/init.md)
- Library pack protocol / 资料库协议: [references/library-packs.md](references/library-packs.md)
- Workflows / 工作流: [references/workflows.md](references/workflows.md)

## Natural Trigger Cues / 自然触发线索

Use this skill by default when the user / 当用户出现以下意图时，默认使用本 skill:

- asks what a registered corpus says about a topic / 询问某个已注册知识库对某话题怎么说
- drops a file or folder and wants it absorbed into memory / 丢一个文件或文件夹，希望自动吸收到记忆系统里
- asks to refresh, update, or extend a source library / 想更新、扩充、刷新某个资料库
- wants advice that should combine durable memory with source archives / 希望回答同时结合长期记忆和原始资料库
- asks to search multiple packs together / 希望跨多个 pack 联合搜索
- asks to run maintenance or dream cycle / 希望跑一遍维护或 dream cycle
- has just installed the skill and asks what it is or how to initialize it / 刚安装完 skill，询问这是什么、第一步怎么初始化

Do not wait for exact trigger phrases.  
不要死等某个固定触发词。

If the user is clearly asking for a memory-backed answer, project advice, cross-corpus synthesis, or corpus ingest, this skill should activate naturally.  
只要用户明显是在要“基于记忆的回答”“项目建议”“跨资料综合判断”或“吸收新资料”，就应该自然触发这个 skill。

Typical cues / 常见触发词:

- "X 怎么说"
- "这个库里有没有提到"
- "把这批资料喂进去"
- "把这个文件夹吸收到记忆里"
- "更新这个资料库"
- "跨多个库一起搜"
- "结合这个知识库回答"
- "跑一遍 dream cycle"

## Core Invariants / 核心不变量

- `gbrain` stores durable, cross-linked memory / `gbrain` 负责长期、可交叉引用的记忆
- every imported corpus keeps its original files / 每个导入库都保留原文
- every library has a human-facing `index.md` plus machine metadata under `_system/` / 每个资料库都有给人看的 `index.md`，机器元数据则放在 `_system/`
- every library has manifest, index, and summary layers / 每个资料库都有 manifest、索引、summary 层
- every library gets a lightweight library map / 每个资料库导入时都会生成轻量地图
- new packs are indexed automatically / 新 pack 自动生成索引
- if current domains are insufficient, the taxonomy extends automatically / 现有分类不够时自动扩展 taxonomy
- retrieval is domain-first and index-first / 检索先按领域，再按索引路由
- once relevant files are known, prefer full raw documents / 一旦定位到相关文件，优先加载完整原文
- user corrections override imported material immediately / 用户修正优先于导入资料
- after writes, refresh GBrain / 写入后要刷新 GBrain

GBrain refresh rule / GBrain 刷新规则:

- git-backed brain: `gbrain sync --repo ... --no-pull --no-embed`
- non-git brain: `gbrain import <brain-root> --no-embed`
- then / 然后: `gbrain embed --stale` when an OpenAI key is configured / 仅在已配置 OpenAI key 时执行

## Operating Modes / 运行模式

### 1. Setup / 初始化

Use when the system is being installed or restructured.  
用于首次安装或重构记忆系统。

- initialize `gbrain`
- create or validate the brain layout / 创建或校验 brain 目录
- inject rules into `AGENTS.md`, `CLAUDE.md`, or equivalent / 把运行规则写入 agent 指令
- import existing memory and starting packs / 导入已有记忆与初始资料库
- register Lenny as the first pack / 把 Lenny 注册为第一个 pack

First-run rule / 首次使用规则:

- if the user just installed the skill, first explain the skill in 3-5 lines / 如果用户刚装好 skill，先用 3-5 行解释它是干什么的
- then default to `scripts/bootstrap_advisor_memory.py` instead of making the user assemble the setup manually / 然后默认走 `scripts/bootstrap_advisor_memory.py`，不要让用户自己拼初始化命令
- after bootstrap, tell the user the first 3 things to do next: consult, search, ingest / bootstrap 结束后，要告诉用户接下来最先做的 3 件事：咨询、搜索、导入

### 2. Ingest / 导入

Use when the user gives new documents, notes, exports, or a corpus.  
当用户给你新的文档、笔记、访谈库或资料目录时使用。

- preserve originals / 保留原文
- infer pack identity and source type / 推断 pack 身份与来源类型
- auto-generate manifest, indexes, summaries, library map / 自动生成结构层
- extend domains if the corpus is outside the current taxonomy / 现有 domain 不够时自动扩展
- promote only justified durable insights / 只把值得长期保留的洞见写入长期记忆

### 3. Consult / 咨询回答

Use when answering a question or giving advice.  
用于检索、分析、咨询式回答。

- default to advisor-wide consult unless the user explicitly narrows scope / 默认做全局顾问检索，除非用户明确要求缩小范围
- load the right domain memory first / 先读正确的领域长期记忆
- if the question mentions a known project, treat `projects/...` as the primary frame / 如果问题提到一个已知项目，就把 `projects/...` 当成主上下文
- use summaries and indexes only for routing / summary 和 index 只负责路由
- read full raw documents when feasible / 在 context 允许时读完整原文
- compare multiple packs when useful / 有必要时跨多个 pack 联合检索

Default consult contract / 默认咨询契约:

- the user should not have to choose a pack first / 不要求用户先选 pack
- broad advice should search the full advisor memory by default / 广义建议默认搜全量顾问记忆
- pack-specific retrieval is a precision feature, not a prerequisite / 指定 pack 是精准功能，不是前置条件
- if a project is in play, answer with a project recommendation, not a corpus summary / 如果问题和项目有关，输出项目建议，不要只做资料摘要

### 4. Consolidate / 巩固维护

Use during nightly or periodic maintenance.  
用于夜间或周期性巩固。

- sweep recent signals / 扫描近期信号
- refresh stale summaries and library maps / 修复过期摘要和库地图
- emit a promotion queue / 生成待提升队列
- refresh GBrain / 刷新 GBrain

## When To Write Back / 什么时候写回长期记忆

Write into durable memory when / 满足以下任一条件时写回长期记忆:

- the user states a durable fact, decision, or judgment / 用户给出了稳定事实、决策、判断
- a source changes an active recommendation or project / 某资料改变了当前建议或项目判断
- a pattern repeats across sessions or documents / 某模式在多次会话或多篇资料中重复出现
- an external idea becomes part of the user's own thinking / 外部观点已经被用户吸收成自己的方法

Do not bulk-copy raw corpus files into durable memory.  
不要把原始资料整篇整篇塞进长期记忆。

## Retrieval Rule / 检索顺序

For any question, use this order / 对任何问题按这个顺序执行:

1. identify the domain / 识别领域
2. load distilled memory / 读取长期蒸馏记忆
3. load working memory if active / 若主题正在进行，再读 working memory
4. search the relevant pack or packs / 搜相关 pack，必要时跨 pack 联搜
5. load the most relevant full raw files / 加载最相关的完整原文
6. fall back to summaries only when speed or token budget demands it / 只有在速度或 token 受限时才退回摘要

## Minimum Commands / 最小命令集

```bash
gbrain search "topic"
gbrain get <slug>
gbrain query "question"
# non-git brain / 非 git brain
gbrain import /path/to/brain --no-embed
# git-backed brain / git-backed brain
gbrain sync --repo /path/to/brain --no-pull --no-embed
gbrain embed --stale
python3 scripts/init_lenny_first_memory.py --brain-root /path/to/brain --lenny-root /path/to/lennys-podcast-newsletter
python3 scripts/bootstrap_advisor_memory.py --brain-root ~/brain --lenny-root /path/to/lennys-podcast-newsletter --install-gbrain
python3 scripts/smart_ingest_library_pack.py --brain-root /path/to/brain --source /path/to/new-corpus
python3 scripts/register_library_pack.py --brain-root /path/to/brain --pack-name marketing-interviews --source-root /path/to/marketing-corpus
python3 scripts/consult_advisor_memory.py --brain-root /path/to/brain "How should we improve onboarding and PMF?"
python3 scripts/consult_advisor_memory.py --brain-root /path/to/brain --project-target projects/project-a.md "How should we improve onboarding and PMF?"
python3 scripts/search_library_pack.py --brain-root /path/to/brain --pack-name lenny search "query" --limit 5
python3 scripts/search_library_pack.py --brain-root /path/to/brain --all-packs search "query" --limit 10
python3 scripts/search_library_pack.py --brain-root /path/to/brain --all-packs fulltext "phrase" --limit 10
python3 scripts/search_library_pack.py --brain-root /path/to/brain --pack-name lenny read "03-podcasts/file.md" --lines 250
python3 scripts/dream_cycle.py --brain-root /path/to/brain
python3 scripts/dream_cycle.py --brain-root /path/to/brain --apply
python3 scripts/promote.py --brain-root /path/to/brain --item working:working/pending-promotions/note.md --target concepts/pmf.md
python3 scripts/update_project_memory.py --brain-root /path/to/brain --review-file /path/to/brain/working/project-memory-reviews/review.json --accept default
```

Notes / 说明:

- Run from the skill root, or use absolute paths / 可在 skill 根目录执行，也可用绝对路径
- `smart_ingest_library_pack.py` is the default ingest entrypoint / 默认导入口是 `smart_ingest_library_pack.py`
- `bootstrap_advisor_memory.py` is the preferred first-run entrypoint after installation / 安装后的首次初始化优先走 `bootstrap_advisor_memory.py`
- `consult_advisor_memory.py` is the default consult entrypoint for broad advisory questions / 广义咨询问题默认走 `consult_advisor_memory.py`
- without embeddings, `consult_advisor_memory.py` should still run in keyword-first mode and rely on pack metadata/fulltext/raw reads / 没有 embeddings 时，`consult_advisor_memory.py` 也应以 keyword-first 模式运行，并依赖 pack metadata/fulltext/raw reads
- if a known project is mentioned, the answer should be recommendation-first for that project, not summary-first about the libraries / 如果提到了已知项目，回答应以该项目的建议为先，而不是先做资料摘要
- for project-bound consults, pass `--project-target projects/project-a.md` so the consult emits candidate project-memory updates that must be confirmed before applying / 对绑定项目的咨询，传 `--project-target projects/project-a.md`，让 consult 生成候选项目记忆更新，并在应用前确认
- `search_library_pack.py --all-packs` is the low-level cross-pack runtime path / `search_library_pack.py --all-packs` 是底层跨 pack 联搜入口
- `dream_cycle.py --apply` will auto-refresh stale pack artifacts and write a promotion queue / `dream_cycle.py --apply` 会自动修复过期结构并生成待提升队列
- `promote.py` is the executable promotion bridge from queue items or source items into durable pages / `promote.py` 是把 queue item 或 source item 提升为长期页面的可执行桥梁
- `update_project_memory.py` applies a confirmed consult review into `projects/...` durable pages / `update_project_memory.py` 会把确认过的咨询回顾写入 `projects/...` 长期页面
- `--brain-root` can be omitted if `ADVISOR_BRAIN_ROOT` or `~/.advisor-memory/config.json` is set / 如果已配置默认 brain root，可省略 `--brain-root`
- for human browsing, start with `sources/libraries/index.md` and each pack `index.md` / 人工浏览时，从 `sources/libraries/index.md` 和各 pack 的 `index.md` 开始

## Example Requests / 示例请求

- "把我现在的 notes、聊天总结和 Lenny 语料统一成一个分层记忆系统。"
- "我刚喂给你一批产品访谈，把原文保存下来，并更新产品域记忆。"
- "结合我当前项目，从产品域记忆和 Lenny 库里一起给建议。"
- "跨多个库一起搜，看看谁提到过 onboarding 和 PMF。"
- "今晚跑一遍 dream cycle，把最近对话和新增资料做记忆巩固。"
