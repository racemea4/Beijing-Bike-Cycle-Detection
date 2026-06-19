#!/usr/bin/env python3
"""
自动翻译监控脚本（安全版）
监视文件夹，有新PDF放入时自动翻译，并移动到以原文件名前10字符+翻译结果命名的子文件夹。
首次运行自动在桌面创建所需的三个文件夹，并提示输入 DeepSeek API Key。
"""

import os
import sys
import time
import shutil
import subprocess
import json
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ========== 配置 ==========
# 自动获取当前用户的桌面路径
DESKTOP = Path(os.path.expanduser("~/Desktop"))

# 三个文件夹路径（位于桌面）
WATCH_FOLDER = DESKTOP / "英文论文"
OUTPUT_FOLDER = DESKTOP / "论文翻译"
PROCESSING_FOLDER = DESKTOP / "临时处理论文"

# 自动获取当前用户目录，拼接 pdf2zh 路径
USER_HOME = os.path.expanduser("~")
PDF2ZH_CMD = os.path.join(USER_HOME, "pdf2zh-env", "Scripts", "pdf2zh_next.exe")

LANG_OUT = "zh-CN"
CONFIG_FILE = Path(__file__).parent / ".pdf_translate_config.json"
# ==========================

def ensure_folders():
    """检测并创建所需的三个文件夹"""
    folders_created = []
    for folder in [WATCH_FOLDER, OUTPUT_FOLDER, PROCESSING_FOLDER]:
        if not folder.exists():
            folder.mkdir(parents=True, exist_ok=True)
            folders_created.append(str(folder))
    return folders_created

def check_pdf2zh():
    """检查 pdf2zh_next.exe 是否存在，如果不存在则提示用户输入"""
    if os.path.exists(PDF2ZH_CMD):
        return PDF2ZH_CMD
    
    print("\n" + "=" * 60)
    print("⚠️ 未找到 pdf2zh_next.exe")
    print("=" * 60)
    print(f"默认搜索路径: {PDF2ZH_CMD}")
    print("-" * 60)
    print("请确保已安装 pdf2zh：")
    print("  pip install pdf2zh")
    print("  或参考: https://github.com/Byaidu/PDFMathTranslate")
    print("-" * 60)
    
    while True:
        custom_path = input("请输入 pdf2zh_next.exe 的完整路径（直接回车使用默认路径）: ").strip()
        if not custom_path:
            print(f"将使用默认路径: {PDF2ZH_CMD}")
            print("请确保该文件存在，或重新运行脚本输入正确路径")
            # 返回默认路径，后续会报错提示
            return PDF2ZH_CMD
        if os.path.exists(custom_path):
            return custom_path
        print(f"❌ 路径不存在: {custom_path}，请重新输入")

def load_api_key():
    """从配置文件加载 API Key"""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                key = config.get('deepseek_api_key', '')
                if key:
                    return key
        except:
            pass
    return None

def save_api_key(api_key):
    """保存 API Key 到配置文件"""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump({'deepseek_api_key': api_key}, f, indent=2)
    # Windows下设置文件为隐藏
    if os.name == 'nt':
        try:
            import ctypes
            ctypes.windll.kernel32.SetFileAttributesW(str(CONFIG_FILE), 2)
        except:
            pass
    print(f"✅ API Key 已保存至: {CONFIG_FILE}")

def get_api_key_interactive():
    """交互式获取 API Key"""
    print("\n" + "=" * 60)
    print("🔑 首次运行需要设置 DeepSeek API Key")
    print("=" * 60)
    print("请前往 https://platform.deepseek.com/api_keys 获取")
    print("（按 Ctrl+C 可退出）")
    print("-" * 60)

    while True:
        key = input("请输入你的 DeepSeek API Key: ").strip()
        if key:
            confirm = input("确认保存？(y/n): ").strip().lower()
            if confirm in ['y', 'yes', '']:
                save_api_key(key)
                return key
            else:
                print("请重新输入")
        else:
            print("❌ API Key 不能为空，请重新输入")

def translate_pdf(pdf_path, api_key, pdf2zh_path):
    """翻译单个PDF"""
    print(f"🔄 开始翻译: {pdf_path.name}")
    cmd = [
        pdf2zh_path,
        str(pdf_path),
        "--lang-out", LANG_OUT,
        "--deepseek",
        "--deepseek-api-key", api_key,
        "--output", str(PROCESSING_FOLDER),
        "--pool-max-workers", "6"
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        stem = pdf_path.stem
        mono_file = Path(PROCESSING_FOLDER) / f"{stem}-mono.pdf"
        dual_file = Path(PROCESSING_FOLDER) / f"{stem}-dual.pdf"

        if not mono_file.exists() and not dual_file.exists():
            candidates = list(Path(PROCESSING_FOLDER).glob(f"{stem}*.pdf"))
            if candidates:
                mono_found = dual_found = None
                for c in candidates:
                    if "-mono" in c.name:
                        mono_found = c
                    elif "-dual" in c.name:
                        dual_found = c
                mono_file = mono_found if mono_found else (candidates[0] if candidates else None)
                dual_file = dual_found if dual_found else (candidates[1] if len(candidates) > 1 else None)
            else:
                print(f"⚠️ 翻译完成但未找到生成的PDF文件")
                return False, None, None
        return True, mono_file, dual_file

    except subprocess.CalledProcessError as e:
        if "401" in str(e.stderr) or "Unauthorized" in str(e.stderr):
            print("❌ API Key 无效或已过期，请重新设置")
            print("   运行: python pdf_translate_watcher.py --set-key")
        elif "No such file or directory" in str(e.stderr) or not os.path.exists(pdf2zh_path):
            print(f"❌ pdf2zh_next.exe 未找到或无法执行")
            print(f"   当前路径: {pdf2zh_path}")
            print("   请运行: python pdf_translate_watcher.py --set-pdf2zh-path")
        else:
            print(f"❌ 翻译失败: {e}")
            if e.stderr:
                print(e.stderr)
        return False, None, None

def move_files(original_pdf, mono_file, dual_file):
    """移动文件到目标文件夹"""
    stem = original_pdf.stem
    prefix = stem[:10]
    folder_name = f"{prefix}翻译结果"
    dest_folder = Path(OUTPUT_FOLDER) / folder_name
    dest_folder.mkdir(parents=True, exist_ok=True)

    shutil.move(str(original_pdf), str(dest_folder / original_pdf.name))
    for f in [mono_file, dual_file]:
        if f and f.exists():
            shutil.move(str(f), str(dest_folder / f.name))

    glossary_file = Path(PROCESSING_FOLDER) / f"{stem}.zh-CN.glossary.csv"
    if glossary_file.exists():
        shutil.move(str(glossary_file), str(dest_folder / glossary_file.name))
        print(f"📄 术语表已移动: {glossary_file.name}")

    print(f"✅ 所有文件已移动到: {dest_folder}")

def handle_pdf(file_path, api_key, pdf2zh_path):
    """处理单个PDF"""
    pdf_path = Path(file_path)
    if pdf_path.parent == PROCESSING_FOLDER or str(pdf_path.parent).startswith(str(OUTPUT_FOLDER)):
        return
    time.sleep(1)
    success, mono, dual = translate_pdf(pdf_path, api_key, pdf2zh_path)
    if success:
        move_files(pdf_path, mono, dual)
    else:
        print(f"❌ 翻译失败，文件 {pdf_path.name} 留在原地。")

# ========== 事件处理器 ==========
class PDFHandler(FileSystemEventHandler):
    def __init__(self, api_key, pdf2zh_path):
        self.api_key = api_key
        self.pdf2zh_path = pdf2zh_path
        self.processing_files = set()

    def on_created(self, event):
        if not event.is_directory and event.src_path.lower().endswith('.pdf'):
            if event.src_path in self.processing_files:
                return
            self.processing_files.add(event.src_path)
            try:
                time.sleep(0.5)
                handle_pdf(event.src_path, self.api_key, self.pdf2zh_path)
            finally:
                self.processing_files.discard(event.src_path)

    def on_modified(self, event):
        if not event.is_directory and event.src_path.lower().endswith('.pdf'):
            if event.src_path in self.processing_files:
                return
            self.processing_files.add(event.src_path)
            try:
                time.sleep(0.5)
                handle_pdf(event.src_path, self.api_key, self.pdf2zh_path)
            finally:
                self.processing_files.discard(event.src_path)

# ========== 命令行参数处理 ==========
def set_pdf2zh_path_interactive():
    """交互式设置 pdf2zh 路径"""
    print("\n" + "=" * 60)
    print("🔧 设置 pdf2zh_next.exe 路径")
    print("=" * 60)
    print(f"当前路径: {PDF2ZH_CMD}")
    print("-" * 60)

    while True:
        custom_path = input("请输入 pdf2zh_next.exe 的完整路径: ").strip()
        if os.path.exists(custom_path):
            # 保存到配置文件
            config = {}
            if CONFIG_FILE.exists():
                try:
                    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                except:
                    pass
            config['pdf2zh_path'] = custom_path
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
            print(f"✅ pdf2zh 路径已保存: {custom_path}")
            return custom_path
        print(f"❌ 路径不存在: {custom_path}，请重新输入")

def load_pdf2zh_path():
    """从配置文件加载 pdf2zh 路径，如果不存在则使用默认路径"""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                path = config.get('pdf2zh_path', '')
                if path and os.path.exists(path):
                    return path
        except:
            pass
    return PDF2ZH_CMD

# ========== 主程序 ==========
def main():
    # 处理命令行参数
    if len(sys.argv) > 1:
        if sys.argv[1] == "--set-key":
            get_api_key_interactive()
            return
        if sys.argv[1] == "--set-pdf2zh-path":
            set_pdf2zh_path_interactive()
            return

    print("=" * 60)
    print("📄 PDF 自动翻译监控工具")
    print("=" * 60)

    # 1. 检测并创建文件夹
    created = ensure_folders()
    if created:
        print("📁 已在桌面创建以下文件夹：")
        for f in created:
            print(f"   - {f}")
    else:
        print("📁 所需文件夹已存在")

    # 2. 加载或设置 API Key
    api_key = load_api_key()
    if not api_key:
        api_key = get_api_key_interactive()

    # 3. 加载或设置 pdf2zh 路径
    pdf2zh_path = load_pdf2zh_path()
    if not os.path.exists(pdf2zh_path):
        print(f"\n⚠️ 未找到 pdf2zh: {pdf2zh_path}")
        pdf2zh_path = set_pdf2zh_path_interactive()

    print(f"\n📁 监控文件夹: {WATCH_FOLDER}")
    print(f"📤 输出根文件夹: {OUTPUT_FOLDER}")
    print(f"📂 临时处理文件夹: {PROCESSING_FOLDER}")
    print(f"🔧 pdf2zh 路径: {pdf2zh_path}")
    print("\n👉 将PDF文件拖入【英文论文】文件夹，将自动翻译并归类到【论文翻译】文件夹")
    print("按 Ctrl+C 停止监控")
    print("命令行参数:")
    print("  --set-key             重新设置 API Key")
    print("  --set-pdf2zh-path     重新设置 pdf2zh 路径")
    print("-" * 60)

    event_handler = PDFHandler(api_key, pdf2zh_path)
    observer = Observer()
    observer.schedule(event_handler, str(WATCH_FOLDER), recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\n👋 已停止监控")
    observer.join()

if __name__ == "__main__":
    main()
