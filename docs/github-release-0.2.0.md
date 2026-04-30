# GitHub Release 0.2.0

## 建议仓库 Description

`AI intelligence harness for tracking GitHub updates, trending projects, AI reports, and proactive brief delivery.`

## 建议 Topics

- `ai-agent`
- `agent-harness`
- `python`
- `github`
- `trending`
- `openai`
- `cli`
- `automation`
- `digest`
- `notification`

## 建议 Release Title

`v0.2.0 - From CLI toolset to AI intelligence harness`

## 建议 Release Notes

### Highlights

- 新增统一 harness runtime，不再只是零散 CLI 命令
- 新增 `nextinai chat`，支持常驻对话、追问和动作确认
- 新增事件层 `IntelligenceEvent`，把原始更新提升为更适合浏览和交付的情报对象
- 新增三种简报视图：快讯、深读、对话
- 新增本地任务系统和 `task daemon`，支持主动推送、失败重试和重复发送抑制

### Recommended First Run

```bash
python3 -m venv .venv-nextinai
source .venv-nextinai/bin/activate
pip install -r requirements-dev.txt
pip install -e .
cp .env.example .env
nextinai system init-storage
nextinai chat
```

### Notes

- 当前版本仍然面向个人使用场景，默认采用本地 JSON 存储
- 常驻运行先以本地轮询模式落地，后续可继续扩展到 systemd / Docker 等部署方式
