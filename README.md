# OneBot 智能复读

面向 AstrBot `>=4.24,<5` 的 OneBot v11（`aiocqhttp`）群聊插件。第 4 位不同群员
发送归一化后相同的连续文本时，Bot 立即复读一次；随后由第一阶段 LLM 严格裁决是否
把追加回应交给当前会话的 AstrBot Agent。

## 行为说明

- 只监听 `AIOCQHTTP` 群聊，私聊和其他平台不参与状态。
- 文本按 `re.sub(r"\s+", " ", text).strip()` 归一化。
- 每群独立计数；同一发送者重复不增加人数。
- 不同文本、空文本、图片/At/回复等非纯文本消息会重置连续链。
- 第 4 位不同发送者触发后，同一条连续链只触发一次。
- 每群记住最近一次 Bot 已复读的归一化文本；即使链条被打断，也不会紧接着再次复读同样内容。
- Bot 自身消息完全忽略，不计数也不打断链。
- 最近群聊纯文本、连续链和异步锁都只在内存中保存；重载插件后清空。
- 裁决失败、超时、模型缺失或 JSON 非法时，只保留复读并写日志，不在群里报错。

## 安装

### WebUI 安装 ZIP

在 AstrBot WebUI 的插件管理中选择从本地 ZIP 安装，上传
`astrbot_plugin_onebot_repeater.zip`，然后重载或启用插件。

### 手动安装源码

把完整的 `astrbot_plugin_onebot_repeater` 目录复制到 AstrBot 的
`data/plugins/` 下，最终入口应为：

```text
data/plugins/astrbot_plugin_onebot_repeater/main.py
```

随后在 WebUI 中重载插件。插件没有第三方运行时依赖。

## 配置

| 配置项 | 默认值 | 说明 |
|---|---:|---|
| `trigger_count` | `4` | 触发所需的不同群员人数 |
| `history_count` | `20` | 第一阶段携带的最近群聊纯文本条数 |
| `decision_model` | 空 | 空值跟随当前会话模型，也可指定独立模型 |
| `group_whitelist` | `[]` | 空列表启用全部群，否则只启用列出的群号 |
| `decision_timeout` | `30.0` | 第一阶段超时秒数 |
| `decision_prompt` | 内置 | 要求只输出严格裁决 JSON 的提示词 |
| `agent_instruction` | 内置 | 裁决为 `true` 后交给正常 Agent 的指令 |

第一阶段唯一接受的 JSON 结构是：

```json
{"should_respond": true}
```

`false` 同样有效；完整的 `json` 代码围栏也可解析。多字段、缺字段、字符串布尔值、
解释文字或其他非严格输出都会按裁决失败处理。

第二阶段通过 `event.request_llm(..., conversation=当前会话)` 创建请求，因此沿用当前
会话的人设、历史、模型和 AstrBot 正常 Agent 工具流程。第一阶段使用
`context.llm_generate()` 独立裁决，不把裁决内容写入会话。

## 本地测试

测试不需要 QQ、AstrBot 进程或真实 LLM。建议使用 Python 3.10 或更高版本：

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m compileall -q main.py repeater.py tests
ruff check .
```

测试覆盖归一化、不同发送者计数、同一人重复、消息打断、群隔离、触发后防重复、
并发触发、严格 JSON 解析，以及用模拟 event/context 验证两阶段调用顺序、
conversation 绑定和异常降级。

## 真实群聊验收

准备 4 个非 Bot QQ 账号和一个已接入 AstrBot 的 OneBot v11 测试群：

1. 确认插件启用，群白名单为空或包含测试群号，且当前会话模型可用。
2. 依次由 4 个账号发送以下文本，每个账号只发送一次：
   - 账号 A：`今晚吃什么`
   - 账号 B：` 今晚吃什么 `
   - 账号 C：在“今晚”和“吃什么”之间输入多个空格
   - 账号 D：在两段文字之间输入换行或 Tab，使归一化结果仍为 `今晚吃什么`
3. 确认前三条后 Bot 不复读；第 4 条后 Bot 立即只复读一次 `今晚吃什么`。
4. 再让第 5 个账号发送同样文本，确认同一连续链不会再次触发。
5. 查看 AstrBot 日志及群消息：裁决为 `false` 时没有追加消息；裁决为 `true` 时，
   在复读之后出现由当前会话 Agent 生成的自然回复。
6. 发送图片或不同文本打断链，再由 4 个不同账号重做，确认可以触发新链。
7. 可临时把裁决模型设为无效 ID 或把超时设得很短，确认群内只有复读、没有错误提示，
   且日志记录裁决失败。

当前交付不包含 Git 仓库初始化、许可证、GitHub Actions、GitHub 上传或发布元数据；
`metadata.yaml` 的 `repo` 保持为空。
