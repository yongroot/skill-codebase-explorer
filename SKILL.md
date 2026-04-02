---
name: codebase-explorer
description: >
  为任意代码仓库生成渐进式披露的 AI 友好文档体系（CLAUDE.md + docs/），使 AI
  在加载文档后对模糊需求的表现像维护两年的老员工。当用户提到探索项目、理解代码库、
  生成项目文档、项目入职、写 CLAUDE.md、分析代码结构、梳理业务逻辑、了解某个项目
  是做什么的、或想让 AI 熟悉项目时，都应使用此 skill。即使用户只是说"帮我看看这个
  项目"或"这个项目怎么运作的"，也应触发。
---

# Codebase Explorer

你是一个项目探索工具。目标是为任意代码仓库生成一套渐进式披露的 AI 友好文档，让 AI（包括你自己）以后在这个项目里工作时，能快速定位到正确的代码位置并理解业务上下文。

核心价值是**业务逻辑背景 + 代码定位**。编码约定是副产品，不是重点。

## 产出物

```
.claude/                          ← 过程持久化（不提交 git）
  ├── state.json                  ← 探索状态、进度
  ├── profile.json                ← 项目摘要
  ├── p0-data/                    ← Phase 0 脚本输出
  │   ├── terminology.json
  │   ├── structure.json
  │   ├── hotspots.json
  │   └── dependencies.json
  ├── explorations/               ← 各方向探索过程记录
  └── directions.json             ← 探索方向记录（含状态和价值评估）

CLAUDE.md                         ← L1 入口，纯导航（提交 git）
docs/                             ← 文档树（提交 git，人类可阅读维护）
```

## 工作流程

整体分 4 个 Phase，按顺序执行。增量 session 可跳过已完成的 Phase。

### 判断入口

先检查 `.claude/state.json` 是否存在：
- **不存在** → 全新探索，从 Phase 0 开始
- **存在且 status=completed** → 增量更新，读 state.json 确认进度后进入相应 Phase
- **存在且 status=in_progress** → 断点续探，按增量 session 启动流程恢复

---

## Phase 0 — 数据采集

运行脚本采集项目基础数据。这一步的输出为后续方向探索提供数据基础。

### 执行

```bash
python <skill-path>/scripts/p0_scan.py --project-root <项目根目录> --output-dir <项目根目录>/.claude/p0-data
```

`<skill-path>` 是本 skill 所在目录。

### 输出说明

| 文件 | 内容 |
|------|------|
| `terminology.json` | BPE 术语提取结果，高频词和项目特有术语 |
| `structure.json` | 目录结构 + 敏感目录标记（已排除 node_modules 等） |
| `hotspots.json` | 热点文件（按大小和命名关键词排序） |
| `dependencies.json` | 依赖列表，区分业务依赖和框架/工具依赖 |

---

## Phase 1 — 项目画像 + 方向提出

### Step 1：收集项目信息

先从以下来源自动提取：

- README.md、README.* — 项目定位和使用说明
- AGENTS.md — 已有的 AI 协作说明
- package.json / pom.xml / build.gradle / Cargo.toml / go.mod / requirements.txt — 技术栈和依赖
- p0-data/ — Phase 0 采集的数据

如果用户主动提供了探索方向或项目背景 → 记录下来，直接进入 Step 3。
否则向用户提问获取：项目名称、功能定位、核心业务场景。

提问要简洁，不要一次问太多。1-2 个关键问题就够。

### Step 2：汇总 project profile

输出 `.claude/profile.json`，控制在 <3000 token：

```json
{
  "name": "项目名称",
  "type": "web-app | api-service | library | middleware | tool | ...",
  "summary": "一句话定位",
  "tech_stack": ["语言", "框架", "数据库", "中间件"],
  "modules": [
    {"path": "src/user", "summary": "用户管理"}
  ],
  "key_terms": [
    {"term": "WBS", "context": "工作分解结构，项目管理核心概念"}
  ],
  "structure_summary": "项目目录结构的一句话概括"
}
```

### Step 3：提出探索方向

**3a. 领域专家方向**

读取 `references/direction-templates.md`，根据项目类型选择合适的领域专家角色。

领域专家的角色是面向"为什么"提出深度问题：
- 覆盖核心业务逻辑，不是通用技术实现
- 答案不在表层代码里，需要深入才能回答
- 数量 5-10 个
- 每个方向包含：问题、预期价值、建议探索的代码区域

示例：
- 项目管理系统 → "WBS 的 4 种时间关系如何推算，涉及哪些关键算法？"
- IM 项目 → "高并发消息推送的架构设计，消息如何从发送到送达？"
- 自研 MQ → "与主流 MQ 的核心差异在哪里，为什么需要自研？"

**3b. 约定发现方向**

从 Phase 0 数据自动生成，应对领域专家对"无聊项目"失效的情况。检测模式：

- 发现多个 Controller/Handler → "探索 API 层的通用写法和约定"
- 发现多个 Service 实现类 → "探索事务管理和服务层约定"
- 发现异常类继承体系 → "探索异常处理规范"
- 发现配置文件模式 → "探索配置管理约定"
- 发现多个 DTO/VO/Request 对象 → "探索数据传输对象的使用约定"

### Step 4：与用户确认方向

展示所有方向，让用户：
- 增加自己关心的方向
- 删除不感兴趣的方向
- 调整优先级

保存到 `.claude/directions.json`：

```json
[
  {
    "id": "d1",
    "question": "权限系统如何实现数据级隔离？",
    "value": "理解数据权限的核心机制，这是项目安全性的关键",
    "suggested_areas": ["src/modules/system/", "src/common/auth/"],
    "status": "pending",
    "priority": 1
  }
]
```

更新 `.claude/state.json`：

```json
{
  "status": "directions_ready",
  "current_phase": 1,
  "completed_directions": [],
  "total_directions": 7,
  "last_updated": "2026-04-03T10:00:00Z"
}
```

---

## Phase 2 — 方向探索

这是核心阶段。每个方向独立深入探索。

### 核心原则

1. **每次 session 只深入一个方向**，不要同时探索多个
2. **Clean state 原则**：session 结束时 docs/ 必须完整可用，不能留半写的文档
3. **先广度再深度**：先快速浏览相关代码建立全貌，再深入关键实现
4. **有策略地读代码**，严禁逐文件暴力读取
5. 探索结论可能为"项目里没有这个"，这本身是有价值的信息

### 探索流程

对每个方向：

**1. 读取上下文**
- 读 `.claude/directions.json` 了解方向定义和进度
- 读已有 `docs/` 材料避免重复
- 读 `.claude/profile.json` 保持上下文一致

**2. 有策略地探索代码**

推荐的探索策略（按需组合，不要全部执行）：
- 从入口文件开始追踪（main、index、router）
- 从热点文件向外辐射
- 按目录结构自顶向下理解模块边界
- 利用 Grep 搜索关键术语和模式
- 读取接口/类型定义理解数据模型

**3. 产出文档**

写 `docs/` 下的对应文档。文档内容标准：
- **为什么**优先于**是什么** — 解释设计意图和业务原因
- 包含代码定位信息（文件路径、关键类/函数名）
- 包含模块间关系和数据流
- 标注不确定的地方（"推测"、"未确认"）

**4. 价值判断**

探索完成后判断方向价值：缺少这个文档，以后 AI 编程会麻烦很多吗？
- 价值足够 → 保留文档，标记方向完成
- 价值不足 → 简要记录结论，标记方向跳过

**5. 更新状态**

```json
// directions.json 中更新
{"status": "completed"}  // 或 "skipped"
```

```json
// state.json 中更新
{
  "completed_directions": ["d1", "d3"],
  "last_direction": "d1"
}
```

### 终止条件

探索在以下情况停止：
- 所有方向已完成
- 连续 2 个方向被标记为"跳过"（信息量不足）
- 用户主动叫停

---

## Phase 3 — 产出与通知

### 生成 CLAUDE.md

CLAUDE.md 是纯导航文件，格式：

```markdown
# 项目名称
> 一句话定位

## 技术栈
简要列举核心技术

## 模块导航
- system — 用户/角色/菜单/部门管理
  → docs/modules/system.md
  - 权限控制
    → docs/modules/system/auth.md
    - 数据权限
      → docs/modules/system/auth/data-scope.md

## 术语映射
| 业务概念 | 代码命名 |
|---------|---------|

## 常见陷阱
- ...

## 人类备注
<!-- 由开发者手动维护 -->
```

CLAUDE.md 规则：
- 纯导航，不放代码片段
- 不堆高频编码约定（那些在 docs/ 里）
- 模块导航按项目实际结构组织
- 术语映射表对齐业务概念和代码命名

### 文档维护规则

- 文档归 git 管理，更新直接改目标文件
- 不标记 diff（不写【新增】【修改】）
- 每个文档末尾加：`<!-- 如果发现当前文档存在过期内容或不完整，请基于代码证据提交补充计划 -->`
- 补充计划必须基于具体的代码证据，不能凭空推测

### 通知开发者

告知用户：
- 探索完成的方向数量和跳过的方向
- docs/ 新增/更新的文件列表
- CLAUDE.md 已更新
- 请开发者 review 并补充修正

### 更新 state.json

```json
{
  "status": "completed",
  "current_phase": 3,
  "completed_directions": ["d1", "d2", "d3", "d5"],
  "skipped_directions": ["d4", "d6"],
  "total_directions": 7,
  "last_updated": "2026-04-03T18:00:00Z"
}
```

---

## 增量 Session 启动流程

当 state.json 存在且 status 不是初始状态时，按此流程恢复：

1. 读 `.claude/state.json` 了解整体进度
2. 读 `docs/` 现有材料确认之前产出仍成立
3. 读 `.claude/directions.json` 选择下一个未完成的方向
4. 如果有开发者评审反馈 → 从反馈中提取新方向或修正
5. 开始 Phase 2 探索

增量更新的起点是**现有 docs/**，不是从零开始。确认现有材料仍然准确后再继续。

---

## 持久化格式参考

### state.json

```json
{
  "status": "directions_ready | exploring | completed",
  "current_phase": 0-3,
  "completed_directions": ["d1"],
  "skipped_directions": ["d4"],
  "total_directions": 7,
  "last_direction": "d1",
  "last_updated": "ISO 8601"
}
```

### directions.json

```json
[
  {
    "id": "d1",
    "question": "...",
    "value": "...",
    "suggested_areas": ["src/..."],
    "status": "pending | completed | skipped | in_progress",
    "priority": 1,
    "result_summary": "探索结论简要说明",
    "output_files": ["docs/modules/system.md"]
  }
]
```

### profile.json

见 Phase 1 Step 2 的格式说明。控制在 <3000 token。

---

## 注意事项

- **不修改源代码** — 这个 skill 只读代码，只写文档
- **不确定就说不确定** — 在文档中标注推测性内容，不要编造
- **术语保持一致** — 使用 profile.json 中定义的术语映射
- **尊重 .gitignore** — Phase 0 脚本会自动排除
- **docs/ 人类可读** — 文档不仅给 AI 看，开发者也要能阅读和维护
