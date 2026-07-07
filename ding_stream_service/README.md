# DingTalk Stream 微服务

这是当前项目内的独立微服务，不挂载到 Flask `run.py`。

## 配置

复用项目根目录 `.env`：

```env
DING_STREAM_CLIENT_ID=
DING_STREAM_CLIENT_SECRET=
```

## 启动

```powershell
python -m ding_stream_service
```

也可以使用独立脚本入口：

```powershell
python .\ding_stream_service\run.py
```

## 钉钉命令

```text
查看运行任务 第1页 每页5条
查看停止任务 第1页 每页10条
重启任务 <任务ID>
重启任务 <任务名称>
重启异常任务
重启异常任务 数量10
断点重启 <任务ID>
```

任务重启指令默认使用断点恢复。任务名必须精确匹配且唯一；如果名称重复，请使用任务 ID。
`重启异常任务` 会批量断点重启最近的 `error` 任务，默认 5 个，单次最多 20 个。

当前钉钉告警 markdown 可直接作为输入的一部分，例如：

```text
断点重启
### 告警
- **任务名称**：AAPL回测
- **任务ID**：abcdef12-3456-7890-abcd-ef1234567890
```

所有回复统一使用钉钉机器人 `markdown` 消息类型：

```text
### 标题

- **字段**：值

> 摘要
> 补充说明
```
