#!/usr/bin/env python3

import re
import json
import subprocess
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageDraw

def run_mlx_vlm(image_path: str, prompt: str) -> str:
    result = subprocess.run([
        'python', '-m', 'mlx_vlm.generate',
        '--model', 'mlx-community/LocateAnything-3B-4bit',
        '--image', image_path,
        '--prompt', prompt,
        '--max-tokens', '512',
        '--temperature', '0.1'
    ], capture_output=True, text=True)
    return result.stdout

def parse_all_boxes(text: str):
    """解析所有 <box> 标签"""
    pattern = r'<box><(\d+)><(\d+)><(\d+)><(\d+)></box>'
    matches = re.findall(pattern, text)
    return [tuple(int(x) for x in m) for m in matches]

def scale_box(box, img_w, img_h, norm=1000):
    x1, y1, x2, y2 = box
    return (
        int(x1 / norm * img_w),
        int(y1 / norm * img_h),
        int(x2 / norm * img_w),
        int(y2 / norm * img_h),
    )

def draw_boxes(image_path: str, boxes: list, output_path: str, colors=None, width=4):
    """在图片上绘制多个框"""
    img = Image.open(image_path).convert('RGB')
    draw = ImageDraw.Draw(img)
    
    if colors is None:
        # 默认颜色循环
        colors = ['red', 'green', 'blue', 'yellow', 'purple', 'orange', 'cyan', 'magenta']
    
    for i, box in enumerate(boxes):
        color = colors[i % len(colors)]
        real_box = scale_box(box, img.width, img.height)
        draw.rectangle(real_box, outline=color, width=width)
        print(f'[{i+1}] 坐标 (归一化): {box}')
        print(f'    坐标 (实际 px): {real_box}')
    
    img.save(output_path)
    print(f'标注图保存到：{output_path}')

def save_to_json(boxes: list, output_dir: str = "."):
    """将所有归一化坐标保存到 JSON 文件"""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    json_path = Path(output_dir) / "coords.json"
    
    data = {
        "timestamp": datetime.now().isoformat(),
        "count": len(boxes),
        "boxes": []
    }
    
    for i, box in enumerate(boxes):
        data["boxes"].append({
            "index": i,
            "normalized_box": {
                "x1": box[0],
                "y1": box[1],
                "x2": box[2],
                "y2": box[3]
            },
            "box_tuple": list(box),
            "center": {
                "x": (box[0] + box[2]) / 2,
                "y": (box[1] + box[3]) / 2
            }
        })
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f'坐标 JSON 保存到：{json_path}')
    return str(json_path)

def crop_boxes(image_path: str, boxes: list, output_pattern: str):
    """将每个 box 裁切成独立的图片"""
    img = Image.open(image_path).convert('RGB')
    img_w, img_h = img.width, img.height
    
    cropped_paths = []
    for i, box in enumerate(boxes):
        real_box = scale_box(box, img_w, img_h)
        x1, y1, x2, y2 = real_box
        
        # 裁切图片
        cropped = img.crop((x1, y1, x2, y2))
        
        # 生成输出路径，替换 xxx 为序号
        output_path = output_pattern.replace('xxx', str(i + 1))
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        
        cropped.save(output_path)
        print(f'裁切图片 [{i+1}] 保存到：{output_path} (尺寸：{x2-x1}x{y2-y1})')
        cropped_paths.append(output_path)
    
    return cropped_paths

# ---- 主流程 ----
image = 'wechat/desktop2_small.png'
prompt = """Locate the entire rounded message container in the WeChat chat window. 
Ignore individual characters and text lines. 
Return a bounding box covering the whole announcement card, including its background area and all text inside. 
Do not include surrounding UI elements."""

output = run_mlx_vlm(image, prompt)
print("模型输出:")
print(output)
print()

boxes = parse_all_boxes(output)

# 去重：保留唯一的坐标
unique_boxes = []
seen = set()
for box in boxes:
    if box not in seen:
        seen.add(box)
        unique_boxes.append(box)

print(f"原始找到 {len(boxes)} 个，去重后 {len(unique_boxes)} 个唯一坐标\n")
boxes = unique_boxes

if boxes:
    print(f"找到 {len(boxes)} 个目标:\n")
    draw_boxes(image, boxes, 'annotated.png')
    save_to_json(boxes)
    # 裁切图片到 wechat/messages/xxx1.png
    crop_boxes(image, boxes, 'wechat/messages/xxx1.png')
else:
    print('未找到 <box> 坐标，原始输出：', output)
