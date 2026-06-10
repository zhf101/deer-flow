# 13 Skills 技能系统

对应字幕：

- `13-Skills技能系统_哔哩哔哩_bilibili_BV1SVdHBEEhZ_P字幕.srt`
- `14-GatewayAPI_哔哩哔哩_bilibili_BV1SVdHBEEhZ_P字幕.srt` 内容重复本章，应视为重复字幕。

## 本章目标

这一集区分“工具”和“技能”：工具告诉 Agent 能做什么，技能告诉 Agent 怎么做好某类任务。

核心源码：

- `backend/packages/harness/deerflow/skills/types.py`
- `backend/packages/harness/deerflow/skills/parser.py`
- `backend/packages/harness/deerflow/skills/storage/`
- `backend/packages/harness/deerflow/skills/security_scanner.py`
- `backend/packages/harness/deerflow/skills/tool_policy.py`
- `backend/packages/harness/deerflow/agents/lead_agent/prompt.py`
- `backend/app/gateway/routers/skills.py`

## 技能是什么

技能是一个目录，核心文件是 `SKILL.md`。它通常包含：

- YAML front matter：给程序读。
- Markdown 正文：给 LLM 读。
- 可选资源、引用、脚本、模板等。

字幕里 “front metal / Emo front matter” 应校正为 front matter。

## `Skill` 数据结构

`skills/types.py` 定义：

```python
@dataclass
class Skill:
    name: str
    description: str
    license: str | None
    skill_dir: Path
    skill_file: Path
    relative_path: Path
    category: SkillCategory
    allowed_tools: list[str] | None = None
    enabled: bool = False
```

`SkillCategory` 分为：

- `PUBLIC`：内置技能。
- `CUSTOM`：用户自定义技能。

技能还提供 `get_container_path()`，把宿主机技能目录映射成沙箱内 `/mnt/skills/...` 路径。

## 为什么用 Markdown

LLM 的行为主要由语言指令影响。技能的核心内容是工作流程、质量标准、领域方法论，这些天然适合用 Markdown 表达。

如果写成 Python 函数，就只能执行固定逻辑，不能直接改变模型在复杂任务中的判断标准。技能正好补上“工具能执行，但不知道怎么做得好”的空白。

## Front matter 为什么必要

`parser.py` 用正则提取开头的 YAML front matter，并读取：

- `name`
- `description`
- `license`
- `allowed-tools`

正文是给 LLM 的自然语言，front matter 是给程序的确定性元数据。UI 列表、启用/禁用、权限过滤都不能靠 LLM 理解正文来做。

## `allowed-tools`

`allowed-tools` 是重要安全边界。

解析逻辑：

- 省略字段：返回 `None`。
- 空列表：表示这个技能显式不允许任何工具。
- 字符串列表：工具白名单。
- 格式错误：技能解析失败。

工具过滤逻辑在 `tool_policy.py`：

- 如果没有任何技能声明 `allowed-tools`，沿用 allow-all。
- 一旦有技能声明，则取所有显式白名单并集。
- 没声明的 legacy 技能不会扩大权限。

这避免了一个技能本来只需要读文件，却因为 Agent 全局工具过多而误用 `bash` 或写文件工具。

## 本地技能存储

`LocalSkillStorage` 管理目录：

```text
skills/
  public/{name}/SKILL.md
  custom/{name}/SKILL.md
  custom/.history/{name}.jsonl
```

它支持：

- 遍历 public/custom 技能。
- 读取自定义技能。
- 原子写入自定义技能。
- 删除自定义技能。
- 写历史记录。
- 从 `.skill` 压缩包安装技能。

`.skill` 安装会安全解压、校验 front matter、扫描内容，然后移动到 custom 目录。

## 技能启用状态

启用状态不写在 `SKILL.md`，而是在 `extensions_config.json`：

```json
{
  "skills": {
    "code-documentation": {"enabled": true}
  }
}
```

`ExtensionsConfig.is_skill_enabled()` 的默认规则是：public/custom 技能如果没有显式配置，默认启用。

## Gateway Skills API

`backend/app/gateway/routers/skills.py` 提供：

- `GET /api/skills`：列出全部技能。
- `GET /api/skills/{skill_name}`：查看技能。
- `PUT /api/skills/{skill_name}`：启用/禁用技能。
- `POST /api/skills/install`：从线程目录里的 `.skill` 文件安装。
- `GET /api/skills/custom`：列出自定义技能。
- `GET /api/skills/custom/{skill_name}`：读取自定义技能内容。
- `PUT /api/skills/custom/{skill_name}`：编辑自定义技能。
- `DELETE /api/skills/custom/{skill_name}`：删除自定义技能。
- `GET /api/skills/custom/{skill_name}/history`：查看历史。
- `POST /api/skills/custom/{skill_name}/rollback`：回滚。

编辑和回滚都会经过 `scan_skill_content()` 安全扫描，并刷新 skills system prompt cache。

## 子 Agent 如何加载技能

`SubagentExecutor` 会根据 `SubagentConfig.skills` 加载技能：

- `None`：加载所有启用技能。
- `[]`：不加载技能。
- 指定列表：只加载白名单技能。

加载后，子 Agent 会把技能内容合并进 SystemMessage，并用 `filter_tools_by_skill_allowed_tools()` 过滤工具。

## 本章结论

Skills 是 DeerFlow 的方法论层。工具扩展 Agent 的行动能力，技能扩展 Agent 的工作方式和质量标准。`SKILL.md` 用 Markdown 给 LLM 读，用 front matter 给程序读；`allowed-tools` 则让技能同时具备权限约束能力。

## 结合当前源码的补充分析

如果把 DeerFlow 的 Skills 只理解成“一堆 Markdown 文件”，会漏掉它真正的设计重点。当前源码里，Skills 有明确的生命周期：

```text
磁盘发现 -> front matter 解析 -> extensions_config 启用态合并
-> Lead Prompt 暴露轻量目录 -> LLM 按需 read_file 加载正文
-> allowed-tools 过滤工具 -> summarization 保护近期技能内容
-> Gateway / skill_manage 修改 custom skill -> 安全扫描、历史、缓存刷新
```

这套链路的核心是：技能正文不是默认全量注入，而是渐进加载；技能启用状态和技能内容分开；技能可以影响工具权限；技能变更会刷新 prompt 缓存。

### 技能发现生命周期

`SkillsConfig.get_skills_path()` 决定技能根目录，优先级是：

1. `config.yaml` 里的 `skills.path`。
2. `DEER_FLOW_SKILLS_PATH` 环境变量。
3. 调用方项目根目录下的 `skills`。
4. monorepo 兼容路径。

`LocalSkillStorage._iter_skill_files()` 会递归扫描：

```text
skills/public/**/SKILL.md
skills/custom/**/SKILL.md
```

实现上有几个细节：

- 支持嵌套目录，例如 `public/parent/child-skill/SKILL.md`。
- 跳过以 `.` 开头的隐藏目录。
- `public` 和 `custom` 都会扫描，按 `skills_by_name[skill.name] = skill` 合并；同名时后扫描到的 custom 会覆盖 public，因此 custom 可以 shadow 内置技能。
- `Skill.get_container_file_path()` 会把宿主机路径转换成 sandbox 里的 `/mnt/skills/{public|custom}/.../SKILL.md`。

这说明 Skills 的“目录名”和“技能名”不是完全等价的。真正对 Agent 暴露的是 front matter 里的 `name`，而不是文件夹名。GDP 如果后续做 GDP 专用 Skills，也应该以 `name` 作为稳定标识，目录只是存储位置。

### 解析和校验是两层

`parser.py` 的 `parse_skill_file()` 是运行期解析，要求较少：

- 必须有 YAML front matter。
- 必须有非空字符串 `name`。
- 必须有非空字符串 `description`。
- 可选 `license`。
- 可选 `allowed-tools`，但必须是字符串列表。

`validation.py` 的 `_validate_skill_frontmatter()` 是写入/安装前校验，约束更严格：

- 只允许 `name`、`description`、`license`、`allowed-tools`、`metadata`、`compatibility`、`version`、`author`。
- `name` 必须是小写 hyphen-case，不能以 hyphen 开头/结尾，不能连续 hyphen，最长 64。
- `description` 不能含 `<` / `>`，最长 1024。
- `allowed-tools` 必须通过同一套 `parse_allowed_tools()` 校验。

这种两层设计是合理的：运行期尽量容错，写入期严格收口。GDP 后续如果引入业务技能，也建议保留这个模式：老技能可以被读取，新建/编辑的 GDP 技能必须走严格校验。

### 启用状态生命周期

技能是否启用不写在 `SKILL.md`，而写在 `extensions_config.json`：

```json
{
  "skills": {
    "code-documentation": {"enabled": true},
    "chart-visualization": {"enabled": false}
  }
}
```

`SkillStorage.load_skills()` 每次都会调用 `ExtensionsConfig.from_file()`，重新从磁盘读启用状态。这和 MCP 一样，是为了让 Gateway 或其他进程改配置后，Agent 能看到最新状态。

默认规则在 `ExtensionsConfig.is_skill_enabled()`：

- 如果 `extensions_config.json` 没有配置某个 skill，`public` / `custom` 技能默认启用。
- 如果配置了该 skill，则按 `enabled` 字段。

这个默认值很重要：新安装的 custom skill 默认会进入可用技能列表。对通用 Lead Agent 来说这提升可发现性；对 GDP 来说则要谨慎。GDP 的技能如果会影响造数、审批、环境选择，建议不要简单沿用“默认启用”，而是在 GDP 策略层要求显式绑定到阶段或场景。

### Lead Prompt 中的 Skills 注入方式

`lead_agent/prompt.py` 没有把所有 `SKILL.md` 正文直接塞进系统提示，而是生成一个 `<skill_system>` 区块：

```xml
<skill_system>
  <available_skills>
    <skill>
      <name>...</name>
      <description>...</description>
      <location>/mnt/skills/public/.../SKILL.md</location>
    </skill>
  </available_skills>
</skill_system>
```

Prompt 明确要求模型使用 Progressive Loading：

1. 判断用户任务是否匹配某个 skill。
2. 先用 `read_file` 读取该 skill 的 `SKILL.md`。
3. 只在需要时继续加载 skill 里引用的 `references/`、`templates/`、`scripts/` 等资源。
4. 遵循 skill 指令完成任务。

这解决的是上下文经济性问题。技能目录可以很多，但每次任务只加载相关正文。这里和 MCP 的 `tool_search` 有相似设计哲学：先暴露轻量索引，按需加载完整内容。

### Skills Prompt Cache

Lead Prompt 对 enabled skills 做了缓存，避免每次请求都同步扫磁盘：

- `prime_enabled_skills_cache()` 在 agents 包初始化时预热。
- `get_cached_enabled_skills()` 命中缓存直接返回。
- 缓存未命中时启动后台线程刷新，当前请求返回空列表，避免 request path 被磁盘 IO 卡住。
- `warm_enabled_skills_cache()` 可以等待缓存预热，超时会记录 warning。
- 显式传入 `app_config` 时，会按 `id(app_config)` 缓存，保证请求级配置路径正确。
- `clear_skills_system_prompt_cache()` / `refresh_skills_system_prompt_cache_async()` 会同时清理 prompt section 的 `lru_cache` 和 enabled skills 缓存。

Gateway 安装、编辑、删除、回滚 custom skill 后都会调用 `refresh_skills_system_prompt_cache_async()`。`skill_manage` 工具修改技能后也会刷新缓存。

这个设计对 GDP 有启发：如果 GDP 技能会参与任务编排，不能只缓存“技能列表”，还要缓存“技能和阶段/场景/环境策略的映射”。否则一个 skill 内容更新后，GDP 主 Agent 可能仍按旧能力说明做决策。

## `allowed-tools` 的真实含义

`allowed-tools` 不是技能自己的工具列表，而是“加载了这些技能后，Agent 工具集允许保留哪些工具”的限制。

`tool_policy.py` 的规则是：

- 没有加载任何技能：返回 `None`，表示不做 skill-based 工具限制。
- 加载了技能，但没有任何技能声明 `allowed-tools`：沿用 allow-all。
- 只要至少一个技能声明了 `allowed-tools`：取所有显式白名单的并集。
- 声明 `allowed-tools: []` 的技能贡献空集合。
- 没声明 `allowed-tools` 的 legacy 技能不会扩大权限。

Lead Agent 工厂里有两个关键点：

- `_load_enabled_skills_for_tool_policy()` 如果加载技能失败，会抛异常，Agent 不会继续创建。这是 fail closed。
- `filter_tools_by_skill_allowed_tools()` 在 `create_agent()` 前过滤工具，因此模型根本看不到被过滤掉的工具 schema。

还要注意一个边界：如果 custom agent 的 `skills=[]`，含义是“不加载任何技能”。此时没有 skill-based 工具限制，工具权限仍由 agent 的 `tool_groups`、subagent 配置和全局工具配置决定，而不是“禁用所有工具”。

对 GDP 来说，`allowed-tools` 可以借鉴，但不能原样作为业务安全模型。GDP 的安全边界不仅是工具名，还包括：

- 当前阶段是否允许使用。
- 当前环境是否允许使用。
- 是否有写操作或造数副作用。
- 是否已经用户确认。
- 是否有幂等键避免恢复后重复执行。
- 输出是否敏感，能否进入 messages 或变量栈。

因此 GDP 可以参考 `allowed-tools` 的“声明式白名单”思想，但应该升级为 GDP 自己的 `allowed-capabilities` 或 `allowed-actions`。

## Custom Skills 写入和安装安全

自定义技能有两条写入路径：Gateway API 和 `skill_manage` 工具。

### Gateway 写入路径

`backend/app/gateway/routers/skills.py` 提供 custom skill 的读写、删除、历史和回滚。编辑和回滚都会：

1. 校验 custom skill 是否可编辑，内置 public skill 不能直接编辑。
2. 校验 `SKILL.md` front matter。
3. 调用 `scan_skill_content()` 做安全扫描。
4. 写入前后内容到 `custom/.history/{name}.jsonl`。
5. 刷新 skills prompt cache。

安装 `.skill` 包时，Gateway 先通过 `resolve_thread_virtual_path()` 找到线程目录中的上传文件，再交给 `LocalSkillStorage.ainstall_skill_from_archive()`。

### `.skill` 安装路径

`installer.py` 对 `.skill` ZIP 包做了多层防护：

- 拒绝绝对路径。
- 拒绝 `..` 目录穿越。
- 跳过 symlink 成员。
- 限制总解压大小，防 zip bomb。
- 过滤 macOS 元数据目录和 dotfile。
- 支持压缩包根目录就是 skill，也支持外层包一层目录。
- 校验根目录 `SKILL.md`。
- 禁止嵌套 `SKILL.md`。
- 扫描 `SKILL.md`。
- 扫描 `references/`、`templates/` 中的文本类提示输入文件。
- 扫描 `scripts/` 下的脚本文件，并且 executable 内容必须是 `allow`，`warn` 也会拒绝。
- 安装时先 staging，再移动到目标 custom 目录，最后把 skill tree 调整为 sandbox 可读。

### `skill_manage` 工具路径

当 `config.skill_evolution.enabled=true` 时，`get_available_tools()` 会把 `skill_manage` 加入内置工具，并且 Lead Prompt 会出现 Skill Self-Evolution 规则。

`skill_manage` 支持：

- `create`
- `edit`
- `patch`
- `delete`
- `write_file`
- `remove_file`

实现细节：

- 按 skill name 使用 `asyncio.Lock`，避免同一个 skill 并发写。
- `patch` 支持 `expected_count`，防止误替换。
- 所有写入都走安全扫描。
- 支持文件只能写入 `references/`、`templates/`、`scripts/`、`assets/`。
- `scripts/` 被视为 executable，扫描要求更严格。
- 每次变更记录 history，包含 action、author、thread_id、前后内容和 scanner 结果。
- 修改主 `SKILL.md` 后刷新 prompt cache。

这套机制的设计精髓是：Agent 可以演进技能，但不能绕过校验、扫描、历史和缓存刷新。它不是让 Agent 直接用 `write_file` 改 `/mnt/skills`。

## Sandbox 中的 Skills 只读边界

`LocalSandboxProvider` 会把 skills 目录挂载到 `config.skills.container_path`，默认 `/mnt/skills`，并标记为 `read_only=True`。

`LocalSandbox.write_file()` 和删除相关操作会检查 `_is_resolved_path_read_only()`，因此普通文件工具不能写 `/mnt/skills`。自定义技能的修改必须走 Gateway 或 `skill_manage`，这样才能经过安全扫描和历史记录。

安装和写入后，`permissions.py` 还会调整权限：

- 目录给 sandbox 可读可进入。
- 文件给 sandbox 可读。
- 去掉 group/other 写权限。
- `make_skill_written_path_sandbox_readable()` 只调整被写入路径及其父目录，不会顺手打开无关 sibling 文件。

这个边界对 GDP 也重要。如果 GDP 允许“业务技能演进”，也应该走受控 API 或专用工具，不应该让造数 Agent 直接改技能目录。

## Skills 与消息压缩的关系

Skills 和 summarization 不是互不相关的两套系统。`DeerFlowSummarizationMiddleware` 对读取过的技能文件做了“skill rescue”：

- 它识别 `read_file` / `read` / `view` / `cat` 等工具调用。
- 只要读取路径在 `/mnt/skills` 下，就认为这是技能文件加载。
- summarization 触发时，会在被压缩区间里找 AIMessage + ToolMessage 技能读取 bundle。
- 按最近使用、去重、总 token 上限、单 skill token 上限选择要保留的技能内容。
- 被保留的技能读取结果不会被总结成一段摘要，而是原样留在 messages 里。

配置项在 `SummarizationConfig`：

- `preserve_recent_skill_count` 默认 5。
- `preserve_recent_skill_tokens` 默认 25000。
- `preserve_recent_skill_tokens_per_skill` 默认 5000。
- `skill_file_read_tool_names` 默认 `read_file/read/view/cat`。

这说明 Lead Agent 明确考虑了一个问题：如果模型刚加载了某个技能，长任务压缩后不应该把这份方法论压没。GDP 后续如果引入技能，也要解决同类问题。即使 GDP 不依赖长 messages，也要在 `TaskRun/TaskStep/TaskEvent` 中记录“本阶段采用了哪些技能、版本/路径是什么、关键约束是什么”，恢复时才能重建方法论上下文。

## 子 Agent 的 Skills 处理

子 Agent 和 Lead 主 Agent 的技能加载方式不同。

Lead 主 Agent：

- Prompt 里暴露技能目录。
- 模型按需 `read_file` 加载 `SKILL.md`。
- `allowed-tools` 在 agent 创建前过滤工具。

Subagent：

- `_load_skills()` 根据 `SubagentConfig.skills` 读取 enabled skills。
- `skills=None`：加载所有 enabled skills。
- `skills=[]`：不加载技能。
- `skills=["a", "b"]`：只加载白名单。
- `_load_skill_messages()` 直接读取每个 `SKILL.md` 正文。
- `_build_initial_state()` 把 subagent system_prompt 和技能正文合成一个 SystemMessage。
- `_apply_skill_allowed_tools()` 同样用 `allowed-tools` 过滤工具。

也就是说，子 Agent 没走“轻量目录 + 按需 read_file”这条路径，而是按配置把技能正文直接注入。这对短生命周期子 Agent 合理，因为子 Agent 的任务通常更窄，直接注入可减少它忘记加载技能的概率。

GDP 如果后续有子 Agent，可以借鉴这个差异：

- GDP 主 Agent 更适合技能目录 + 阶段选择。
- GDP 子 Agent 更适合直接注入少量、明确的 GDP 技能。
- 子 Agent 的技能白名单应该由父任务阶段和子任务类型决定，而不是让子 Agent 自己自由选择。

## Skills 和 Memory 的边界

Skills 是稳定方法论，Memory 是用户或团队偏好，TaskRun/TaskStep/TaskEvent 是业务事实。

三者不要互相替代：

- Skills 适合写“如何做场景设计”“如何判断 SQL Source 参数”“如何做造数审批”“如何处理接口幂等”等流程。
- Memory 适合记“这个用户常用 DEV 环境”“这个团队把 cust_id 叫客户号”“审批偏好是什么”。
- TaskRun/TaskStep/TaskEvent 适合记录“这次任务实际选择了哪个场景、调用了哪个 Source、产生了什么变量、在哪一步中断”。

Lead Agent 的 Skills 系统不负责记忆用户偏好，也不负责记录业务执行事实。GDP 后续接入时也要保持这个边界。

## 当前 GDP Agent 的 Skills 状态

当前 GDP 代码里只有很轻的 `GDP_AGENT_PURPOSE`：

```python
GDP_AGENT_PURPOSE = """你是 GDP 造数任务编排 Agent。优先复用已发布造数场景；缺少场景时记录资源缺口，不越级配置 HTTP、SQL 或基础资源。"""
```

GDP 图目前是显式业务节点编排，不是 Lead 那种模型自由调用工具的长循环。因此当前没有接入 Skills，不是明显缺陷。现在 GDP 的主要方法论已经被硬编码进节点路由和服务函数：

- 优先复用场景。
- 缺少场景进入 `SCENE_DESIGN`。
- 缺少 Source 进入 `SOURCE_CONFIG`。
- 缺少基础配置进入 `INFRA_CONFIG`。
- 写操作前进入 `WAITING_USER`。
- 执行结果进入变量栈和任务事件。

但当 GDP 后续开始引入更多 LLM 决策，尤其是场景设计、SQL/HTTP Source 生成、业务字段映射、子 Agent 协作时，Skills 就会很有价值。

## GDP Agent 应如何借鉴 Skills 系统

GDP 不应该直接把 Lead 的 `get_skills_prompt_section()` 挂进 GDP Prompt 就结束。更合理的方式是把 DeerFlow Skills 的思想拆开复用。

### 第一层：GDP 技能目录

建议为 GDP 定义专用技能命名和目录约束，例如：

```text
gdp-scene-design
gdp-sql-source-design
gdp-http-source-design
gdp-infra-resolution
gdp-approval-policy
gdp-variable-stack
gdp-task-recovery
```

可以先存放在现有 `skills/custom` 或 `skills/public` 下，但 GDP 运行时应该有自己的筛选规则，例如只加载 `name.startswith("gdp-")` 或配置在 GDP policy 中的技能。不要让通用写作、图表、代码技能自动影响造数编排。

### 第二层：按阶段加载技能

GDP 技能不应该“全部启用就全部可用”。更适合按 `DatagenTaskPhase` 选择：

```text
SCENE_FULFILLMENT  -> gdp-scene-selection, gdp-variable-stack
SCENE_DESIGN       -> gdp-scene-design, gdp-sql-source-design, gdp-http-source-design
SOURCE_CONFIG      -> gdp-sql-source-design, gdp-http-source-design
INFRA_CONFIG       -> gdp-infra-resolution
SCENE_EXECUTING    -> gdp-approval-policy, gdp-task-recovery
PROGRESS_REFLECTION -> gdp-progress-reflection, gdp-variable-stack
```

这样技能成为“阶段方法论”，而不是全局提示词噪声。

### 第三层：GDP 专用 Skill Registry

Lead 的 skills prompt cache 是全局运行时缓存。GDP 如果做自己的 middleware 链，建议物理隔离：

```text
Lead:
SkillStorage -> get_skills_prompt_section -> Lead Prompt -> read_file -> messages

GDP:
SkillStorage -> GDPSkillRegistry -> GDPSkillContextMiddleware -> GDP phase prompt/state
```

GDP registry 至少需要记录：

- `skillName`
- `category`
- `path`
- `enabled`
- `applicablePhases`
- `requiredCapabilities`
- `allowedActions`
- `version` 或内容 hash
- `lastLoadedAt`

这些字段不是为了“像 ThreadState 一样字段多”，而是为了每个字段都有生命周期：

- `enabled` 来自配置。
- `applicablePhases` 来自 GDP policy。
- `version/hash` 用于任务恢复和审计。
- `lastLoadedAt` 用于判断是否需要重新注入。
- `allowedActions` 用于 GDP 专用工具/能力权限过滤。

### 第四层：技能内容进入 GDP 状态的方式

GDP 不适合把长 `SKILL.md` 正文长期放在 `GDPState.messages`。建议做成三层：

1. `GDPState` 只保存当前阶段已选技能的轻量引用，例如 skill name、hash、path。
2. `TaskEvent` 记录“本阶段加载了哪些技能”和关键版本。
3. 真正的技能正文只在进入 LLM 节点前临时拼进 prompt，或按需读取后做短摘要。

这样可以避免 GDPState 膨胀，也能在中断恢复时知道应该重新加载哪些技能。

### 第五层：GDP `allowed-actions`

GDP 可以借鉴 `allowed-tools`，但应改造成业务动作白名单：

```yaml
---
name: gdp-sql-source-design
description: 指导 GDP Agent 设计 SQL Source 的流程和质量标准。
allowed-actions:
  - search_sql_sources
  - parse_sql_source
  - test_sql_source
  - upsert_sql_source_draft
applicable-phases:
  - SOURCE_CONFIG
  - SCENE_DESIGN
side-effect-level: WRITE_CONFIG
approval-required: true
---
```

当前 DeerFlow parser 不支持这些字段；如果 GDP 要用，需要扩展 GDP 自己的 metadata 解析，或者放在 `metadata.gdp` 下，避免破坏通用 skill 校验：

```yaml
metadata:
  gdp:
    applicable-phases: [...]
    allowed-actions: [...]
    side-effect-level: WRITE_CONFIG
```

这样既兼容现有 `SKILL.md` 协议，又能让 GDP 有更强的业务约束。

### 第六层：GDP 技能演进

GDP 后续可以接入类似 `skill_manage` 的演进能力，但建议不要直接让 GDP 主 Agent 修改通用 custom skills。更稳妥的方式是新增 GDP 专用技能管理入口：

```text
gdp_skill_manage:
  create_draft
  propose_patch
  approve_patch
  publish
  rollback
```

原因是 GDP 技能会影响造数安全，不能和普通写作/可视化技能同一审批等级。GDP 技能演进至少要记录：

- 哪个任务触发了技能变更。
- 哪个业务场景暴露了方法论缺口。
- 变更前后内容。
- 审批人。
- 生效范围。
- 是否影响历史任务恢复。

## GDP 接入 Skills 的推荐结论

GDP 适合接入 Skills，但接入方式应该是“借鉴 Lead 的技能生命周期”，而不是“直接复用 Lead 的 prompt 注入”。

推荐判断：

- 当前 GDP 没有 Skills 可以接受，因为核心编排还靠显式节点和数据库状态。
- 一旦 GDP 的 LLM 决策增多，就应该引入 GDP 专用 Skills。
- Skills 应该承载造数方法论，不承载任务事实。
- GDP Skills 应按阶段加载，按业务动作过滤权限。
- GDPState 只保存技能引用和版本，不长期保存完整正文。
- TaskEvent 要记录技能采用情况，保证中断恢复和审计。
- 技能演进要走 GDP 专用审批，不建议直接复用通用 `skill_manage` 的权限等级。

一句话总结：Lead Skills 的设计精髓是“用轻量目录触发按需方法论加载，并把方法论和工具权限绑定”；GDP 应该继承这个思想，但把技能从通用 Agent 工作流升级为“造数阶段方法论 + 业务动作权限 + 可恢复审计”的专用体系。
