#!/usr/bin/env python3
"""
用 VLM (LocateAnything) 自动标注微信聊天截图，生成 YOLO26 格式训练数据。

输出目录结构（Ultralytics 标准格式，YOLO26 沿用同一套 txt 标注格式）：

dataset/
├── data.yaml
├── images/
│   ├── train/xxx.png
│   └── val/xxx.png
├── labels/
│   ├── train/xxx.txt   # 每行: class_id x_center y_center width height (均为 0~1 归一化)
│   │                    # 无检测目标的负样本为空 txt（等价于 touch）
│   └── val/xxx.txt
└── check/
    └── xxx.png          # 原图叠加了模型框选结果，供人工核对，不参与训练
        # 无检测的图会以 xxx_NODETECT.png 命名，提醒你确认是真负样本还是模型漏检

用法：
    python gen_yolo_dataset.py --input wechat/raw_screenshots --output dataset --val-ratio 0.1

增量运行：脚本只看 check/ 文件夹——里面已经有对应图片，就说明你之前核对过
这张图没问题，直接跳过、不再调用模型推理。往 input 目录里加新截图后直接重跑
同一条命令即可，只会对 check/ 里还没有的新图跑推理。

核对标注：把 dataset/check 里的图挑几张看一眼，框歪了/漏检了就把对应原图挪出
input 目录（或者标签质量不行的话把 dataset/labels 下对应的 .txt 删掉再重跑），
不需要额外脚本。带 _NODETECT 后缀的图要重点看一下：如果其实是模型漏检而不是
真负样本，把对应的空 .txt 和图片从 images/labels 里删掉，再把原图挪出 input
目录重新处理（或人工标注）。

支持多个类别：默认只有一个类别 "message_card"，如需扩展，改 CLASS_NAMES 并在
prompt / parse 逻辑里区分不同类型的框。
"""

import argparse
import random
import re
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

# ---- 配置 ----
CLASS_NAMES = ["message_card"]  # class_id 0 = message_card；多类别时按顺序追加
MODEL_NAME = "mlx-community/LocateAnything-3B-4bit"
PROMPT = """Locate the entire rounded message container in the WeChat chat window.
Ignore individual characters and text lines.
Return a bounding box covering the whole announcement card, including its background area and all text inside.
Do not include surrounding UI elements.
Requirements:
- Detect all individual message containers/bubbles visible in the screenshot.
- Each message bubble should have its own separate bounding box.
- Include messages from both sides of the chat (left and right aligned).
- Include short messages such as "好的", "嗯嗯", and single-line replies.
- Exclude the input text area, toolbar icons, window borders, and non-message UI elements.
- If multiple messages belong to the same conversation thread, annotate each message separately.
- Exclude pictures.
"""
BOX_RE = re.compile(r'<box><(\d+)><(\d+)><(\d+)><(\d+)></box>')
IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def run_mlx_vlm(image_path: str, prompt: str = PROMPT) -> str:
    result = subprocess.run(
        [
            "python", "-m", "mlx_vlm.generate",
            "--model", MODEL_NAME,
            "--image", image_path,
            "--prompt", prompt,
            "--max-tokens", "512",
            "--temperature", "0.9",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"  [警告] 模型推理失败: {result.stderr.strip()[:300]}")
    return result.stdout


def parse_all_boxes(text: str):
    """解析所有 <box> 标签，返回 0~1000 归一化坐标 (x1, y1, x2, y2)"""
    matches = BOX_RE.findall(text)
    return [tuple(int(x) for x in m) for m in matches]


def dedupe_boxes(boxes):
    seen = set()
    unique = []
    for box in boxes:
        if box not in seen:
            seen.add(box)
            unique.append(box)
    return unique


def to_yolo_line(box, class_id: int = 0) -> str:
    """
    把模型输出的 0~1000 归一化 (x1, y1, x2, y2) 转成 YOLO 格式：
    class_id x_center y_center width height，全部 0~1 归一化。
    模型坐标系已经是归一化的，所以只需除以 1000，不需要图片实际宽高。
    """
    x1, y1, x2, y2 = box
    x1, y1, x2, y2 = x1 / 1000, y1 / 1000, x2 / 1000, y2 / 1000

    # clip 防止模型输出越界
    x1, x2 = sorted((max(0.0, min(1.0, x1)), max(0.0, min(1.0, x2))))
    y1, y2 = sorted((max(0.0, min(1.0, y1)), max(0.0, min(1.0, y2))))

    x_center = (x1 + x2) / 2
    y_center = (y1 + y2) / 2
    width = x2 - x1
    height = y2 - y1

    return f"{class_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}"


CHECK_COLORS = ["red", "lime", "blue", "yellow", "magenta", "orange", "cyan"]


def draw_check_image(image_path: Path, boxes, output_path: Path, width: int = 4):
    """把 0~1000 归一化框画在原图上，另存一份供人工核对，不影响训练数据"""
    img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    img_w, img_h = img.width, img.height

    for i, (x1, y1, x2, y2) in enumerate(boxes):
        real_box = (
            int(x1 / 1000 * img_w),
            int(y1 / 1000 * img_h),
            int(x2 / 1000 * img_w),
            int(y2 / 1000 * img_h),
        )
        color = CHECK_COLORS[i % len(CHECK_COLORS)]
        draw.rectangle(real_box, outline=color, width=width)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path)


def write_data_yaml(output_dir: Path):
    yaml_path = output_dir / "data.yaml"
    names_block = "\n".join(f"  {i}: {name}" for i, name in enumerate(CLASS_NAMES))
    yaml_path.write_text(
        f"path: dataset\n"
        f"train: images/train\n"
        f"val: images/val\n"
        f"nc: {len(CLASS_NAMES)}\n"
        f"names:\n{names_block}\n",
        encoding="utf-8",
    )
    print(f"已写入 {yaml_path}")


def is_already_processed(img_path: Path, check_dir: Path) -> bool:
    """
    只认 check/ 文件夹：里面有对应的图（正常框选结果，或者 _NODETECT 后缀），
    就说明这张图之前跑过、你也核对过了，直接跳过，不重新调用模型推理。
    images/train、images/val 里有没有文件不作为判断依据——那两个目录随时
    可能被你手动清空重建，check/ 才是"确认过"的记录。
    """
    if (check_dir / img_path.name).exists():
        return True
    if (check_dir / f"{img_path.stem}_NODETECT{img_path.suffix}").exists():
        return True
    return False


def process_dataset(input_dir: Path, output_dir: Path, val_ratio: float, seed: int = 42):
    images_train = output_dir / "images" / "train"
    images_val = output_dir / "images" / "val"
    labels_train = output_dir / "labels" / "train"
    labels_val = output_dir / "labels" / "val"
    check_dir = output_dir / "check"
    for d in (images_train, images_val, labels_train, labels_val, check_dir):
        d.mkdir(parents=True, exist_ok=True)

    image_paths = sorted(
        p for p in input_dir.iterdir() if p.suffix.lower() in IMG_EXTS
    )
    if not image_paths:
        print(f"未在 {input_dir} 找到图片")
        return

    random.seed(seed)
    shuffled = image_paths[:]
    random.shuffle(shuffled)
    n_val = max(1, int(len(shuffled) * val_ratio)) if len(shuffled) > 1 else 0
    val_set = set(shuffled[:n_val])

    total_images, total_boxes, negative_count, already_done, new_val_count = 0, 0, 0, 0, 0

    for img_path in image_paths:
        if is_already_processed(img_path, check_dir):
            print(f"跳过（已处理过）: {img_path.name}")
            already_done += 1
            continue

        print(f"\n处理: {img_path.name}")
        output = run_mlx_vlm(str(img_path))
        boxes = dedupe_boxes(parse_all_boxes(output))

        is_val = img_path in val_set
        img_dst_dir = images_val if is_val else images_train
        lbl_dst_dir = labels_val if is_val else labels_train

        if not boxes:
            print("  未检测到目标，记为负样本（空标签）")
            # 图片正常收进 images/，标签为空 txt（相当于 touch），
            # YOLO 训练时会把它当作"该图无目标"的负样本
            shutil.copy2(img_path, img_dst_dir / img_path.name)
            (lbl_dst_dir / (img_path.stem + ".txt")).touch()

            # 核对图加 _NODETECT 后缀，提醒你确认这是真负样本还是模型漏检
            check_dst = check_dir / f"{img_path.stem}_NODETECT{img_path.suffix}"
            shutil.copy2(img_path, check_dst)

            if is_val:
                new_val_count += 1
            negative_count += 1
            print(f"  空标签 -> {lbl_dst_dir / (img_path.stem + '.txt')} ({'val' if is_val else 'train'})")
            print(f"  核对图 -> {check_dst}")
            continue

        if is_val:
            new_val_count += 1
        img_dst = img_dst_dir / img_path.name
        shutil.copy2(img_path, img_dst)

        lbl_dst = lbl_dst_dir / (img_path.stem + ".txt")
        lines = [to_yolo_line(box) for box in boxes]
        lbl_dst.write_text("\n".join(lines) + "\n", encoding="utf-8")

        check_dst = check_dir / img_path.name
        draw_check_image(img_path, boxes, check_dst)

        print(f"  {len(boxes)} 个框 -> {lbl_dst} ({'val' if is_val else 'train'})")
        print(f"  核对图 -> {check_dst}")
        total_images += 1
        total_boxes += len(boxes)

    write_data_yaml(output_dir)

    print(
        f"\n完成：本次新处理正样本 {total_images} 张（标注框总数 {total_boxes}），"
        f"负样本（空标签）{negative_count} 张，"
        f"跳过 {already_done} 张此前已处理过，"
        f"其中新增 val 集 {new_val_count} 张。\n"
        f"核对图片在 {check_dir}，挑几张看看框选准不准，"
        f"尤其是 _NODETECT 后缀的图，确认是真负样本还是模型漏检。"
    )


def main():
    parser = argparse.ArgumentParser(description="生成 YOLO26 格式训练数据")
    parser.add_argument("--input", required=True, help="原始截图所在目录")
    parser.add_argument("--output", default="dataset", help="YOLO 数据集输出目录")
    parser.add_argument("--val-ratio", type=float, default=0.1, help="验证集比例")
    parser.add_argument("--seed", type=int, default=42, help="train/val 切分随机种子")
    args = parser.parse_args()

    process_dataset(Path(args.input), Path(args.output), args.val_ratio, args.seed)


if __name__ == "__main__":
    main()
