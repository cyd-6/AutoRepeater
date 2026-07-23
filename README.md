# OneBot 智能复读

适用于 AstrBot `>=4.24,<5` 的 OneBot v11（`aiocqhttp`）群聊智能复读插件。

当第 4 位不同群员连续发送归一化后相同的文本时，Bot 会立即复读一次。随后插件使用
LLM 进行严格 JSON 裁决；只有确实需要补充回应时，才把请求交给当前会话的 AstrBot
Agent，继续沿用会话人设、历史、模型和工具。

## 主要功能

- 仅监听 OneBot v11（`AIOCQHTTP`）群聊。
- 每个群独立维护连续消息状态和最近文本历史。
- 文本使用 `re.sub(r"\s+", " ", text).strip()` 归一化。
- 默认由第 4 位不同群员触发；同一群员重复发送不增加人数。
- 不同文本、空文本或非纯文本消息会重置当前连续链。
- 同一连续链只触发一次，并使用按群异步锁避免并发重复触发。
- 每个群记住 Bot 最近复读过的内容；在其他内容触发复读前，不会再次复读相同内容。
- 忽略 Bot 自身消息，所有状态仅驻留内存，插件重载后自动清空。
- 裁决失败、超时、模型缺失或返回格式错误时，只保留复读并记录日志。

## 工作流程

1. 收到 OneBot 群聊消息。
2. 检查群白名单、消息类型和发送者。
3. 归一化纯文本，并在对应群的异步锁内更新连续链。
4. 达到触发人数后立即发送一次归一化文本。
5. 使用指定模型或当前会话模型，结合最近群聊文本进行第一阶段裁决。
6. 裁决为 `true` 时，通过
   `event.request_llm(..., conversation=当前会话)` 交给 AstrBot 正常 Agent 流程。
7. 裁决为 `false` 或发生异常时结束，不向群内发送错误提示。

## 安装

### 从 GitHub 安装

在 AstrBot WebUI 的插件管理页面选择从 GitHub 仓库安装，填写：

```text
https://github.com/cyd-6/AutoRepeater
```

安装完成后重载或启用插件。

### 上传 ZIP

在 AstrBot WebUI 中选择本地 ZIP 安装并上传
`astrbot_plugin_onebot_repeater.zip`。安装包的顶层目录必须是：

```text
astrbot_plugin_onebot_repeater/
```

### 手动安装

把完整源码目录复制到 AstrBot 的 `data/plugins/`：

```text
data/plugins/astrbot_plugin_onebot_repeater/main.py
```

随后在 WebUI 中重载插件。插件没有第三方运行时依赖。

## 配置

| 配置项 | 默认值 | 说明 |
|---|---:|---|
| `trigger_count` | `4` | 触发复读所需的不同群员人数 |
| `history_count` | `20` | 裁决时携带的最近群聊纯文本条数 |
| `decision_model` | 空 | 留空跟随当前会话模型，也可选择独立裁决模型 |
| `group_whitelist` | `[]` | 空列表启用全部群，否则仅启用列出的群号 |
| `decision_timeout` | `30.0` | 第一阶段裁决超时秒数 |
| `decision_prompt` | 内置 | 第一阶段严格 JSON 裁决提示词 |
| `agent_instruction` | 内置 | 裁决通过后交给正常 Agent 的附加指令 |

第一阶段只接受以下结构：

```json
{"should_respond": true}
```

`false` 同样有效，也允许完整的 `json` 代码围栏。多字段、缺字段、字符串布尔值、
解释文字或其他非严格输出均视为裁决失败。

## 隐私与数据

- 群聊历史、发送者集合、连续链和最近复读内容只保存在内存中。
- 插件不会自行写入数据库或创建持久化消息记录。
- 第一阶段裁决使用 `context.llm_generate()`，不会把裁决内容写入当前会话。
- 第二阶段只有在裁决为 `true` 时才进入当前 conversation。
- 实际群聊文本会发送给所选 LLM 提供商，请根据所使用模型服务的隐私政策进行配置。

## 开发与测试

测试不需要连接 QQ、运行 AstrBot 或调用真实 LLM。建议使用 Python 3.10 或更高版本：

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m compileall -q main.py repeater.py tests
ruff check .
```

当前测试覆盖：

- 空白归一化、不同发送者计数和同一发送者重复。
- 消息打断、群隔离、触发后防重复和并发触发。
- 最近已复读内容的去重限制。
- 合法、代码围栏、非法及缺字段的裁决 JSON。
- 第 4 位群员触发且复读先于 LLM 裁决。
- `false` 时仅复读，`true` 时创建绑定当前 conversation 的 Agent 请求。
- 模型异常或超时的静默降级。

## 真实群聊验收

准备 4 个非 Bot QQ 账号和一个已接入 AstrBot 的 OneBot v11 测试群：

1. 启用插件，确认群白名单为空或包含测试群号，并配置可用模型。
2. 让 4 个账号依次发送语义相同、但空格、换行或 Tab 形式不同的文本，例如
   `今晚吃什么`。
3. 确认前三条消息不会触发，第 4 条后 Bot 只复读一次归一化文本。
4. 让第 5 个账号继续发送相同文本，确认同一连续链不会再次触发。
5. 使用其他消息打断链后再次组成相同队形，确认 Bot 不会立即重复刚刚复读过的内容。
6. 先让另一段文本成功触发，再测试原文本，确认原文本可以重新触发。
7. 检查裁决结果：`false` 时只有复读；`true` 时随后出现当前会话 Agent 的自然回应。
8. 将模型设为无效 ID 或缩短超时时间，确认群内没有错误提示，日志记录裁决失败。

## 兼容性

- AstrBot：`>=4.24,<5`
- 平台：`aiocqhttp`
- Python：随对应 AstrBot 版本
- 运行时依赖：无额外第三方依赖

## 许可证

本项目使用仓库中的 [GNU Affero General Public License v3.0](LICENSE)。

