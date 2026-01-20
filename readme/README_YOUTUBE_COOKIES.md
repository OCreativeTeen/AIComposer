# YouTube Cookies 导出指南

## 问题说明

错误信息：`Failed to decrypt with DPAPI`

**原因**：Windows 的数据保护 API (DPAPI) 无法解密浏览器的 cookies 数据库。这通常发生在：
- Chrome/Edge 浏览器正在运行时
- 用户权限不匹配时
- 浏览器配置文件加密时

## 解决方案（3种方法）

---

### 方法 1：使用提供的导出脚本（最简单）

#### 步骤：

1. **关闭所有浏览器窗口**（重要！）

2. **运行导出脚本**：
   ```powershell
   # 双击运行
   export_youtube_cookies.bat
   
   # 或使用 PowerShell
   .\export_youtube_cookies.ps1
   ```

3. **选择你的浏览器**（1-3）

4. **等待导出完成**

5. **重启程序**

---

### 方法 2：使用浏览器扩展（推荐，最可靠）

#### Chrome/Edge 用户：

1. **安装扩展**：
   - 访问：https://chrome.google.com/webstore
   - 搜索：`Get cookies.txt LOCALLY`
   - 安装扩展

2. **导出 Cookies**：
   - 访问并登录：https://www.youtube.com
   - 点击扩展图标
   - 选择 "Export" 或 "Download"
   - 保存为：`www.youtube.com_cookies.txt`

3. **放置文件**：
   - 将 `www.youtube.com_cookies.txt` 放入项目文件夹
   - 例如：`D:\AIComposer\project\p202601151428\`

#### Firefox 用户：

1. **安装扩展**：
   - 访问：https://addons.mozilla.org
   - 搜索：`cookies.txt`
   - 安装扩展

2. 其余步骤同上

---

### 方法 3：使用 yt-dlp 命令行（手动）

#### 前提条件：
- 必须完全关闭浏览器
- 必须已登录 YouTube

#### PowerShell 命令：

```powershell
# 进入项目文件夹
cd "D:\AIComposer\project\p202601151428"

# 从 Chrome 导出
yt-dlp --cookies-from-browser chrome --cookies www.youtube.com_cookies.txt "https://www.youtube.com"

# 从 Edge 导出
yt-dlp --cookies-from-browser edge --cookies www.youtube.com_cookies.txt "https://www.youtube.com"

# 从 Firefox 导出
yt-dlp --cookies-from-browser firefox --cookies www.youtube.com_cookies.txt "https://www.youtube.com"
```

---

## 验证 Cookies 文件

### 检查文件：

```powershell
# 检查文件是否存在
Test-Path www.youtube.com_cookies.txt

# 查看文件大小（应该 > 0）
(Get-Item www.youtube.com_cookies.txt).Length

# 查看文件内容前几行
Get-Content www.youtube.com_cookies.txt -Head 5
```

### 正确的 Cookies 文件格式：

```
# Netscape HTTP Cookie File
.youtube.com	TRUE	/	FALSE	1735689600	VISITOR_INFO1_LIVE	abc123...
.youtube.com	TRUE	/	FALSE	1735689600	YSC	def456...
```

---

## 故障排除

### 问题 1：DPAPI 解密失败

**解决方案**：
1. 完全关闭浏览器（检查任务管理器）
2. 使用方法 2（浏览器扩展）
3. 以管理员身份运行

### 问题 2：Cookies 文件为空或无效

**解决方案**：
1. 确保浏览器已登录 YouTube
2. 重新导出 cookies
3. 检查文件编码（应为 UTF-8 或 ASCII）

### 问题 3：仍然出现"机器人验证"

**解决方案**：
1. Cookies 可能已过期，重新导出
2. 确保 cookies 包含 YouTube 域名
3. 尝试在浏览器中访问视频，确认能正常播放

---

## 重要提示

### 安全性：
- ⚠️ **不要分享** cookies 文件（包含登录信息）
- ⚠️ **不要提交** cookies 到 Git 仓库
- 🔒 将 `www.youtube.com_cookies.txt` 添加到 `.gitignore`

### 有效期：
- Cookies 通常 **几周到几个月** 后过期
- 如果遇到问题，先尝试重新导出 cookies
- 建议定期更新（每月一次）

### 文件位置：
每个项目都有独立的 cookies 文件：
```
D:\AIComposer\project\p202601151428\www.youtube.com_cookies.txt
D:\AIComposer\project\p202601081625\www.youtube.com_cookies.txt
...
```

---

## 使用程序

导出 cookies 后，重新运行程序：

```powershell
# 激活虚拟环境
.\venv\Scripts\Activate.ps1

# 运行程序
python GUI.py
```

程序启动时会显示：
```
✅ 找到 cookies 文件: D:\AIComposer\project\...\www.youtube.com_cookies.txt
📊 Cookies 文件大小: 12345 字节
🍪 使用 cookies 文件: ...
```

---

## 常见问题

**Q: 为什么不能自动从浏览器提取？**
A: Windows DPAPI 加密导致无法直接解密浏览器的 cookies 数据库。手动导出更可靠。

**Q: 需要为每个项目导出 cookies 吗？**
A: 不需要。可以复制 cookies 文件到其他项目文件夹。

**Q: Cookies 文件安全吗？**
A: Cookies 文件包含登录信息，请妥善保管，不要分享。

**Q: 多久需要更新一次？**
A: 通常几周到几个月。如果遇到验证问题，重新导出即可。

---

## 技术支持

如果以上方法都无法解决问题，请：
1. 检查 yt-dlp 版本：`yt-dlp --version`
2. 更新 yt-dlp：`pip install -U yt-dlp`
3. 查看完整错误日志
4. 尝试不同的浏览器

---

## 参考链接

- yt-dlp GitHub: https://github.com/yt-dlp/yt-dlp
- Cookies 导出指南: https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp
- DPAPI 问题: https://github.com/yt-dlp/yt-dlp/issues/10927
