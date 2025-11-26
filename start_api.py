#!/usr/bin/env python3
"""
Magic Video API 启动脚本
"""

import sys
import os
import subprocess
from pathlib import Path
import argparse
import config


def check_dependencies():
    """检查必要的依赖"""
    print("🔍 检查依赖环境...")
    
    # 检查Python版本
    if sys.version_info < (3, 8):
        print("❌ Python版本过低，需要3.8+")
        return False
    
    # 检查CUDA
    try:
        import torch
        cuda_available = torch.cuda.is_available()
        print(f"📱 CUDA可用: {cuda_available}")
        if cuda_available:
            print(f"🎮 GPU设备: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A'}")
    except ImportError:
        print("⚠️  PyTorch未安装")
    
    # 检查关键模块
    required_modules = {
        'fastapi': 'fastapi',
        'uvicorn': 'uvicorn', 
        'pydantic': 'pydantic',
        'python-multipart': 'multipart'
    }
    
    missing_modules = []
    for package_name, import_name in required_modules.items():
        try:
            __import__(import_name)
            print(f"✅ {package_name}")
        except ImportError:
            missing_modules.append(package_name)
            print(f"❌ {package_name}")
    
    if missing_modules:
        print(f"\n缺少以下模块: {', '.join(missing_modules)}")
        print("请运行: pip install -r requirements.txt")
        return False
    
    return True


def check_directories():
    """检查和创建必要的目录"""
    print("\n📁 检查目录结构...")
    
    dirs_to_create = [
        f"{config.BASE_MEDIA_PATH}/program/uploads",
        config.PROJECT_DATA_PATH, 
        config.PUBLISH_PATH
    ]
    
    for dir_path in dirs_to_create:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
        print(f"✅ {dir_path}")


def start_server(host="0.0.0.0", port=8000, workers=1, reload=False):
    """启动API服务器"""
    print(f"\n🚀 启动Magic Video API服务器...")
    print(f"📍 地址: http://{host}:{port}")
    print(f"📚 API文档: http://{host}:{port}/docs")
    print("按 Ctrl+C 停止服务\n")
    
    cmd = [
        sys.executable, "-m", "uvicorn", 
        "api_server:app",
        "--host", host,
        "--port", str(port),
        "--workers", str(workers)
    ]
    
    if reload:
        cmd.append("--reload")
    
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\n👋 服务已停止")


def main():
    parser = argparse.ArgumentParser(description="Magic Video API 启动脚本")
    parser.add_argument("--host", default="0.0.0.0", help="绑定主机地址")
    parser.add_argument("--port", type=int, default=8000, help="端口号")
    parser.add_argument("--workers", type=int, default=1, help="工作进程数")
    parser.add_argument("--reload", action="store_true", help="开发模式（自动重载）")
    parser.add_argument("--skip-check", action="store_true", help="跳过环境检查")
    
    args = parser.parse_args()
    
    print("🎬 Magic Video API 启动器")
    print("=" * 40)
    
    if not args.skip_check:
        if not check_dependencies():
            print("\n❌ 环境检查失败，请解决上述问题后重试")
            sys.exit(1)
        
        check_directories()
    
    start_server(
        host=args.host,
        port=args.port, 
        workers=args.workers,
        reload=args.reload
    )

if __name__ == "__main__":
    main() 