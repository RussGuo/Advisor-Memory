# Workflows / 工作流

## 1. Setup Workflow / 初始化工作流

Use this when first installing the system.  
首次安装系统时使用。

### A. Inject operating rules / 注入运行规则

Add rules to `AGENTS.md`, `CLAUDE.md`, or equivalent:

- read domain memory before external search / 先读领域记忆，再做外部检索
- preserve raw sources on ingest / 导入时保留原文
- write durable insights back into the brain / 稳定洞见写回长期记忆
- sync after writes / 写完后同步
- run periodic dream cycle / 定期跑 dream cycle

### B. Initialize the brain / 初始化 brain

```bash
gbrain init
gbrain doctor --json
```

Then create or validate durable directories and `sources/libraries/`.  
然后创建或校验长期目录和 `sources/libraries/`。

For the Lenny-first path, use:

```bash
python3 scripts/init_lenny_first_memory.py \
  --brain-root /absolute/path/to/brain \
  --lenny-root /absolute/path/to/lennys-podcast-newsletter
```

### C. Bootstrap existing memory / 导入现有记忆

- private knowledge goes to normal brain pages / 私有长期知识进标准长期页面
- corpus-like materials become library packs / 资料库型内容注册成 pack
- unresolved material lands in `working/` or `inbox/` / 暂时不确定的内容放 `working/` 或 `inbox/`

### D. Keep the result human-readable / 保持结果对人可读

After setup, a human should be able to browse the system without learning the internal scripts first.  
初始化完成后，人应该不需要先理解内部脚本，也能直接浏览这套系统。

Default human entrypoints / 默认给人看的入口:

- durable pages such as `projects/`, `concepts/`, `people/`, `companies/`, `ideas/`
- `sources/libraries/index.md`
- each pack's `index.md`
- raw files when deeper reading is needed

## 2. Ingest Workflow / 导入工作流

Default entrypoint / 默认入口:

```bash
python3 scripts/smart_ingest_library_pack.py \
  --brain-root /absolute/path/to/brain \
  --source /absolute/path/to/corpus-or-file
```

### A. Identify the ingest type / 识别导入类型

- single note or document / 单文件
- batch export / 批量导出
- transcript archive / 访谈或转录归档
- external corpus / 外部知识库
- updated existing source / 已有资料库更新

### B. Decide the home / 决定放哪里

- durable entity or fact -> main brain / 稳定实体或事实，写入主脑
- reusable corpus -> library pack / 可复用语料，注册成 pack
- unclear -> `working/` or `inbox/` / 不明确时先放工作层

### C. Preserve the original / 保留原文

Never skip this.  
这一步不能跳。

- copy or symlink the original into `raw/`
- record checksum and source metadata / 记录 checksum 与来源信息
- keep it human-readable / 保持人可读

### D. Build the disclosure ladder / 建立渐进披露层

Create:

- metadata entry / 元数据
- indexes / 索引
- file-level summaries / 单文件摘要
- lightweight library map / 轻量库地图

Human vs system split / 人类入口与系统元数据拆分:

- keep `raw/` and pack `index.md` human-facing / 让 `raw/` 和 pack 根目录 `index.md` 面向人类
- write machine metadata under `_system/` / 把机器元数据写到 `_system/`

If domains are insufficient, extend taxonomy automatically before finalizing indexes.  
如果现有 domain 不够，先自动扩展 taxonomy，再完成索引。

### E. Link into durable memory / 与长期记忆建立回链

If the material changes a concept, project, or entity page:

- update compiled truth / 更新 compiled truth
- append timeline evidence / 追加 timeline 证据
- link back to the raw source / 回链到原文

### F. Sync / 同步

For git-backed brains:

```bash
gbrain sync --repo /absolute/path/to/brain --no-pull --no-embed
# optional when an OpenAI key is configured / 配置了 OpenAI key 时再执行
gbrain embed --stale
```

If no OpenAI key is configured, this workflow should still continue in keyword/fulltext/raw mode instead of failing.  
如果没有配置 OpenAI key，这条工作流也应继续以 keyword/fulltext/raw 模式运行，而不是失败。

For non-git brains, the scripts use selective import through a temporary staging tree.  
对于非 git brain，脚本会通过临时 staging tree 做选择性导入。

Imported / 会导入:

- durable pages
- `working/`
- `sources/libraries/<pack>/raw/`

Skipped / 会跳过:

- pack `_system/`
- `inbox/`

## 3. Consult Workflow / 咨询与回答工作流

Use this when the user asks for advice or synthesis.  
当用户要建议、分析、综合回答时使用。

Default entrypoint / 默认入口:

```bash
python3 scripts/consult_advisor_memory.py \
  --brain-root /absolute/path/to/brain \
  "How should we improve onboarding and PMF?"
```

This path should automatically:

- search GBrain durable memory first / 先查 GBrain 长期记忆
- auto-resolve a mentioned project page when possible / 如果问题里提到已知项目，自动解析对应项目页
- score all relevant packs / 对相关 pack 自动打分
- locate the best source files / 找最相关原文
- read the most relevant matched windows instead of always reading file headers / 优先读取命中片段上下文，而不是只读文件开头

If the consult belongs to a live project, use:

```bash
python3 scripts/consult_advisor_memory.py \
  --brain-root /absolute/path/to/brain \
  --project-target projects/project-a.md \
  "How should we improve onboarding and PMF?"
```

This will also emit a project-memory review under `working/project-memory-reviews/`.  
这还会在 `working/project-memory-reviews/` 下生成一个项目记忆待确认 review。

### A. Determine the active domains / 确定活跃领域

Examples / 例子:

- roadmap question -> `product`, `projects`
- PMF question -> `product`, `growth`
- people issue -> `people`, `leadership`

### B. Load distilled memory first / 先加载长期蒸馏记忆

Read:

- concept pages
- project pages
- person/company pages
- recent `working/` pages if the topic is active

### C. Route into relevant packs / 路由到相关 pack

Examples / 例子:

- Lenny for product or growth playbooks
- interview archive for voice-of-customer evidence
- personal notes pack for historical thinking

For low-level multi-pack inspection, use:

```bash
python3 scripts/search_library_pack.py \
  --brain-root /absolute/path/to/brain \
  --all-packs \
  search "query" --limit 10
```

Best practice / 最佳实践:

- broad advisory questions should default to `consult_advisor_memory.py`
- pack-specific search is a precision feature, not the default path
- do not require users to say a specific trigger phrase before using advisor-wide retrieval / 不要要求用户先说某个固定触发词才进入全局顾问检索

### D. Drill down only as needed / 只在需要时下钻

Go in this order / 顺序如下:

1. manifest or indexes
2. summaries for routing only
3. full raw files for the best candidates
4. excerpts only if token budget is tight

### E. Answer in three layers / 三层式回答

- current situation / 当前情况
- supporting evidence / 支撑证据
- recommendation / 建议

If a known project is in play, invert the center of gravity:  
如果涉及一个已知项目，就把回答重心倒过来：

- start from the project page / 从项目页出发
- use packs as evidence / 把 pack 当证据层
- answer with a project decision, recommendation, or next move / 用项目决策、建议或下一步来回答
- do not answer with a library summary first / 不要先做资料摘要

Production-quality answer contract / 生产级回答契约:

- recommendation-first / 先给建议或判断
- evidence-backed / 再给证据
- project-aware when relevant / 涉及项目时必须结合项目上下文
- full-memory by default / 默认联合全量顾问记忆，而不是只看单 pack

### F. Ask before writing back to a project / 写回项目页前先确认

If a consult emits `project_memory_review`, do this:

1. show the candidate updates to the user / 把候选更新展示给用户
2. ask whether they should be written back into the project page / 询问是否写回项目页
3. only after confirmation, apply the review / 确认后再应用

Apply with:

```bash
python3 scripts/update_project_memory.py \
  --brain-root /absolute/path/to/brain \
  --review-file /absolute/path/to/brain/working/project-memory-reviews/review.json \
  --accept default
```

This writes confirmed consult updates into `projects/...` and adds a timeline entry.  
它会把确认过的咨询更新写入 `projects/...`，并追加 timeline 记录。

## 4. Dream Cycle Workflow / 梦境周期工作流

Run nightly or during quiet hours.  
夜间或空闲时运行。

### Inspect Mode / 诊断模式

```bash
python3 scripts/dream_cycle.py --brain-root /absolute/path/to/brain
```

This will scan / 会扫描:

- `working/` candidates / 待提升工作记忆
- stale `_system/summaries/` / 过期 `_system/summaries/`
- stale human-facing `index.md` / 过期的人类入口页 `index.md`
- domain suggestions / 自动分类建议
- then optionally refresh GBrain / 然后按配置刷新 GBrain

### Apply Mode / 自动修复模式

```bash
python3 scripts/dream_cycle.py --brain-root /absolute/path/to/brain --apply
```

This will automatically:

- rebuild stale summaries / 重建过期摘要
- rebuild stale library maps / 重建过期库地图
- refresh pack indexes / 刷新 pack 索引
- emit `working/pending-promotions/dream-cycle-queue.json`
- emit `working/pending-promotions/dream-cycle-queue.md`
- refresh GBrain unless disabled / 除非显式关闭，否则刷新 GBrain

Promote queue items or source items with:

```bash
python3 scripts/promote.py \
  --brain-root /absolute/path/to/brain \
  --item working:working/pending-promotions/note.md \
  --target concepts/pmf.md
```

What it does not auto-decide / 它不会自动决定:

- semantic promotion destination / 语义上到底该提升到哪个长期页面
- final human judgment / 最终判断

## 5. Lenny Workflow / Lenny 专用工作流

Treat Lenny as one registered library inside the larger system.  
把 Lenny 看成系统内一个标准 pack，而不是独立外挂。

When a product question may benefit from Lenny:

1. load relevant personal/project memory / 先读相关长期记忆
2. search the Lenny pack / 搜 Lenny
3. read the best raw file / 读最相关原文
4. answer with both user and Lenny context / 结合用户上下文与 Lenny 回答
5. if the answer becomes durable, write back distilled insight / 若形成稳定结论，再写回长期记忆
