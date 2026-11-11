# 证据链数据契约与操作手册（evidence-chain）

**何时读取**：需要登记来源、写入证据、抽取论点或排查证据链问题时读本文件。`references/quality-gates.md` 讲“门槛是什么”，本文件讲“数据怎么落、命令怎么跑”。

## 1. 为什么需要证据链

深度研究的交付物不只是报告，还要能回答三个问题：

1. 这句话是**从哪来的**？
2. 原文**具体怎么说**？
3. 报告里的数字、日期、名称是否与原文一致？

证据链把「报告句子 → 论点 → 证据 → 来源」连成一条可回溯的路径。这样即使上下文被压缩、隔几天再修改，也能还原依据；也能用脚本自动发现「引用了不存在的来源」「数字与原文不符」「论点没有证据」等问题。

## 2. 文件与字段

### 2.1 `来源.jsonl`

每行一个来源对象：

| 字段 | 说明 |
|---|---|
| `source_id` | `sha256(canonical_locator)[:16]`，稳定 ID |
| `canonical_locator` | 规范化定位符：`doi:...`、`arxiv:...` 或规范化 URL |
| `raw_url` | 用户可点击的原始 URL |
| `title` | 来源标题 |
| `authors` | 作者列表或 null |
| `year` | 年份或 null |
| `source_type` | `official` / `academic` / `news` / `industry` / `web` / `other` / `documentation` / `code` / `government` / `book` |
| `metadata_status` | 登记时写入 `unverified`；如需标记人工核验结论，可改为 `doi_verified` / `url_verified` / `title_matched` / `verified` / `conflicted`（脚本不自动回写，需人工或后续工具更新） |
| `registered_at` | ISO 8601 时间 |

### 2.2 `证据.jsonl`

每行一条证据：

| 字段 | 说明 |
|---|---|
| `evidence_id` | `sha256(source_id + normalized_quote + locator)[:16]` |
| `source_id` | 对应 `来源.jsonl` 的 source_id |
| `quote` | 原文片段（尽量逐字，不要改写） |
| `locator` | 页码、章节标题、URL 锚点或时间戳 |
| `evidence_type` | `direct_quote` / `paraphrase` / `data_point` / `official_statement` / `methodology` |
| `captured_at` | ISO 8601 时间 |
| `query` | 触发这条证据的检索式或任务（可选） |

### 2.3 `论点.jsonl`

每行一个原子论点：

| 字段 | 说明 |
|---|---|
| `claim_id` | `sha256(section_id + normalized_text)[:16]` |
| `section_id` | 报告章节标识（如 `finding_1`、`synthesis`） |
| `text` | 一句可核查的陈述 |
| `claim_type` | `factual` / `synthesis` / `recommendation` / `speculation` |
| `materiality` | `A` / `B` / `C` / `D` |
| `cited_source_ids` | 该句引用的来源 ID 列表 |
| `evidence_ids` | 支持该句的证据 ID 列表 |
| `support_status` | `unverified` / `supported` / `partial` / `needs_review` / `unsupported` / `retired`（改稿后不再出现的旧论点会被标记 retired，不参与校验） |
| `_support_score` | 脚本计算的重合分（0–1） |
| `extracted_at` | ISO 8601 时间 |

### 2.4 `运行清单.json`

记录本轮研究的基本信息：版本、查询、模式、查询形态、验证强度、预算、开始/结束时间、假设、报告目录、产物路径、续写信息。`citation_manager.py init-run` 自动创建；**交付前运行 `citation_manager.py finalize-run --dir "[run目录]"` 写入 `finished_at` 与关键假设**，不要手工编辑 JSON。

## 3. 操作流程

### 3.1 初始化 run 目录

```powershell
$skill = "<DSH 技能根目录>\deep-research"
$py = "$env:DSH_HOME\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
& $py "$skill\scripts\citation_manager.py" init-run --query "研究问题" --mode <direct|standard|deep> --out-dir "<工作目录>\research\<主题>_研究_<YYYYMMDD>"
```

**始终以用户工作目录为 cwd，用 `--out-dir` 显式指定 run 目录**，不要写进技能安装目录。

输出示例：

```json
{"status": "ok", "manifest": "C:\\...\\research\\研究问题_研究_20261111\\运行清单.json", "dir": "C:\\...\\research\\研究问题_研究_20261111"}
```

`--mode` 可选 `direct` / `standard` / `deep`。深研需要更大预算时可加 `--budget extended`。

### 3.2 登记来源

先把来源对象写入一个 UTF-8 JSON 文件（例如 `来源1.json`）：

```json
{"raw_url": "https://example.com/report", "title": "示例报告", "source_type": "official", "year": "2026"}
```

再运行：

```powershell
$skill = "<DSH 技能根目录>\deep-research"; $py = "$env:DSH_HOME\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
& $py "$skill\scripts\citation_manager.py" register-source --dir "[run目录]" --json-file "来源1.json"
```

PowerShell 直接传 `--json '{"..."}'` 时内层双引号可能被剥离；优先用 `--json-file`。也支持 `--json -` 从标准输入读取。

输出 `source_id`。同一 canonical locator 重复登记会返回 `duplicate`，不会重复写入。

### 3.3 写入证据

先把证据对象写入 UTF-8 JSON 文件（例如 `证据1.json`）：

```json
{"source_id": "abc123", "quote": "原文片段", "locator": "第 5 页", "evidence_type": "direct_quote"}
```

再运行：

```powershell
$skill = "<DSH 技能根目录>\deep-research"; $py = "$env:DSH_HOME\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
& $py "$skill\scripts\evidence_store.py" add --dir "[run目录]" --json-file "证据1.json"
```

原则：一份证据只对应一段原文；不要把整篇文章塞进一个 quote。quote 必须是来源中真实存在的文字。

### 3.4 抽取论点

```powershell
$skill = "<DSH 技能根目录>\deep-research"; $py = "$env:DSH_HOME\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
& $py "$skill\scripts\extract_claims.py" extract --report "[run目录]\研究报告.md" --dir "[run目录]"
```

脚本按标题拆分章节、按中文句号/问号/叹号或英文标点切句，并初步分类 `claim_type` 与 `materiality`。自动分类是启发式，负责人需要复核；随后运行 `link-claims` 把引用编号关联到来源。

### 3.5 关联论点与来源

```powershell
$skill = "<DSH 技能根目录>\deep-research"; $py = "$env:DSH_HOME\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
& $py "$skill\scripts\citation_manager.py" link-claims --dir "[run目录]"
```

把 `论点.jsonl` 里的 `_citation_numbers`（正文中的 `[1]`、`[2]`）按 `来源.jsonl` 的登记顺序（**先去重再编号**）映射为稳定 `source_id`，写入 `cited_source_ids`。如果出现 `unresolved_citation_numbers`，说明正文引用编号在来源表中找不到对应项，命令会以退出码 1 失败；先修报告或补登记来源。

**多个来源的写法**：同一句引用多个来源时，`[1,2]` 与 `[1][2]` 两种写法都支持，脚本会把两个编号都登记到该论点。推荐用 `[1,2]`（更紧凑）。引用编号必须紧跟在它所支撑的那句话句末，不要写到下一句，否则会被判为「该论点无引用」。

### 3.6 校验论点支撑

```powershell
$skill = "<DSH 技能根目录>\deep-research"; $py = "$env:DSH_HOME\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
& $py "$skill\scripts\verify_claim_support.py" verify --dir "[run目录]" --profile standard --strict
```

`--profile` 可选 `direct` / `standard` / `deep`。标准档对 A 类硬事实严格，深研对所有 factual 严格，直查只警告。`needs_review` / `partial` 不阻塞，会进入 `advisory` 清单供人工复核。

### 3.7 导出参考文献

```powershell
$skill = "<DSH 技能根目录>\deep-research"; $py = "$env:DSH_HOME\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
& $py "$skill\scripts\citation_manager.py" export-bibliography --dir "[run目录]" --style markdown
```

生成编号参考文献，可粘贴到 `研究报告.md` 的「参考文献」一节，再核对正文编号。

## 4. 材料性判定示例

| 句子 | 类型 | 理由 |
|---|---|---|
| 「2025 年该市场规模为 120 亿美元 [1]」 | A | 具体数字与年份 |
| 「该行业通常分为上游、中游、下游 [2]」 | B | 背景定义 |
| 「综合来看，价格战仍将持续 [3]」 | C | 分析判断，需要可追溯的事实支撑 |
| 「预计 2027 年渗透率将达到 30%」 | D | 预测，必须标注 |

## 5. 常见问题

### 5.1 中文句子被判 `needs_review`

`verify_claim_support.py` 对中文使用字符 bigram 计算重合度。如果证据是高度概括的转述、或句子主要是分析而非事实，得分可能偏低。处理顺序：

1. 检查是否引用了正确的 `evidence_ids`；
2. 检查 `quote` 是否真的包含对应事实；
3. 确认 `claim_type` 是否应为 `synthesis` 而非 `factual`；
4. 仍不合理时人工复核，不要为了过校验而删除有价值的分析。

### 5.2 同一来源被多次登记

`source_id` 基于 canonical locator；URL 的 utm 参数、末尾斜杠、大小写 host 会被规范化，通常不会重复。如果发现重复，检查 canonical locator 是否被手工写错。

### 5.3 参考文献编号与正文不一致

先运行 `export-bibliography` 重新生成，再按正文出现顺序核对。不要手工重排 `来源.jsonl`；它的顺序是登记顺序，编号由 `assign-display-numbers` 统一分配。

### 5.4 续写或上下文丢失

所有证据都在 `证据.jsonl`，不在模型上下文里。续写时先读 `运行清单.json` 与 `研究计划.md`，再从 `来源.jsonl` / `证据.jsonl` 恢复事实基础。

## 6. 最低操作要求

- 每批检索完成后立即登记来源与证据，不要等报告写完再补。
- 任何 A 类事实如果没有 `证据.jsonl` 记录，不得写入报告。
- 交付前必须运行 `verify_claim_support.py`，并检查 `support_status` 中 `unsupported` 的 factual 论点数量为 0。
- 所有 JSONL 使用 UTF-8、每行一个 JSON 对象、`ensure_ascii=False`。
