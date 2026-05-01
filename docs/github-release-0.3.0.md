# GitHub Release 0.3.0

## 建议仓库 Description

`AI intelligence harness with chat, Streamlit frontend, GitHub tracking, report analysis, digest generation, and proactive delivery.`

## 建议 Topics

- `ai-agent`
- `agent-harness`
- `python`
- `streamlit`
- `github`
- `trending`
- `openai`
- `automation`
- `digest`
- `notification`

## 建议 Release Title

`v0.3.0 - Streamlit frontend and unified runtime logging`

## 建议 Release Notes

### Highlights

- 新增 Streamlit 前端控制台，支持 Chat、订阅、热门榜、报告、简报、任务统一操作
- 新增 `nextinai web` 启动入口，适合本地持续体验和演示
- 新增统一运行日志，覆盖 assistant、工具执行、报告抓取、简报生成、通知发送、任务执行
- 新增 `nextinai system show-logs`，便于排查“当前到底运行到哪一步”

### Recommended First Run

```bash
python3 -m venv .venv-nextinai
source .venv-nextinai/bin/activate
pip install -r requirements.txt
pip install -e .
cp .env.example .env
nextinai system init-storage
nextinai web
```

### Notes

- 当前前端仍然是本地单机场景，默认适合个人使用
- 日志文件默认写入 `data/nextinai.log`
- 如需体验对话式 agent，也可以直接使用 `nextinai chat`
