import subprocess
import time

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
    subprocess.run(['screencapture', '-x', path])

def resize(input_path: str, output_path: str, max_size: int = 1024):
    import os
    # 总是生成带时间戳的新文件名
    base, ext = os.path.splitext(output_path)
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    final_output = f'{base}_{timestamp}{ext}'
    subprocess.run([
        'ffmpeg', '-i', input_path,
        '-vf', f'scale={max_size}:{max_size}:force_original_aspect_ratio=decrease',
        final_output
    ])
    return final_output

# 使用
desktop = 2
raw = f'wechat/desktop{desktop}_raw.png'
small = f'wechat/desktop{desktop}_small.png'

switch_to_desktop(desktop)
time.sleep(1)
screenshot(raw)
resize(raw, small)

final_path = resize(raw, small)
print(f'Done: {final_path}')
