# Client Secret 文件迁移记录

## 概述
将 YouTube OAuth 认证所需的 `client_secret_xxx.json` 文件从根目录移动到 `config/` 文件夹，以实现更好的项目组织。

## 迁移的文件

### 移动前位置（根目录）：
1. `client_secrets_ocreativeteen.json` → `config/client_secrets_ocreativeteen.json`
2. `client_secret_creative4teen.json` → `config/client_secret_creative4teen.json`
3. `client_secret_myhomefunpic.json` → `config/client_secret_myhomefunpic.json`

## 更新的代码文件

### config.py
更新了 `channel_config` 中的 `channel_key` 路径：

```python
channel_config = {
    "strange_zh": {
        # ... 其他配置 ...
        "channel_key": "config/client_secrets_ocreativeteen.json"  # 更新路径
    },
    "cristian_zh": {
        # ... 其他配置 ...
        "channel_key": "config/client_secret_creative4teen.json"  # 更新路径
    },
    "travel_zh": {
        # ... 其他配置 ...
        "channel_key": "config/client_secret_myhomefunpic.json"  # 更新路径
    }
}
```

## 影响的功能

这些文件被以下代码使用：

1. **YouTube 视频上传** (`utility/youtube_downloader.py`)
   - 用于 OAuth 2.0 认证流程
   - 获取 YouTube API 访问权限

2. **工作流程视频上传** (`magic_workflow.py`)
   - 自动上传生成的视频到指定频道

3. **独立上传脚本** (`run_youtube_downloader.py`)
   - 手动上传视频功能

## 验证

✅ 所有文件已成功移动到 `config/` 文件夹
✅ `config.py` 中的路径已更新
✅ 现有功能应继续正常工作，无需额外更改

## 文件目录结构

```
Movie_Maker/
├── config/
│   ├── client_secrets_ocreativeteen.json     # 聊斋新语频道
│   ├── client_secret_creative4teen.json      # 心意更新频道  
│   ├── client_secret_myhomefunpic.json       # 旅途故事频道
│   ├── token_default.json                    # OAuth 令牌
│   └── token_strange_zh.json                 # OAuth 令牌
├── config.py
└── ... 其他文件
```

## 注意事项

- 这是一个纯粹的文件组织改进，不影响任何功能
- OAuth 令牌文件（`token_*.json`）已经在 `config/` 文件夹中
- 确保 `config/` 文件夹在版本控制中被适当处理（通常这些认证文件应该被忽略） 