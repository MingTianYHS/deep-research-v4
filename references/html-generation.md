# HTML 报告生成：McKinsey 风格

**何时读取**：用户需要网页版报告，或需要把已通过校验的 Markdown 报告转换成可直接打开的 HTML 时读取。

**用途**：说明 `scripts\md_to_html.py` 与 `templates\mckinsey_report_template.html` 的调用方式、模板占位符、校验步骤与视觉规范。

## 设计原则

- 直角设计，不使用圆角。
- 低饱和企业配色：深蓝 `#003d5c`、浅灰 `#f8f9fa`。
- 紧凑排版，信息优先，14px 基础字号。
- 不使用装饰性渐变或多余颜色，不使用 emoji。
- 中文字体优先：`Microsoft YaHei`、`PingFang SC`、`Noto Sans CJK SC`、`Source Han Sans SC`。

## 生成前提

1. `研究报告.md` 已通过 `validate_report.py` 与 `verify_citations.py`，正文与参考文献稳定。
2. 报告使用标准 Markdown：`##` 章节标题、`###` 小节标题、列表、表格、`[标题](URL)` 链接与 `[N]` 引用。
3. run 目录由 `citation_manager.py init-run` 创建，路径形如 `research\<主题>_研究_<YYYYMMDD>\`。

## 生成步骤

### 1. 直接生成 HTML

```powershell
$skill = "<DSH 技能根目录>\deep-research"; $py = "$env:DSH_HOME\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
& $py "$skill\scripts\md_to_html.py" "research\<主题>_研究_<YYYYMMDD>\研究报告.md"
```

默认行为：

- 读取 UTF-8 编码的 Markdown 报告。
- 转换为正文 HTML 与参考文献 HTML。
- **读取同目录 `来源.jsonl`，把正文里的 `[N]` 渲染成可点击来源链接**（点一下在新标签页打开来源 URL）；没有 URL 的编号保持纯文本。Markdown 版报告本身不插入链接，保持 `[N]` 纯编号。
- 载入技能自带的 `templates\mckinsey_report_template.html`，填充全部占位符，并自动生成顶部指标条（章节数、来源数、正文字数）。
- 在报告同目录写出 `报告.html`。

可选参数：

| 参数 | 说明 |
| --- | --- |
| `--template <模板.html>` | 指定其他模板；默认使用技能目录下的 `templates\mckinsey_report_template.html` |
| `--output <输出.html>` | 指定输出路径；默认与 Markdown 报告同目录的 `报告.html` |
| `--date YYYY-MM-DD` | 覆盖页面显示的生成日期；默认取当前日期 |

示例：显式指定输出文件（模板使用技能自带默认值）：

```powershell
$skill = "<DSH 技能根目录>\deep-research"; $py = "$env:DSH_HOME\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
& $py "$skill\scripts\md_to_html.py" "research\<主题>_研究_<YYYYMMDD>\研究报告.md" --output "research\<主题>_研究_<YYYYMMDD>\报告.html"
```

### 2. 模板占位符（由脚本填充）

| 占位符 | 填入内容 |
| --- | --- |
| `{{TITLE}}` | 报告标题，取报告第一个一级标题 |
| `{{DATE}}` | 生成日期，格式 `YYYY-MM-DD` |
| `{{SOURCE_COUNT}}` | `来源.jsonl` 中的唯一来源数 |
| `{{METRICS_DASHBOARD}}` | 顶部指标条 HTML；脚本自动生成章节数、来源数、正文字数三项 |
| `{{CONTENT}}` | 除参考文献外的全部章节 HTML |
| `{{BIBLIOGRAPHY}}` | 参考文献 HTML |

生成后如需微调顶部指标或版式，直接用 `edit` 修改 `报告.html`，改完重新执行第 3 步校验。所有 `{{...}}` 占位符必须清空，不能留在成品里。

### 3. 校验 HTML

```powershell
$skill = "<DSH 技能根目录>\deep-research"; $py = "$env:DSH_HOME\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
& $py "$skill\scripts\verify_html.py" --html "research\<主题>_研究_<YYYYMMDD>\报告.html" --md "research\<主题>_研究_<YYYYMMDD>\研究报告.md"
```

校验内容包括：Markdown 章节是否全部出现在 HTML、占位符是否清空、是否有 emoji、HTML 基本结构、引用与参考文献是否保留。失败时按错误提示修复后重跑，不要交付未通过校验的文件。

### 4. 打开检查

```powershell
Start-Process "research\<主题>_研究_<YYYYMMDD>\报告.html"
```

在浏览器中确认：中文字体正常、表格不溢出、长链接可点击、页面可离线打开。

## 交付前检查清单

- [ ] 所有 `{{...}}` 占位符已替换。
- [ ] `研究报告.md` 的每个 `##` 章节在 HTML 中有对应标题。
- [ ] 正文引用 `[N]` 与参考文献条目一一对应，无缺号。
- [ ] 页面无 emoji、无外部资源依赖、无未闭合标签。
- [ ] 保存为 UTF-8 编码的 `报告.html`，位于同一 run 目录。
