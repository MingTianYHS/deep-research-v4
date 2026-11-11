# 开源方案全景与证据核验

**何时读取**：研究主题涉及软件、工具、自动化、实现、集成、部署，或用户明确要求可落地的开源方案时读取。这是条件性但强制的完成门槛，不适用时也要在报告中说明「不适用」的理由。

**用途**：规定代码托管平台检索范围、候选仓库规范化、实现级证据核验、`开源方案.jsonl` 数据契约与报告呈现方式。

## 1. 发现覆盖

搜索 GitHub，并在可用且与主题相关时至少再搜索两个代码托管平台或代码索引。候选平台包括 GitLab、Gitee、Codeberg、SourceForge、GitCode、Bitbucket 公开仓库、包注册表与垂直领域索引。不要为满足数量加入低价值平台；记录每个平台为何适用或不可用。

使用多种查询形式：

- 主题与产品名：中文、英文各搜一轮。
- 动作词：upload、publish、automate、scheduler、adapter、plugin、CLI、SDK、bot、integration。
- 实现词：Playwright、Puppeteer、Selenium、API、browser extension、RPA、reverse engineering、protocol。
- 平台原生检索：topic、language、filename、code search（平台支持时）。

把尝试的平台、查询式、检索日期与结果数记录到 `运行清单.json` 的检索轨迹（或报告的方法论附录）。搜索摘要只是发现线索，不能当作证据。

## 2. 规范化与入选条件

把镜像、fork、改名仓库、组织迁移与 vendored copy 归并到 canonical upstream。仅当 fork 独立维护且有实质改动时，才作为独立方案记录。记录仓库之间的关系，不要虚增方案数量。

入选仓库必须满足：

1. 有公开可访问的 canonical URL；
2. 有与主题相关的实现代码或文档；
3. 至少检查过一个文件、提交、发布版本或 issue，能支撑所声称的机制；
4. 有足够元数据，能诚实说明维护状态与许可证不确定性。

归档、停更、无许可证、概念验证或私有协议项目，在决策相关时可以纳入，但必须标注状态，不得当作生产可用方案推荐。

## 3. 证据核验

只有 README 声明不足以支撑核心能力判断。要检查相关 adapter、uploader、workflow、manifest、包元数据、release、issue 或 commit；实现证据优先使用不可变的 commit URL。记录检查了哪个证据、它证明了什么。

stars、forks、归档状态、许可证、默认分支、最后推送时间等易变事实，用平台 API 或仓库元数据页确认，并记录检索日期。不得根据编程语言、仓库可见性或许可证文本的传闻推断许可证。

每个仓库分开记录四类信息：

- **仓库事实**：URL、平台、所有者、许可证、指标、日期、归档状态、语言。
- **已验证机制**：实现如何工作，证据路径或 commit 是什么。
- **评估**：成熟度、安全性、维护状况、平台政策与采用适配度。
- **建议**：可复用、仅参考、需人工介入、仅作研究、拒绝。

## 4. 数据契约

在 run 目录写入 `开源方案.jsonl`，一行一个 JSON 对象：

```json
{
  "name": "project-name",
  "canonical_url": "https://forge.example/owner/repo",
  "forge": "github",
  "upstream_url": null,
  "description": "一句话说明已验证的范围",
  "license": "MIT",
  "stars": 123,
  "forks": 12,
  "archived": false,
  "last_activity_at": "2026-08-30",
  "retrieved_at": "2026-08-30",
  "implementation_mechanism": "Playwright 驱动官方创作者界面",
  "evidence_url": "https://forge.example/owner/repo/blob/commit/path/file",
  "evidence_locator": "function publishVideo",
  "verification_status": "code_verified",
  "fit": "reference",
  "risks": ["平台条款", "登录态存储"]
}
```

`verification_status` 只允许 `code_verified`、`release_verified`、`documentation_only`、`unverified`。`fit` 只允许 `reuse`、`reference`、`human_in_the_loop`、`research_only`、`reject`。

如果没有任何仓库达标，写入一条 `status: "no_qualifying_repositories"` 记录，并带上 `attempted_forges`、`queries`、`retrieved_at`、`reason`；不能以沉默代替结论。

## 5. 报告呈现

报告必须包含「开源方案全景」一节，给出 canonical 仓库直链，并用紧凑表格覆盖：项目、平台、已验证机制、活跃度、许可证、检查过的证据、适配方式、风险。

表格之后用段落说明：

- 最强的可复用方案及理由；
- 仅参考或仅研究的项目；
- 被排除的镜像、fork、失效链接或只有营销话术的项目；
- 尝试过的平台中仍存在的覆盖缺口；
- 易变指标可能在检索后发生变化。

对比表是发现与交接材料，不能替代证据分析。仓库页面与实现证据要同时登记到 `来源.jsonl` 与 `证据.jsonl`，报告中的相关论点照常引用。

## 6. 校验

适用时运行：

```powershell
$skill = "<DSH 技能根目录>\deep-research"; $py = "$env:DSH_HOME\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
& $py "$skill\scripts\validate_open_source_solutions.py" --artifact "research\<主题>_研究_<YYYYMMDD>\开源方案.jsonl" --report "research\<主题>_研究_<YYYYMMDD>\研究报告.md" --strict
```

校验失败时先修 `开源方案.jsonl` 或报告中的缺失项，再重跑；连续 2 次仍失败，停止并说明具体缺口。
