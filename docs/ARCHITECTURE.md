# 全局架构与数据流

版本：M5-A · 2026-10-04 · 技术实现约定；功能与迁移集中验证待执行

[项目入口](../README.md) · [功能指南](FEATURE_GUIDE.md) · [产品说明](PROJECT_OVERVIEW.md) · [进度记录](DEVELOPMENT_PROGRESS.md) · [功能测试](FUNCTIONAL_TESTS.md)

本文档是跨模块技术约定的统一来源。产品含义见项目说明，实际验证结果见进度记录。每次接口、数据结构或事务行为变化都必须同步本文件。

对应的测试步骤、边界与异常见功能测试文档；技术约定变化时同步修订相关用例。功能实现与测试执行分别记录，尚未运行的验证保持未执行。

## 1. 系统边界

React/TypeScript/Vite 前端通过同源 `/api/v1` 访问 FastAPI。SQLAlchemy 2 使用 Python sqlite3 驱动保存本地数据，Alembic 管理表结构。本地运行不依赖 Docker 或数据库服务器；手动功能不依赖模型，M3 使用用户配置的兼容模型接口。

每个后端实例使用一个 SQLite 文件；多账号以所有者字段隔离。不同电脑独立启动时有各自的数据；共享同一后端的账号访问同一文件中各自的数据。Git 仅同步代码、迁移、契约和文档。

| 模块 | 当前代码 | 职责 |
| --- | --- | --- |
| 界面与路由 | `frontend/src/main.tsx`、`shell.tsx`、`auth.tsx`、`records.tsx`、`projects.tsx` | 账号、项目与记录页面；地图和规划按路由延迟加载 |
| 地图与规划 | `map.tsx`、`research.tsx`、`planning.tsx`、`actions.tsx`、`reflections.tsx`、`m2-shared.tsx` | 画布/列表、方向、行动、复盘、共用证据与对象选择器 |
| 贡献与成长 | `growth-page/editor/shared/material.tsx`、`api_growth.py`、`growth_commands/data/queries.py` | 三页签、固定引用/历史/复核、跨模块入口与行动来源 |
| AI 贡献候选 | `ai-contribution.tsx`、`ai_prompts/data/commands.py` | 复用模型设置与任务，按类型校验及事务采纳 |
| 请求与缓存 | `api.ts`、TanStack Query | Cookie 同源请求、内存 CSRF、错误展示、保存后的缓存更新 |
| API 契约 | `backend/app/main.py`、`api_m1.py`、`api_m2.py`、`schemas*.py`、`openapi.json` | 请求校验、HTTP/错误映射、生成前端类型 |
| 会话与归属 | `security.py`、`records.py` | 确定用户、校验所有者与父级对象、限制归档/删除对象 |
| 记录服务 | `records.py` | 创建、CAS 更新、删除恢复、来源修订与事务历史 |
| M2 命令与投影 | `m2_commands.py`、`m2_common.py`、`m2_queries.py` | 业务命令、固定引用、图查询与分页投影；查询不改正文 |
| 存储与运维 | `models.py`、`models_m2.py`、`db.py`、`migrations/`、`scripts/backup.py` | 模型、连接参数、启动迁移与一致性备份 |

## 2. 全项目数据流

```mermaid
flowchart TD
    A[文本输入或文件导入] --> B[身份与归属检查]
    B --> C[事务保存原始材料及版本]
    C --> D[探索卡与用户判断]
    D --> E[记录版本快照]
    C -. M3 .-> F[固定输入版本的 AI 任务]
    F --> G[带证据的候选建议]
    G --> H[用户修改、采纳或拒绝]
    H --> D
    D --> I[研究问题与图谱关系]
    D -. M4 .-> J[贡献条目与成长实例]
    I --> K[手动复盘]
    J --> K
    D --> K
    K --> L[方向选择与行动]
    L --> A
```

M1 实现身份、项目、记录、来源及历史。图谱引用业务对象，不复制正文；布局独立保存。M2 问题、发现、方向、关系、行动与复盘见第 9 节。M3 模型流程见第 10 节，M4 贡献、成长见第 11 节，继续引用固定来源版本，模型建议不能直接覆盖用户判断。

## 3. M1 对象与关系

```mermaid
erDiagram
    USER ||--o{ SESSION : authenticates
    USER ||--o{ PROJECT : owns
    USER ||--o{ RECORD : owns
    PROJECT o|--o{ RECORD : groups
    RECORD ||--|{ RECORD_REVISION : snapshots
    RECORD ||--o{ SOURCE : captures
    SOURCE ||--|{ SOURCE_VERSION : versions
```

| 对象 | 约定 |
| --- | --- |
| User | UUID、唯一规范化用户名、显示名称、Argon2 密码哈希 |
| Session | 令牌 SHA-256 摘要、用户、CSRF token、到期时间；有效期七天 |
| Project | 所有者、名称、说明、归档状态；不提供物理删除 |
| Record | 所有者、可空项目、类型、正文及结构化判断、工作/结果状态、版本号、删除时间、创建请求标识及内容摘要 |
| RecordRevision | 每次变更后的完整快照、当时来源版本标识、操作类型；只追加 |
| Source | 所属记录、材料类型、名称、当前版本；原始材料与整理正文分离 |
| SourceVersion | 稳定 UUID、序号、原文或 HTTP(S) URL、UTC 时间；只追加 |

UUID 使用字符串，时间以 UTC 保存并通过带时区的 ISO 8601 输出，快照采用通用 JSON。工作状态为 `planned/in_progress/blocked/paused/finished`；结果判断为 `none/inconclusive/unsupported/preliminary/not_applicable`；类型为 `note/paper/experiment/ai/idea`。

M2 新增研究内容、节点、关系、固定证据、行动、复盘、布局与修订表。M3 已增加 AIConfig/AITask/AITaskInput/AISuggestion/AISuggestionEvent；未来 Contribution/Skill/GrowthEntry 不创建空表，按对应里程碑迁移；继续沿用固定版本引用和显式确认。

## 4. 存储生命周期

- 默认 `data/edutoy.sqlite3`；`EDUTOY_DB_PATH` 可覆盖，相对路径始终从仓库根目录解析。
- 统一启动入口创建目录，运行 Alembic，再启动单进程 Uvicorn；迁移失败立即退出，不替换原库。
- 每个连接启用 `foreign_keys=ON`、`busy_timeout=5000`；使用默认 DELETE 日志模式及短事务。
- 每个请求独立数据库会话。SQLite 繁忙返回 503 `database_busy`，前端保留表单。
- 备份使用 sqlite3 backup API；目标必须是新文件。恢复须先停止后端，再替换配置指向的数据库。
- 数据目录、数据库/日志/备份、虚拟环境、环境文件均不进入 Git。
- 测试使用独立临时文件与真实迁移，不读取或清空日常数据库。

`backend/run.py` 是统一启动入口。初始表结构版本为 `0001_m1`；迁移环境启用 `render_as_batch=True`，未来 SQLite 结构变更使用 Alembic 批处理。就绪接口动态读取 Alembic 当前 head，与数据库 `alembic_version` 比较；目前 head 为 `0002_m2`。备份命令和停服恢复步骤见 README。

## 5. 写入、版本和幂等

1. 创建：探索卡、原始材料、来源首版、记录首版在一个事务中完成。创建请求 UUID 在同一账号内唯一；相同请求与内容返回已有对象，不同内容返回 409。
2. 编辑：客户端发送 `expected_version`；数据库原子条件更新成功后才追加快照。旧版本返回 409，不覆盖较新内容。
3. 来源追加或修订：经记录服务更新记录版本、追加来源版本和历史快照，同事务提交。
4. 删除/恢复：均有版本检查与历史记录。普通查询不返回删除记录；只能通过已删除筛选查看并恢复。
5. 项目归档：保留数据，阻止其记录变更；恢复项目后可继续编辑。归档项目不能接收新记录。
6. 快照包含当时的来源版本 ID。任何材料或记录变化都不会修改旧快照。
7. 模型和其他外部调用不得占用写事务；后续重复采纳以建议 ID 保证幂等，过期输入版本必须复核。

记录编辑、追加材料和材料修订都会递增记录 `version`；删除和恢复同样增加版本。操作类型为 `create/edit/source_add/source_revise/delete/restore`。浏览器编辑表单固定打开时的版本，409 后保留输入，用户明确放弃当前输入后才能重新载入。

幂等标识为每账号内的 `request_id` UUID，数据库保存创建载荷摘要。网络重试必须重用同一个 ID 和原载荷；用户修改载荷后生成新 ID。重放返回同一记录的当前状态，包括可能已被编辑或删除的状态；它不会回滚内容或自动恢复记录。

## 6. 身份与接口

API 前缀 `/api/v1`；规范来源为 FastAPI OpenAPI，前端通过脚本生成类型。所有者由会话决定；对象及父级均检查归属，他人对象返回 404。写请求检查 Origin，已登录写请求同时检查 `X-CSRF-Token`。会话 Cookie 为 HttpOnly、SameSite=Lax；HTTPS 部署启用 Secure。令牌不进入 localStorage。

| 接口 | 能力 |
| --- | --- |
| POST auth/register, auth/login, auth/logout; GET auth/me | 账号与会话 |
| GET/POST projects; GET/PATCH projects/{id} | 项目与归档恢复 |
| GET/POST records; GET/PATCH/DELETE records/{id} | 列表、详情及版本化变更 |
| POST records/import | multipart 单文件导入 |
| POST records/{id}/restore | 版本化恢复 |
| GET records/{id}/revisions | 不可变记录历史 |
| GET/POST records/{id}/sources | 来源查询和追加 |
| GET/POST sources/{id}/versions | 来源历史和修订 |
| GET health/live, health/ready | 存活、迁移就绪检查 |

记录列表返回 `items/total/page/page_size`，默认 20、最大 100 条，界面每页 12 条；项目、历史和单条记录的来源集合返回数组。错误返回 `error.code/message/request_id`，响应头同步 `X-Request-ID`。UUID、状态、字段长度与 URL 由请求模型校验；导入限 `.md/.txt`、1 MiB、UTF-8（可带 BOM），单文件生成一条记录。标题默认首个 Markdown 标题，其次文件名。链接仅保存，不抓取。Markdown 展示禁用原始 HTML，仅允许 HTTP(S) 链接，远程图片显示替代文字，不自动请求外部图片。

### 6.1 请求约定

- `GET records`：`q` 搜索标题、正文和结构化字段的子串（支持中文，`%`/`_` 按文字处理）；`project_id`、`unassigned`、`record_type`、`work_status`、`outcome_status`、`deleted`、`page`、`page_size` 可组合。
- `GET records/{id}?include_deleted=true` 可由所有者查看已删除详情；历史保留可读，来源需恢复记录后读取。未来 AI/图谱的查询入口不得携带此例外。
- `POST records`：`request_id` 必填，标题和正文至少一项非空；`project_id=null` 表示未归类，`fields` 包含六项结构化内容。未指定来源时自动保存首次正文（无正文则保存标题）为原始材料。
- `PATCH records/{id}`：`expected_version` 必填，只改变提交的字段；`fields` 若提交则整体替换，省略的结构化字段为空串。删除、恢复、来源追加和修订也必须发送 `expected_version`。
- `POST records/import`：multipart 字段 `file`、`request_id` 必填；`record_type` 默认为 `note`，`project_id` 可省略。
- `PATCH projects/{id}`：修改 `name/description/archived`；`archived=true/false` 即归档/恢复。项目元数据不维护历史版本，记录变更才使用 CAS。
- 来源内容最多 1,048,576 字符；文件导入上限单独按字节检查。URL 来源只接受 HTTP(S) 且不能携带用户名密码。

核心错误码：`validation_error`（422）、`unauthorized`（401）、`origin_failed/csrf_failed`（403）、`not_found`（404）、`version_conflict/request_conflict/project_archived`（409）、`file_too_large`（413）、`unsupported_file/invalid_encoding/empty_file`（422）、`database_busy/database_unavailable`（503）、`internal_error`（500）。错误响应不回显研究正文或密码。

### 6.2 会话与界面状态

注册即创建会话；重复登录撤销本浏览器旧令牌，其他浏览器的独立会话继续有效。退出删除当前会话并清除 Cookie；到期后接口拒绝访问。`GET auth/me` 返回用户和会话绑定的 CSRF Token，Token 仅保存在前端内存，刷新后重新获取。

未登录入口进入登录页。已打开表单遇到 401 时保留组件和输入，在弹窗中重新登录同一账号，用户再次保存；不会自动重放原请求。网络、锁超时和版本冲突均保留输入；离开未保存页面会提示。退出账号清理查询缓存，避免向下一账号展示前一账号内容。

## 7. 跨模块写入边界

| 模块 | 输入与输出 | 状态与限制 |
| --- | --- | --- |
| M2 图谱 | 问题/发现引用探索卡；关系包含起止节点、类型、依据版本；布局独立 | 所有者校验，删除对象排除，手动编辑通过关系业务接口 |
| M3 AI | 用户选定来源版本 → AITask → 带引用的 Suggestion → 正式对象 | 任务状态 `queued/running/succeeded/failed/cancelled` 与建议状态 `pending/accepted/edited_accepted/rejected` 分开；`needs_review` 独立标记输入过时 |
| M4 成长 | 探索卡与来源 → 用户确认的贡献 → 能力标签与成长实例 | 依据固定版本，用户确认归属，无自动贡献占比或能力总分 |
| 行动与复盘 | 选择已有记录/关系/成长作为证据 → 方向与行动 → 新探索卡 | 调整只经正式业务接口，显式选择，不无声覆盖历史判断 |

AI 任务仅能读取当前用户选择并有权访问的材料，固定输入版本；输出先校验字段和引用，再保存候选。采纳时核对输入仍有效，通过建议 ID 防重复写入，采纳与正式对象同事务保存。模型失败只改变任务状态，不阻止手动操作。M3 已实现手动选择材料后的真实兼容 API 调用；测试模拟服务独立于正式应用，详见第 10 节。

## 8. 开发与验证原则

先实现后端事务与隔离，再接入中文界面；所有展示来自真实接口。M2 开放手动地图和下一步；“我的成长”仍标注待开发。验证覆盖多账号、幂等、版本冲突、事务回滚、外键、锁超时、历史、导入与重启持久化。

数据库方案由原建议 PostgreSQL 调整为用户指定的 SQLite 本地文件；Docker 及独立数据库服务已退出当前方案。具体测试数量和最终完成状态仅在开发进度文档中记录。

## 9. M2 研究地图与行动闭环

本轮开放研究地图与下一步：问题 → 主动关联记录 → 发现 → 跨项目方向 → 行动 → 结果记录 → 手动复盘。M3 的记录/关系 AI 见第 10 节，成长仍留在 M4。记录不自动入图，结项只要求一句结果说明。

```mermaid
flowchart TD
    R[记录及不可变来源版本] --> Q[用户建立问题和关系]
    Q --> F[发现与适用条件]
    F --> D[方向池]
    D --> A[行动]
    A --> S[结项说明与可选结果记录]
    S --> R
    R --> V[尝试复盘和周期复盘]
    S --> V
    V --> C[用户显式调整方向或创建行动]
    C --> D
    C --> A
```

### 对象与数据边界

- ResearchItem 使用 kind=question/finding/direction；正文属于业务对象，差异字段由 Pydantic 严格校验。kind 创建后固定。
- GraphNode 只映射 Record 或 ResearchItem；两个可空外键必须恰好一个有值，目标唯一，不复制标题正文。关系只引用节点。
- GraphRelation 保存有向类型、说明、两端确认版本和证据；普通关联可不写理由，其他关系必须填写。子问题只能连接问题，一个子问题只有一个父问题且不能成环。
- EvidenceReference 固定 record_revision_id，可带 source_version_id、字段路径、Unicode 字符位置和原文片段。引用选定来源时必须出现在该记录快照的来源列表中。
- Action、ActionRecord 管理执行与多对多结果引用；结项不自动关闭方向或改变研究结果。
- Reflection 保存用户复盘及选定记录/行动/研究内容的修订标识；周期默认本地自然周，以 UTC 半开区间查询，保存时区。
- 业务修订只追加；M2 每次正文、状态、证据变化追加完整快照。MutationRequest 保存用户、操作、请求摘要和结果标识，重复调用不重复创建。
- GraphLayout 按账号和 scope（all/project/unassigned）保存坐标，独立 CAS 版本，不改变正文和证据状态。

### 写入与引用生命周期

记录服务内部仅 flush，由请求或复合命令外层提交；结项、可选新记录与可选关联同事务提交。所有写请求在读取会话及业务状态前使用短的 SQLite IMMEDIATE 事务串行校验关系约束，仍采用 5 秒忙等待和原子版本检查。

来源/端点更新后旧引用保留并提示复核；可确认旧依据仍适用，或显式选择新依据。已删除来源返回占位而不再返回引用原文；恢复后重新可读。删除节点仅使相关连线不可见，不级联删除他人对象、其他记录或行动；单独删除的连线不会因节点恢复而自动恢复。归档对象只读。

### 地图投影与界面

项目地图含本项目及直接相连的外部节点，外部节点有项目标识；个人总览覆盖账号内有效内容。记录仅在存在有效关系时入图。单次画布最多 150 节点并返回 total_nodes/truncated，列表可分页访问完整内容。拖动位置单独保存，刷新不自动重排；用户可触发 Dagre 整理。窄屏默认列表，所有关系操作均有表单入口。

### 接口与实施顺序

所有接口仍位于 `/api/v1`，所有权、UUID、CSRF、错误与分页遵守 M1。

| 接口组 | 能力与关键输入 |
| --- | --- |
| `/research-items`、`/{id}` | GET/POST 列表与创建、GET/PATCH/DELETE 单项；kind 创建后固定 |
| `/relations`、`/{id}` | 分页查询、创建/编辑/删除；输入类型化 source/target 引用，由后端解析节点 |
| `/research-items/{id}/review`、`/relations/{id}/review` | POST `expected_version`，可提交新 evidence；确认现有依据仍适用 |
| 上述对象及 `/actions`、`/reflections` 的 `/{id}/restore`、`/revisions` | POST 版本化恢复、GET 不可变快照；不提供回滚 |
| `/graph` | GET 总览/项目/未归类、关键词、类型、状态、待复核、归档、focus/depth；最多 150 节点 |
| `/graph/candidates` | GET 完整对象分页，含未入图记录；`unlinked=true` 筛选待关联记录 |
| `/graph/layout` | GET/PUT 用户与 scope 布局；`expected_version=0` 创建，后续 CAS；只更新提交节点坐标 |
| `/actions`、`/{id}` | 分页查询、创建/编辑/删除及结果记录关联；从方向创建时可默认继承项目 |
| `/actions/{id}/complete` | POST `expected_version/request_id/result_summary`，可带 records/new_record/link_direction；单事务 |
| `/actions/{id}/reopen` | POST `expected_version/request_id/reason`；结项历史保留 |
| `/reflections`、`/{id}` | 尝试/周期复盘创建、列表、编辑、删除；材料是固定版本引用 |
| `/reflections/materials` | GET 时间区间内记录、行动、研究内容最新一次变化，可搜索/项目筛选/分页 |
| `/records/{id}/context` | GET 记录相关的关系、行动及直接选择它的复盘 |

图返回 `nodes/edges/total_nodes/truncated`，节点只带摘要、标识、项目、状态、版本、跨项目和归档标识。未映射的候选记录用 `record:<UUID>` 作为候选 UI 标识，建立关系时只发送业务对象 UUID；不允许把候选标识当成图节点写入布局。

新增错误码包括 `duplicate_relation`、`parent_exists`、`question_cycle`、`self_relation`、`invalid_subquestion`、`immutable_kind`、`invalid_evidence`、`source_deleted`、`use_status_command`。冲突保持当前输入，重新载入需明确放弃当前草稿。

先拆分与事务改造，再迁移 0002_m2、地图、行动、复盘、回归。就绪状态比较 Alembic head。升级前备份日常数据；测试只使用临时库，包括 M1 → M2 升级、500 节点/1000 关系、账号隔离、幂等/回滚及窄屏流程。最终实测结果记入开发进度。


### M2 关系结构

```mermaid
erDiagram
    USER ||--o{ RESEARCH_ITEM : owns
    USER ||--o{ ACTION : owns
    USER ||--o{ REFLECTION : owns
    USER ||--o{ GRAPH_LAYOUT : owns
    USER ||--o{ MUTATION_REQUEST : deduplicates
    PROJECT o|--o{ RESEARCH_ITEM : groups
    PROJECT o|--o{ ACTION : groups
    PROJECT o|--o{ REFLECTION : groups
    RECORD o|--o| GRAPH_NODE : maps
    RESEARCH_ITEM o|--o| GRAPH_NODE : maps
    GRAPH_NODE ||--o{ GRAPH_RELATION : source
    GRAPH_NODE ||--o{ GRAPH_RELATION : target
    RESEARCH_ITEM o|--o{ EVIDENCE_REFERENCE : cites
    GRAPH_RELATION o|--o{ EVIDENCE_REFERENCE : cites
    RECORD_REVISION ||--o{ EVIDENCE_REFERENCE : fixes
    SOURCE_VERSION o|--o{ EVIDENCE_REFERENCE : locates
    RESEARCH_ITEM o|--o{ ACTION : direction
    ACTION ||--o{ ACTION_RECORD : results
    RECORD_REVISION ||--o{ ACTION_RECORD : fixes
    REFLECTION o|--o{ ACTION : inspires
    RESEARCH_ITEM o|--o{ M2_REVISION : snapshots
    GRAPH_RELATION o|--o{ M2_REVISION : snapshots
    ACTION o|--o{ M2_REVISION : snapshots
    REFLECTION o|--o{ M2_REVISION : snapshots
```

GraphNode 的 record/item 外键、EvidenceReference 的 item/relation 外键、M2Revision 的四个业务外键均有“恰好一个非空”的数据库约束。Reflection 的多态材料引用保存在 JSON，通过所有权、对象 ID 和对应修订归属联合校验；历史引用不允许更换为别人的版本。方向外键必须指向 kind=direction 的 ResearchItem，由业务服务校验。

### 状态与方向语义

| 内容 | 状态 |
| --- | --- |
| 问题 | exploring 探索中、paused 暂缓、answered 已有回答 |
| 发现 | tentative 暂定、reviewed 已核对、withdrawn 已撤回 |
| 方向 | candidate 候选、focus 当前重点、paused 暂缓、closed 已关闭；优先级 high/normal/low |
| 行动 | planned 待开始、in_progress 进行中、blocked 受阻、paused 暂缓、completed 已完成、cancelled 已取消 |
| 尝试复盘选择 | continue 继续、adjust 调整、pause 暂缓、finish 结束；不自动改变对象状态 |

关系始终读作 A → B：related 关联、subquestion A 是 B 的子问题、derived_from A 源于 B、tests A 验证 B、supports A 支持 B、challenges A 质疑 B、extends A 延伸 B、reuses A 复用 B。除 related 外均填写理由，没有证据则明确标注“未附证据”。活跃同起点/终点/类型关系唯一；subquestion 起点唯一，其他类型可以形成循环。

### 证据复核与历史展示

- 引用正文保存字段路径和 Unicode 码点区间 `[start,end)`；引用来源保存其固定来源版本内区间，后端验证原文严格匹配。整字段引用不必提供片段。
- `reviewed_record_version` 是用户最近确认该固定依据仍适用时的记录版本，不改变 `record_revision_id` / `source_version_id`。普通编辑保留未变化证据的确认信息；已经处于 reviewed 的发现不会因普通编辑自动清除新的复核提示。
- 首次标记发现为 reviewed 需至少一个有效依据，界面要求勾选核对声明；之后可通过专门复核命令确认旧依据，或编辑选择新版本。
- 关系还比较两端业务版本，删除/恢复同样触发复核；布局更新不影响业务版本。复盘材料始终展示选定修订，不用最新正文替换。
- 历史中的 evidence/results/materials 读取时检查当前来源可用性；被删除的来源只显示占位，原历史标识保留；恢复后重新可读。原始历史 JSON 不改写。编辑自己的文字时可保留同一对象已经引用的删除来源，不得把已删除来源新增到别的对象；占位引用恢复后仍可追溯。
- 复盘保存成功后，创建行动或调整方向使用独立页面和业务命令；后续操作失败不撤销已保存复盘。

实现参考：[React Flow](https://reactflow.dev/learn)、[Dagre 布局示例](https://reactflow.dev/examples/layout/dagre)、[Alembic SQLite 批处理](https://alembic.sqlalchemy.org/en/latest/batch.html)。

## 10. M3：模型配置、任务与候选采纳（已实施，真实接口验收待完成）

M3 阶段整理已有探索卡、建议已有对象之间的关系；M4 增量贡献候选见第 11 节。AI 规划与复盘生成仍待后续。每个账号维护一套 OpenAI Chat Completions 兼容配置：URL、模型名、API Key；URL 保留路径，仅在非完整地址后追加 `/chat/completions`，不追加 `/v1`，不跟随重定向。HTTPS 云端与 HTTP 本机回环可用。

```mermaid
flowchart TD
    A[账号配置] --> B[服务端加密 Key]
    C[用户选择字段和材料] --> D[预览并固定版本]
    D --> E[短事务保存任务]
    B --> F[无数据库事务的模型请求]
    E --> F
    F --> G[结构与引用校验]
    G --> H[持久化候选]
    H --> I[用户对照修改采纳或拒绝]
    I --> J[版本归属业务约束检查]
    J --> K[业务变更历史与采纳结果同事务提交]
```

### 10.1 模型与凭据

新增 `0003_m3`：AIConfig（账号独立配置）、AITask（任务/非敏感配置快照）、AITaskInput（固定输入与真实外键）、AISuggestion（不可变候选与最终采纳结果）、AISuggestionEvent（处理事件）。输入引用记录修订或研究内容修订，来源必须属于该记录修订。任务不复制 Key，正式记录/关系继续通过既有业务服务写入。

```mermaid
erDiagram
    USER ||--o| AI_CONFIG : configures
    USER ||--o{ AI_TASK : requests
    AI_TASK ||--o{ AI_TASK_INPUT : fixes
    AI_TASK ||--o{ AI_SUGGESTION : generates
    RECORD_REVISION o|--o{ AI_TASK_INPUT : record_basis
    M2_REVISION o|--o{ AI_TASK_INPUT : research_basis
    SOURCE_VERSION o|--o{ AI_TASK_INPUT : source_basis
    AI_SUGGESTION ||--o{ AI_SUGGESTION_EVENT : decisions
    RECORD_REVISION o|--o{ AI_SUGGESTION : accepted_record_result
    M2_REVISION o|--o{ AI_SUGGESTION : accepted_relation_result
```

AITaskInput 的记录与研究对象引用互斥，并分别引用真实对象及其修订。配置版本是任务执行前的校验条件；任务保留地址、模型和版本快照，不依赖配置仍然存在，也不保存密钥副本。

API Key 使用 cryptography Fernet 加密落库。主密钥默认 `data/ai-master.key`，可通过 `EDUTOY_AI_KEY_PATH` 配置，相对路径从仓库根目录解析；首次需要时生成，POSIX 0600。已有密文但文件缺失时禁止自动替换，AI 暂不可用，手动功能继续。数据库备份不包含主密钥，迁移电脑时需分别恢复。Key 不进入响应、浏览器持久存储、日志、提示词和任务快照。修改请求地址必须重新输入 Key。

### 10.2 任务与事务

任务状态 queued/running/succeeded/failed/cancelled；建议状态 pending/accepted/edited_accepted/rejected。后端生命周期运行执行器，SQLite 持久排队；全局最多 2 个运行，每账号 1 个运行、5 个排队。连接测试同样是任务，仅发送固定文本。连接超时 10 秒，总时限 120 秒，响应最多 1 MiB，无自动重试。启动将中断的 running 标为 failed，queued 重新校验后继续；取消通过状态条件防止迟到响应覆盖。

创建任务先提交；执行器短事务读取/认领，关闭会话后调用模型，再短事务保存候选。任何外部等待不得持有 SQLite 事务。配置版本改变后排队任务失败，不静默替换配置；清除配置取消未完成任务。创建/重试使用请求 UUID 幂等；采纳与业务历史原子提交，并以建议唯一结果防重复。

### 10.3 选择、输出与复核

单次最多 32,000 Unicode 字符，不截断；整理一条记录，关联任务 2–20 对象且至少一条记录，最多 10 条建议。只发送勾选字段/来源，不抓网页、不扫描其他对象。材料编号由后端分配，引用返回编号/原文/出现序号，后端定位并校验；研究对象只能作端点，证据来自固定记录/来源版本。输出 JSON 经过 Pydantic 和引用校验，失败不创建部分候选；空关系列表是合法结果。

整理只建议标题、类型、六个结构字段；缺失信息留空，未表达的个人判断不得补写。采纳仅合并用户勾选字段，不改原始正文、来源、项目或状态。非空结构字段必须有片段引用。关系建议沿用八种类型与现有约束，候选不进入图谱。用户编辑和原始候选分别保留。

输入更新时 pending 建议提示待复核；保留旧依据须提交用户确认的当前版本映射，采纳事务中再次核对。删除输入时材料和依赖候选隐藏，恢复后可读；归档内容只读。已采纳正式内容和采纳历史保留。错误、冲突、会话过期保留前端输入。

### 10.4 API 与验证

`/api/v1/ai`：config GET/PUT/DELETE、config/test POST、preview POST、tasks GET/POST、tasks/{id} GET、cancel/retry POST、suggestions GET、suggestions/{id} GET、accept/reject POST、suggestions/reject-batch POST。沿用账号/CSRF/Origin、统一错误、分页及 OpenAPI 类型生成；模型 401 作为任务错误，不触发应用退出。

前端账号区模型设置；记录详情 AI 整理、地图 AI 建议关联、科研记录 AI 收件箱。预览显示实际发送内容、地址和模型；字段对照选择、逐条采纳与批量拒绝。任务每 2 秒轮询，终态停止。

测试使用独立 SQLite/主密钥与本地模拟 HTTP 服务。35 项后端与 14 项浏览器测试为 M2 回归基线，新增密钥、网络、任务生命周期、引用、复核、采纳原子性与移动端覆盖。真实兼容接口验收另行记录，未配置真实凭据时不得将模拟测试等同于真实验收。
M3 实际模块：`models_ai.py` / `schemas_ai.py` 定义存储与契约；`ai_credentials.py` 管理加密与配置；`ai_data.py` 定位材料、校验引用并投影删除/更新状态；`ai_prompts.py` 管理 m3.v1 提示词；`ai_worker.py` 执行受限 HTTP 调用；`ai_commands.py` 处理事务与采纳；`api_ai.py` 暴露接口。前端模型设置、材料选择、收件箱分别延迟加载，共用生成的 API 类型。

采纳产生的 RecordRevision/Revision 使用 `ai_accept` 操作名，在同一首次快照中记录 `ai_suggestion_id`；历史页可回到建议。模型调用只含选定材料，当前材料对照仅返回当前用户的界面，不加入外发提示。错误状态和取消通过数据库任务状态检查保护，建议全部校验成功后才一起保存。配置清除保留递增版本，避免旧排队任务错误地使用重新创建的配置。

## 11. M4：贡献与成长（实现完成，集中验证待执行）

本轮开放贡献时间线、能力档案、理解变化及 AI 贡献候选；用户已确认允许先保存自述，AI 仅分析显式选择的科研记录字段/来源。无材料标为“用户自述／待补依据”，有引用不等于系统验证。AI 评分、自动能力判定、AI 规划及导出不在本轮。

```mermaid
flowchart TD
    R[记录/行动/复盘的固定版本] --> C[用户确认贡献]
    C --> G[能力实例/理解变化]
    R --> G
    G --> F[周复盘选择固定版本]
    F --> A[用户明确创建行动]
    G --> A
    A --> R
    S[用户选择记录字段与来源] --> T[AI 贡献候选任务]
    T --> U[引用校验与用户修改确认]
    U --> C
```

### 11.1 存储与版本

新增迁移 `0004_m4`：Contribution、AbilityTag、GrowthEntry、GrowthEntryTag、GrowthEvidence、GrowthRevision、GrowthActionLink。贡献/成长有独立 owner/version/deleted_at；标签归档恢复并保留历史。GrowthEntry.kind 固定为 ability_instance/understanding_change，差异字段使用严格 Pydantic JSON。发生日期为本地日历日期，技术时间 UTC；时间线按发生日期、创建时间、ID 倒序稳定分页。

GrowthEvidence 的宿主是贡献或成长（互斥 FK）；依据固定 RecordRevision、M2Revision（行动/复盘）或 GrowthRevision（仅贡献，且仅成长可引用），真实 FK 加互斥约束。记录可引用 source_version_id、字段与 Unicode 片段；其他对象引用整个快照。理解变化分 before/trigger/after，其余为 context。

创建/编辑的当前内容、依据、标签和历史同事务；内部服务 flush，外层 commit；expected_version 原子比较；创建及复合操作复用 MutationRequest。贡献每次保存须用户确认，保存确认时间。来源变更比较 reviewed_version；下层引用通过迭代访问集合投影状态，reviewed_dependencies 保存明确复核时的下层版本映射，并提示复核，复核提交 current_versions 同时校验直接与下层版本，明确确认保留旧依据；删除来源读取时遮蔽，恢复后重新投影，不能新增删除引用。

引用只返回本层快照和带可用性的摘要，不递归展开整个历史。成长引用贡献时汇总该贡献依据的可用性/复核提示；成长与复盘互引按需读取，使用访问集合防重复。既有用户文字不因依据删除而清除。

能力实例至少一个标签；标签同账号去首尾空白后名称唯一，归档名称保留。用户自述无需材料；材料记录需要记录/行动/复盘引用；任务实践需要已完成且有结项说明的行动快照。贡献自述不能自动升级能力依据类型。标签统计来自后端筛选范围，历史保存当时名称。

### 11.2 接口与联动

新增 `/contributions`、`/growth-entries` 版本化 CRUD、restore/revisions/review；`/ability-tags` 创建修改/归档恢复/历史/筛选统计；`/growth/materials`、按需读取单层快照的 `/growth/material` 与 `/growth/context` 提供受账号约束的材料和关联投影。贡献/成长 `/{id}/actions` 在一个事务中创建行动和 GrowthActionLink，失败不撤销之前已保存的成长。行动详情可查看来源固定修订。

复盘材料增加 contribution/growth_entry 类型；周复盘按修订发生的 UTC 区间查询，发生日期单独展示。归档项目只读，已有引用可保留，新选归档来源需先恢复。贡献与成长不创建 GraphNode。

### 11.3 AI 增量

任务类型 contribution_candidates，1–20 条记录、32,000 字符、最多 10 个候选。复用当前加密配置、执行器和收件箱；新增提示词版本 m4.contributions.v1，M3 提示词版本保留。提示词、校验、采纳均显式分派，未知类型拒绝。

非空事实字段须引用（类型可用候选整体依据）；未知本人参与/帮助/影响留空。采纳须用户确认归属、选择日期/项目、保留至少一个有效引用；用户增补字段独立标记，不把原引用冒充增补内容的证明。AISuggestion 新增贡献与贡献修订 FK，贡献、历史、采纳结果和事件同事务；同一建议重复采纳返回原结果。

### 11.4 验证安排

本轮补充自动化脚本和 FUNCTIONAL_TESTS.md，功能用例均保持未执行；仅运行必要格式、类型、构建、OpenAPI 与文档检查。日常数据库升级待实际启动前备份；不为本轮验收启动真实模型或改写日常数据。

### 11.5 落实细节与迁移决策

- `backend/app/api_growth.py` 提供路由；`growth_commands.py` 维护事务命令；`growth_data.py` 负责固定版本、可用性、复核与单层投影；`growth_queries.py` 负责筛选、统计、材料和上下文。前端 `growth-page/editor/shared/material` 分开组织，页面按路由延迟加载。
- 发生日期范围包含两端；UTC 周复盘范围起点包含、终点不包含，查询贡献/成长在期间内的最新修订。默认每页 20 条；标签数量对完整筛选集合统计，不从页面推算。
- 当前 M4 列表先按数据库条件筛选，再做引用状态计算和分页；适用于当前个人本地规模，大规模优化不在本轮。不会递归向前端发送整条引用链；状态检查使用迭代访问集合，不依赖 Python 递归深度。
- `GrowthEvidence.reviewed_dependencies` 只记录版本确认，不替换原快照。删除的下层材料使依据标为不可用；恢复后重新投影。再次更新会重新提示复核。历史快照保存当时的直接及下层确认信息。
- 贡献编辑每次要求重新勾选本人确认；客户端在任何归属描述改动后清除确认。冲突重载展示服务器内容，保留表单，显式对照后才改用新的版本号。
- `0004_m4` 使用冻结的 SQLite 建表 DDL。AI 建议表只新增两个可空外键列，采用 SQLite 原生 `ADD COLUMN ... REFERENCES`，不重建已有表：避免开启外键时批量重建父表影响已有建议事件。这是对计划“批处理迁移”的针对性调整；后续必须重建的结构变化仍使用批处理。原 M1–M3 迁移未修改。实际升级与 FK 检查留待独立库集中验证。
- M4 没有新增包依赖或模型配置项；提示词版本 `m4.contributions.v1`，无 AI 能力评分、贡献比例或自动成长创建。候选采纳通过同一贡献命令，增加 `ai_suggestion_id`、`user_supplement_fields` 历史追溯。

```mermaid
erDiagram
    Contribution ||--o{ GrowthRevision : history
    GrowthEntry ||--o{ GrowthRevision : history
    AbilityTag ||--o{ GrowthRevision : history
    GrowthEntry ||--o{ GrowthEntryTag : tags
    AbilityTag ||--o{ GrowthEntryTag : instances
    Contribution ||--o{ GrowthEvidence : evidence
    GrowthEntry ||--o{ GrowthEvidence : evidence
    RecordRevision ||--o{ GrowthEvidence : fixed_record
    M2Revision ||--o{ GrowthEvidence : fixed_action_or_reflection
    GrowthRevision ||--o{ GrowthEvidence : fixed_contribution
    SourceVersion o|--o{ GrowthEvidence : optional_source
    GrowthRevision ||--o{ GrowthActionLink : origin
    Action ||--o| GrowthActionLink : follows
    AISuggestion o|--o| Contribution : accepted_as
```

依据表的宿主及目标外键是互斥关系，图示只表示可能关联；具体限制以表约束和业务校验为准。周复盘复用 M2 的类型化 JSON 材料列表，写入及读取时校验固定修订与账号，未额外创建重复的复盘正文。

## 12. M5-A：行动建议、周复盘辅助与业务导出（已实现，待验证）

本轮采用 action_candidates / reflection_draft，复用当前模型配置、队列、取消/重试和收件箱。用户先保存周期复盘中的个人文字，再选字段与已关联的固定材料请求整理。行动仅逐条创建待开始任务，复盘仅修改明确采纳字段，不自动改方向、状态、结果或材料。

```mermaid
flowchart TD
    A[用户选择目标与字段] --> B[预览和固定版本]
    B --> C[AI任务与严格引用校验]
    C --> D[人工修改/复核/采纳]
    D --> E[业务修订与采纳依据同事务]
    E --> F[选择导出范围]
    F --> G[当前内容和引用版本的只读投影]
    G --> H[预览范围与指纹]
    H --> I[重新校验后下载JSON或Markdown]
```

输入适配器显式支持 record/research_item/action/reflection/contribution/growth_entry；仅勾选字段进入模型，不递归发送下层材料。新的任务可固定旧修订，同时携带选择时当前版本；旧任务格式与范围不放宽。1–20对象，材料与规划目标/限制合计32,000 Unicode字符。行动最多5候选，理由至少一项原文引用；复盘仅 progress/understanding/blockers/next_steps，已有文字默认不采用，追加/替换前展示最终文本。新任务输出任一项错误则整体失败。

迁移0005_m5a扩展AITask参数/目标、AITaskInput六类互斥对象修订、AISuggestion正式结果引用，新增AIAdoption和AIAdoptionCitation。输入真实外键、修订归属双重校验。外部请求不持有数据库事务；采纳沿用现有业务服务，正式对象/修订/引用/事件同事务。采纳信息标为特定修订的历史，不宣称支持后来的人工修改。

导出覆盖当前正式业务内容及实际使用的固定依据，不含全部历史、画布布局、账号凭据、模型配置或未采纳候选。普通范围外链接只有摘要；依据引用可以带出跨项目固定版本，在预览中明确列出。引用链迭代去重，删除来源只留占位。JSON与Markdown共享白名单投影；Markdown仅记录/复盘正文及依据附录。全部/项目/未归类/手选范围，归档默认排除，最多5,000条和20MiB，超限不截断。

导出在专用会话显式BEGIN只读快照内完成读取和规范化，关闭事务后传输内存文件。预览内容指纹绑定账号、范围、版本、正文和引用可用性，不含生成时间；下载重新校验，变化返回409。接口新增/ai/materials、/ai/materials/{kind}/{id}、/exports/preview、/exports/download，扩展现有AI契约及行动/复盘采纳投影。

本轮仅工程检查，新增功能、迁移、模拟HTTP、真实模型与浏览器流程均留待集中验证；不启动/迁移日常库。测试目录保持原ID，新增PLAN/EXPORT专项及隔离测试代码，代码完成不能记为功能验收通过。


### 12.1 实际模块与接口

| 模块 | 代码 | 写入/读取职责 |
| --- | --- | --- |
| 六类固定材料 | `ai_materials.py` | 归属、归档、固定修订与字段白名单；预览、任务执行、重试和收件箱共用 |
| 新候选与采纳 | `ai_planning.py` | 输出格式/Unicode 引用定位、调用行动或复盘服务、保存采纳及逐字段引用 |
| 模型分派 | `ai_prompts.py`、`ai_data.py`、`ai_commands.py` | 明确按任务类型分派，旧类型约束不放宽 |
| 导出投影 | `export_data.py`、`api_exports.py` | 白名单、有限引用遍历、只读快照、内容指纹与内存附件 |
| 前端 | `ai-planning-create.tsx`、`ai-planning-review.tsx`、`ai-adoption.tsx`、`export-page.tsx` | 明确选材、预览、逐条/逐字段确认和下载 |

`GET /ai/materials` 按任务类型、对象类型、项目、关键词分页；`GET /ai/materials/{kind}/{id}?revision_id=…` 返回选定版本字段和当前版本摘要。周期复盘只展示已关联材料的摘要，不递归读取正文。`GET /exports/candidates` 为手选导出提供九种正式对象的分页列表；POST 预览/下载沿用会话、Origin 与 CSRF。

输入表新增 `selected_current_version`：固定修订是分析依据，选择时当前版本是并发基线。主动选择旧修订不等于生成后发生变化；以后当前版本偏离选择基线才提示新复核。旧任务该列为空，仍以原固定版本判断变化。采纳提交所有显式输入当前版本，再次变化返回冲突；明确复核只记录确认，不替换旧依据。提示词分别为 `m5.actions.v1`、`m5.reflection.v1`。

行动采纳服务强制 planned/空结果，校验方向与来源复盘来自所选对象。`AIAdoption.final_content` 保存实际采纳文本、当时理由和不确定性；引用分离到 `AIAdoptionCitation`，只关联采纳用到的输入、字段和 Unicode 起止位置。复盘采用前后字段比对，服务端重新计算追加全文，和前端最终预览不一致即拒绝。目标标题/项目/日期/材料保持原值，业务版本和建议事件同事务提交。

### 12.2 导出契约与解析

规范格式 `yanji.business.v1`：

| 顶层字段 | 含义 |
| --- | --- |
| `format_version`、`exported_at` | 格式版本和本次生成 UTC 时间 |
| `selection` | 规范化格式、范围、对象类型、项目/对象 ID 与归档选择 |
| `objects` | 所选正式对象当前版本；`kind` 为业务类型，问题/发现/方向及成长等差异类型另存 `subtype` |
| `fixed_versions` | 实际证据引用或采纳关联的不可变修订，按修订 ID 去重；删除来源只有不可用占位 |
| `source_versions` | 记录快照实际使用的原始材料版本，去重并校验归属 |
| `graph_nodes` | 业务对象与地图节点的稳定映射，不含坐标 |
| `links` | 范围外普通对象链接摘要；能力标签保留名称、说明、归档信息 |

项目范围内关系按至少一端属于所选项目收录；端点属于归档项目时默认排除，需要显式包含归档。普通端点只返回标识与摘要，不沿地图邻居扩展。项目内成长引用的账号级标签保留在必要关联摘要中，全部范围可导出完整标签。

固定引用链以队列与修订 ID 集合迭代处理，不递归展开所有正文；循环历史引用只访问一次。引用正文与删除/归档状态逐层校验；删除记录的原始材料、引用片段均不输出。当前业务对象可附采纳历史，但只读取实际采纳字段的引用；不序列化任务、配置或原候选。手动编辑后的当前字段不会因为附了历史采纳信息就被标记为 AI 生成。

两个导出 POST 在 `security.db_session` 中使用显式 `BEGIN`（其他写操作仍 `BEGIN IMMEDIATE`）；身份校验和投影共享同一 SQLite 读取快照，生成内存内容后 rollback 结束事务再返回附件。SHA-256 指纹绑定账号、规范化选择和完整投影（含版本/引用可用性），排除变化的生成时间；下载重新读取、重新验证，变化返回 `export_changed`。不保存长期导出文件或后台导出任务。

5,000 项边界包括对象、固定版本、来源版本、必要映射/摘要；生成时也检查 20 MiB UTF-8 内容上限。空范围为 `export_empty`，超限为 `export_too_large`。Markdown 使用同一投影，目录/内部锚点由程序生成，用户正文按字面转义，来源链接仅 HTTP/HTTPS。不同格式切换保留范围，移除不支持类型时明确提示。

### 12.3 迁移与本轮检查边界

`0005_m5a` 原生增加任务/建议可空外键及任务参数；输入子表使用批处理保留旧行并替换六类 XOR 约束，新增选择时版本。新采纳表在输入表重建后创建，避免新子引用阻碍重建。未修改 0001–0004。`scripts/check_m5_schema.py` 只捕获迁移声明并和 ORM DDL 比较，不建引擎、不打开数据库；实际带 M4 数据升级、SQLite 外键与回滚仍待集中执行。日常库升级前停服备份，主密钥另存。
