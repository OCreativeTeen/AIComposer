# YouTube 视频信息字段说明

## yt-dlp 返回的频道相关字段

当使用 `yt-dlp` 提取 YouTube 视频信息时,有多个字段可能包含频道名称信息:

### 主要字段 (按推荐优先级排序)

| 字段名 | 说明 | 示例 | 可靠性 |
|-------|------|------|--------|
| `channel` | 频道显示名称 | "心理造夢坊" | ⭐⭐⭐ 最可靠 |
| `uploader` | 上传者名称 | "心理造夢坊" | ⭐⭐⭐ 高可靠 |
| `channel_id` | 频道唯一ID | "UCTgvN0Vfy3BUFTjsyjFjOpQ" | ⭐⭐ 总是存在,但不适合显示 |
| `channel_name` | 频道名称(备选) | "心理造夢坊" | ⭐⭐ 有时可用 |
| `uploader_id` | 上传者ID | "@心理造夢坊" | ⭐ 备选方案 |

### 字段详细说明

#### 1. `channel` (推荐首选)
- **类型**: 字符串
- **说明**: 频道的显示名称,这是用户在 YouTube 上看到的名称
- **特点**: 
  - 最适合用于文件命名和显示
  - 通常是中文或其他语言的可读名称
  - 在大多数情况下都存在
- **示例**: `"心理造夢坊"`, `"TED-Ed"`, `"Crash Course"`

#### 2. `uploader` (备选)
- **类型**: 字符串
- **说明**: 上传者名称,通常与频道名相同
- **特点**:
  - 与 `channel` 几乎相同,但在某些情况下可能略有不同
  - 在旧版本的视频或特殊账户上可能不同
- **示例**: `"心理造夢坊"`, `"TED-Ed"`

#### 3. `channel_id` (唯一但不适合显示)
- **类型**: 字符串
- **说明**: 频道的唯一标识符,由 YouTube 分配
- **特点**:
  - **总是存在**,是最可靠的频道标识
  - 格式固定: `UC` 开头 + 22 个字符
  - 不适合直接显示给用户或用于文件命名
- **示例**: `"UCTgvN0Vfy3BUFTjsyjFjOpQ"`
- **用途**: 适合作为数据库主键或 API 调用参数

#### 4. `uploader_id` (备选)
- **类型**: 字符串
- **说明**: 上传者的自定义 ID 或用户名
- **特点**:
  - 通常以 `@` 开头
  - 可读性较好,但可能包含特殊字符
- **示例**: `"@心理造夢坊"`, `"@TEDEd"`

---
 
## 为什么使用这个顺序?

1. **`channel` 优先**:
   - 最直观,用户友好
   - 适合文件命名和显示
   - 在现代 YouTube API 中通常存在

2. **`uploader` 作为备选**:
   - 与 `channel` 高度相似
   - 在旧视频或特殊情况下可能更可靠
   - 兼容性好

3. **`channel_id` 作为最后备选**:
   - 总是存在,保证不会为空
   - 虽然不美观,但能保证功能正常
   - 对于文件命名,有总比没有好

4. **`'Unknown'` 作为默认值**:
   - 理论上不应该到达这一步
   - 提供最后的安全网

---

### 正常输出示例:
```
📺 频道名称: 心理造夢坊
🔍 调试信息 - channel: 心理造夢坊, uploader: 心理造夢坊, channel_id: UCTgvN0Vfy3BUFTjsyjFjOpQ
```

### 问题输出示例:
```
📺 频道名称: UCTgvN0Vfy3BUFTjsyjFjOpQ
🔍 调试信息 - channel: None, uploader: None, channel_id: UCTgvN0Vfy3BUFTjsyjFjOpQ
```
如果看到这种情况,说明 `channel` 和 `uploader` 字段都缺失了。

---

## 可能导致字段缺失的原因

1. **Cookies 过期或未配置**:
   - YouTube 可能限制未认证用户的信息访问
   - 解决方案: 更新 `youtube_cookies.txt`

2. **网络或区域限制**:
   - 某些地区可能无法完整访问 YouTube API
   - 解决方案: 使用 VPN 或代理

3. **yt-dlp 版本过旧**:
   - 旧版本可能无法正确提取字段
   - 解决方案: 更新到最新版本

4. **YouTube API 变化**:
   - YouTube 可能更改了字段名或结构
   - 解决方案: 检查 yt-dlp 的更新和文档

---

## 文件命名示例

使用改进的频道名获取逻辑后,文件名示例:

### 正常情况:
```
20260118_心理造夢坊_downloads.json
```

### channel/uploader 缺失时:
```
20260118_UCTgvN0Vfy3BUFTjsyjFjOpQ_downloads.json
```

### 完全缺失时(不应该发生):
```
20260118_Unknown_downloads.json
```

---

## 相关文档

- [yt-dlp 官方文档](https://github.com/yt-dlp/yt-dlp)
- [yt-dlp 输出模板](https://github.com/yt-dlp/yt-dlp#output-template)
- [README_YOUTUBE_COOKIES.md](README_YOUTUBE_COOKIES.md) - Cookies 配置指南
- [README_YOUTUBE_TROUBLESHOOTING.md](README_YOUTUBE_TROUBLESHOOTING.md) - 故障排除指南

---

**最后更新**: 2026-01-18
