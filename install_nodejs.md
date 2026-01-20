# 安装 Node.js 以解决 YouTube n 参数挑战

## Windows 安装步骤

### 方法 1: 使用官方安装程序
1. 访问 https://nodejs.org/
2. 下载 LTS 版本 (推荐)
3. 运行安装程序
4. 确保选中 "Add to PATH" 选项
5. 重启终端或命令提示符

### 方法 2: 使用 Chocolatey (如果已安装)
```powershell
choco install nodejs
```

### 方法 3: 使用 Winget
```powershell
winget install OpenJS.NodeJS
```

## 验证安装

安装完成后,在新的终端窗口中运行:
```bash
node --version
npm --version
```

应该看到版本号输出(例如 v20.x.x)

## 重启应用

安装 Node.js 后,关闭并重新启动你的 Python 应用程序。
