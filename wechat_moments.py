#!/usr/bin/env python3
"""
微信朋友圈自动发布脚本
基于 nvision 视觉识别 + pyautogui 自动化

简化流程（直接点击主界面相机图标）：
1. 打开微信主界面
2. 点击左侧/底部的相机图标
3. 在弹出菜单选择"朋友圈"
4. 选择"从相册选择"图片
5. 输入文字
6. 点击"发表"
"""

import subprocess
import time
import json
import pyautogui
from pathlib import Path
from datetime import datetime

# ============ 配置 ============
DESKTOP_NUM = 2  # 微信所在桌面
SCREENSHOT_DIR = Path("wechat")
COORDS_JSON = "coords.json"
ANNOTATED_IMG = "annotated.png"

# 朋友圈各步骤的 VLM prompt 配置
PROMPTS = {
    "moments_icon": "It is the 5th icon from the top in the left sidebar, located directly below the Favorites (cube) icon and right above the Top Stories (target/compass) icon.",
    "camera_icon": "icon: camera",
    "post_button": "button: 发表，Post",
}

# ============ 工具函数 ============

def switch_to_desktop(n: int):
    key_codes = {1: 18, 2: 19, 3: 20, 4: 21, 5: 23, 6: 22, 7: 26, 8: 28, 9: 25}
    key_code = key_codes[n]
    script = f'''
    tell application "System Events"
        key code {key_code} using control down
    end tell
    '''
    subprocess.run(['osascript', '-e', script])

def screenshot(path: str):
    """截图"""
    subprocess.run(['screencapture', '-x', path], check=True)

def resize_image(input_path: str, output_path: str, max_size: int = 1024):
    """使用 ffmpeg 缩放图片"""
    subprocess.run([
        'ffmpeg', '-i', input_path,
        '-vf', f'scale={max_size}:{max_size}:force_original_aspect_ratio=decrease',
        '-frames:v', '1',
        output_path, '-y'
    ], check=True, capture_output=True)

def run_mlx_vlm(image_path: str, prompt: str) -> str:
    """调用 MLX VLM 识别 GUI 元素"""
    result = subprocess.run([
        'python', '-m', 'mlx_vlm.generate',
        '--model', 'mlx-community/LocateAnything-3B-4bit',
        '--image', image_path,
        '--prompt', prompt,
        '--max-tokens', '512',
        '--temperature', '0.4'
    ], capture_output=True, text=True)
    return result.stdout

def parse_box(text: str):
    """解析第一个 <box> 坐标"""
    import re
    pattern = r'<box><(\d+)><(\d+)><(\d+)><(\d+)></box>'
    match = re.search(pattern, text)
    if match:
        return (int(match.group(1)), int(match.group(2)), 
                int(match.group(3)), int(match.group(4)))
    return None

def get_center(box, screen_w, screen_h, norm=1000):
    """将归一化坐标转换为屏幕中心坐标"""
    x1, y1, x2, y2 = box
    real_x1 = int(x1 / norm * screen_w)
    real_y1 = int(y1 / norm * screen_h)
    real_x2 = int(x2 / norm * screen_w)
    real_y2 = int(y2 / norm * screen_h)
    return (real_x1 + real_x2) // 2, (real_y1 + real_y2) // 2

def click_at(x, y, duration=0.3):
    """移动鼠标并点击"""
    pyautogui.moveTo(x, y, duration=duration)
    time.sleep(0.2)
    pyautogui.click()
    time.sleep(0.5)

def long_press_at(x, y, duration=2.0):
    """长按指定位置"""
    pyautogui.moveTo(x, y, duration=0.3)
    time.sleep(0.2)
    pyautogui.mouseDown()
    time.sleep(duration)
    pyautogui.mouseUp()
    time.sleep(0.5)

def click_at(x, y, duration=0.3):
    """移动鼠标并点击"""
    pyautogui.moveTo(x, y, duration=duration)
    time.sleep(0.2)
    pyautogui.click()
    time.sleep(0.5)

def type_text(text: str):
    """输入文本（支持中文）"""
    import pyperclip
    pyperclip.copy(text)
    pyautogui.hotkey('command', 'v')
    time.sleep(0.3)

def get_screen_resolution():
    """获取屏幕分辨率"""
    from AppKit import NSScreen
    screen = NSScreen.mainScreen()
    frame = screen.frame()
    return int(frame.size.width), int(frame.size.height)

# ============ 核心流程 ============

def capture_and_locate(prompt_key: str, description: str = "") -> tuple:
    """
    截图 + VLM 识别，返回中心坐标
    """
    prompt = PROMPTS[prompt_key]
    if description:
        prompt = f"{prompt}, {description}"
    
    # 截图
    raw_path = SCREENSHOT_DIR / f"moments_{prompt_key}_raw.png"
    small_path = SCREENSHOT_DIR / f"moments_{prompt_key}_small.png"
    SCREENSHOT_DIR.mkdir(exist_ok=True)
    
    screenshot(str(raw_path))
    resize_image(str(raw_path), str(small_path))
    
    # VLM 识别
    print(f"🔍 识别：{prompt_key}...")
    output = run_mlx_vlm(str(small_path), prompt)
    print(f"   VLM 输出：{output[:200]}")
    
    box = parse_box(output)
    if not box:
        print(f"❌ 未找到 {prompt_key}")
        return None
    
    screen_w, screen_h = get_screen_resolution()
    center = get_center(box, screen_w, screen_h)
    print(f"✅ {prompt_key} 坐标：{center}")
    return center

def select_image_in_dialog(image_path: str):
    """
    使用 AppleScript 直接控制文件选择对话框（标准化 GUI 操作）
    不需要视觉识别，直接指定文件路径并点击 Open
    
    Args:
        image_path: 图片的完整路径
    """
    # 等待文件选择对话框出现
    print("   ⏳  等待文件选择对话框...")
    time.sleep(1.5)
    
    # 使用 AppleScript 直接操作文件选择对话框
    abs_path = Path(image_path).expanduser().resolve()
    script = f'''
    tell application "System Events"
        tell process "WeChat"
            -- 等待文件选择对话框出现（sheet 或窗口）
            repeat 15 times
                if (count of sheets of window 1) > 0 or exists window "选择图片" or exists window "选择文件" or exists window "Open" then
                    exit repeat
                end if
                delay 0.3
            end repeat
            
            -- 使用 Cmd+Shift+G 打开路径输入框（全局快捷键，不需要定位窗口）
            keystroke "g" using {{command down, shift down}}
            delay 0.5
            
            -- 输入文件路径
            set the clipboard to "{abs_path}"
            keystroke "v" using {{command down}}
            delay 0.3
            
            -- 按回车确认路径
            keystroke return
            delay 0.5
            
            -- 点击"打开"按钮（尝试多种方式）
            try
                -- 尝试 sheet 中的按钮
                if (count of sheets of window 1) > 0 then
                    set theSheet to sheet 1 of window 1
                    if exists button "打开" of theSheet then
                        click button "打开" of theSheet
                    else if exists button "Open" of theSheet then
                        click button "Open" of theSheet
                    else if exists button "选择" of theSheet then
                        click button "选择" of theSheet
                    else
                        -- 找不到按钮就直接回车
                        keystroke return
                    end if
                else
                    -- 尝试独立窗口
                    if exists window "选择图片" then
                        click button "打开" of window "选择图片"
                    else if exists window "选择文件" then
                        click button "打开" of window "选择文件"
                    else if exists window "Open" then
                        click button "Open" of window "Open"
                    else
                        keystroke return
                    end if
                end if
            end try
        end tell
    end tell
    '''
    
    print(f"   📁  选择文件：{abs_path}")
    try:
        result = subprocess.run(['osascript', '-e', script], 
                              capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            print("   ✅ 文件选择成功")
        else:
            print(f"   ⚠️  AppleScript 执行失败：{result.stderr[:100]}")
            print("   🔄  回退到纯键盘操作...")
            # 回退方案：Cmd+Shift+G -> 粘贴路径 -> 回车
            time.sleep(0.5)
            pyautogui.hotkey('command', 'shift', 'g')
            time.sleep(0.3)
            import pyperclip
            pyperclip.copy(str(abs_path))
            pyautogui.hotkey('command', 'v')
            time.sleep(0.3)
            pyautogui.press('return')
            time.sleep(0.5)
            pyautogui.press('return')
    except subprocess.TimeoutExpired:
        print("   ⚠️  AppleScript 超时，回退到键盘操作...")
        pyautogui.hotkey('command', 'shift', 'g')
        time.sleep(0.3)
        import pyperclip
        pyperclip.copy(str(abs_path))
        pyautogui.hotkey('command', 'v')
        time.sleep(0.3)
        pyautogui.press('return')
        time.sleep(0.5)
        pyautogui.press('return')
    
    time.sleep(1.5)

def post_moments(text: str, image_path: str = None):
    """
    发布朋友圈主流程（点击朋友圈 -> 点击 camera -> 直接弹出文件选择 -> 选择图片 -> 粘贴文本 -> 点击发表）
    
    Args:
        text: 朋友圈文字内容
        image_path: 图片路径（可选）
    """
    print("\n" + "="*50)
    print("📱 微信朋友圈自动发布")
    print("="*50)
    
    # Step 1: 切换到微信桌面
    print(f"\n1️⃣  切换到桌面 {DESKTOP_NUM}...")
    switch_to_desktop(DESKTOP_NUM)
    time.sleep(1)
    
    # Step 2: 点击朋友圈图标（左侧边栏第 5 个图标）
    print("\n2️⃣  点击朋友圈图标...")
    coords = capture_and_locate("moments_icon")
    if coords:
        print(f"   🖱️  点击坐标：{coords}")
        click_at(*coords, duration=0.2)
        time.sleep(0.5)
    else:
        print("⚠️  未找到朋友圈图标，请确保微信在主聊天界面")
        return False
    
    # Step 3: 点击相机图标（单击，直接弹出文件选择对话框）
    print("\n3️⃣  点击相机图标...")
    coords = capture_and_locate("camera_icon")
    if coords:
        print(f"   🖱️  点击坐标：{coords}")
        click_at(*coords, duration=0.2)
    else:
        print("⚠️  未找到相机图标，请确保微信在朋友圈界面")
        return False
    
    # Step 4: 如果有图片，在文件选择对话框中选择
    if image_path:
        print(f"\n4️⃣  选择图片：{image_path}")
        select_image_in_dialog(image_path)
        print("   ⏳  等待图片加载到朋友圈编辑界面...")
        time.sleep(2)
    else:
        print("\n4️⃣  跳过图片选择（无图片）")
        time.sleep(1)
    
    # Step 5: 粘贴文本
    print(f"\n5️⃣  粘贴文本：{text[:30]}...")
    type_text(text)
    time.sleep(1)
    
    # Step 6: 识别并点击"发表"按钮
    print("\n6️⃣  识别'发表'按钮...")
    coords = capture_and_locate("post_button")
    if coords:
        print(f"   🖱️  点击坐标：{coords}")
        click_at(*coords)
        time.sleep(1)
        print("\n✅ 朋友圈发布完成！")
    else:
        print("⚠️  未找到'发表'按钮")
        return False
    
    print("="*50)
    return True

# ============ 命令行入口 ============

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="微信朋友圈自动发布工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 使用默认图片路径
  python wechat_moments.py -t "边牧可真上相呐" \
    -i ~/Downloads/边牧可真上相呐_1_童一敏_来自小红书网页版.jpg
  
  # 纯文字朋友圈
  python wechat_moments.py -t "今天天气真好"
  
  # 指定微信在桌面 3
  python wechat_moments.py -t "文字内容" -d 3
""")
    parser.add_argument("-t", "--text", required=True, help="朋友圈文字内容")
    parser.add_argument("-i", "--image", help="图片路径（单张）")
    parser.add_argument("-d", "--desktop", type=int, default=2, help="微信所在桌面编号")
    
    args = parser.parse_args()
    
    # 展开 ~ 路径
    if args.image:
        args.image = Path(args.image).expanduser()
    
    DESKTOP_NUM = args.desktop
    post_moments(args.text, str(args.image) if args.image else None)
