# 状态文件 Schema（data/profile.json）

当 `scripts/lifebuddy.py` 不可用，Agent 须按此结构直接用文件工具读写 `{baseDir}/data/profile.json`，保证记忆不丢、不崩溃。

```json
{
  "profile": {
    "name": "用户称呼（可空）",
    "city": "城市（可空，用于天气降级提示）",
    "timezone": "Asia/Shanghai",
    "preferences": { "风格": "文艺", "忌口": "香菜" },
    "important_dates": [
      { "label": "妈妈生日", "date": "MM-DD", "note": "提前准备祝福" }
    ],
    "created_at": "2026-08-27T14:00:00"
  },
  "rpg": {
    "level": 1,
    "exp": 0,
    "coins": 0,
    "streak": 0,
    "last_active": "YYYY-MM-DD",
    "attributes": { "discipline": 0, "health": 0, "study": 0, "social": 0, "joy": 0 },
    "quests": [
      { "id": 1, "title": "写完周报", "attr": "discipline", "reward": 30, "status": "open", "created": "YYYY-MM-DD", "done": "" }
    ],
    "habits": [
      { "name": "早睡", "attr": "health", "streak": 0, "last": "" }
    ],
    "diary": [
      { "date": "YYYY-MM-DD", "text": "今天有点累但还不错" }
    ],
    "badges": [],
    "history": [
      { "date": "YYYY-MM-DD", "note": "副本完成:写完周报", "exp": 30, "attr": "discipline" }
    ]
  }
}
```

## 读写约定
- 写入前先 `load`；若文件不存在或 JSON 损坏，备份为 `profile.json.bak` 后以默认结构重建。
- 任何经验/属性变更后，立即整体写回（原子性：先写临时文件再替换更稳妥）。
- 日记最多保留最近 200 条。
- 不在 `profile`/`rpg` 之外新增字段，避免结构漂移。
