import json
import subprocess
import time
import pyautogui
from AppKit import NSScreen

def get_screen_resolution():
    """获取主屏幕实际分辨率"""
    screen = NSScreen.mainScreen()
    frame = screen.frame()
    return int(frame.size.width), int(frame.size.height)

def switch_to_desktop(n: int):
    key_codes = {1: 18, 2: 19, 3: 20, 4: 21, 5: 23, 6: 22, 7: 26, 8: 28, 9: 25}
    script = f'''
    tell application "System Events"
        key code {key_codes[n]} using control down
    end tell
    '''
    subprocess.run(['osascript', '-e', script])
    time.sleep(0.8)

def load_coords(json_path: str):
    """从 JSON 加载坐标，返回第一个 box"""
    with open(json_path) as f:
        data = json.load(f)
    # 新格式：data['boxes'][0]['box_tuple']
    if 'boxes' in data and len(data['boxes']) > 0:
        return data['boxes'][0]['box_tuple']
    # 兼容旧格式
    return data.get('box_tuple', [0, 0, 0, 0])

def scale_box(box, img_w, img_h, norm=1000):
    x1, y1, x2, y2 = box
    return (
        int(x1 / norm * img_w),
        int(y1 / norm * img_h),
        int(x2 / norm * img_w),
        int(y2 / norm * img_h),
    )

def click_and_type(x, y, text: str):
    pyautogui.moveTo(x, y, duration=0.3)
    time.sleep(0.2)
    pyautogui.click()
    pyautogui.click()
    time.sleep(0.9)
    # 中文输入用 pyperclip + paste 更可靠
    import pyperclip
    pyperclip.copy(text)
    pyautogui.hotkey('command', 'v')
    time.sleep(0.2)
    # 回车发送
    pyautogui.press('enter')

# ---- 主流程 ----
DESKTOP = 2
COORDS_JSON = 'coords.json'
TEXT = '[微信自动化测试]Hello Dr.Y, Wishing you a wonderful weekend!'
# 截图是缩放到 1024 的，归一化基于截图尺寸
SCREENSHOT_SIZE = 1024

# 1. 切换桌面
print(f'切换到 Desktop {DESKTOP}...')
switch_to_desktop(DESKTOP)

# 2. 读取归一化坐标
box = load_coords(COORDS_JSON)
print(f'归一化坐标: {box}')

# 3. 获取屏幕实际分辨率
screen_w, screen_h = get_screen_resolution()
print(f'屏幕分辨率: {screen_w}x{screen_h}')

# 4. 换算真实坐标（归一化基于截图1024px，再映射到屏幕）
real_box = scale_box(box, screen_w, screen_h)
cx = (real_box[0] + real_box[2]) // 2
cy = (real_box[1] + real_box[3]) // 2
print(f'实际点击坐标: ({cx}, {cy})')

# 5. 点击 + 输入
click_and_type(cx, cy, TEXT)
print('完成！')
