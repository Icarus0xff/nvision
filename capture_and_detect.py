#!/usr/bin/env python3
"""
三步流程：
1. 运行 capture 生成 small 截图
2. 用 yolo.py 的推理模式对 small 图片进行推理
3. 将推理出的 box 裁剪出来（如果有的话）

用法：
    python capture_and_detect.py --desktop 2 --model runs/detect/runs/detect/wechat_msg_card-2/weights/best.pt
"""

import argparse
import os
import subprocess
import time
from pathlib import Path

import cv2
from rapidocr_onnxruntime import RapidOCR
from ultralytics import YOLO

# 导入数据库模块
import db


def switch_to_desktop(n: int):
    """切换到指定桌面"""
    key_codes = {1: 18, 2: 19, 3: 20, 4: 21, 5: 23, 6: 22, 7: 26, 8: 28, 9: 25}
    key_code = key_codes.get(n)
    if key_code is None:
        raise ValueError(f"不支持的桌面编号：{n} (1-9)")
    script = f'''
    tell application "System Events"
        key code {key_code} using control down
    end tell
    '''
    subprocess.run(['osascript', '-e', script])


def screenshot(path: str):
    """截取屏幕截图"""
    # 确保目录存在
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['screencapture', '-x', path], check=True)


def resize(input_path: str, output_path: str, max_size: int = 1024):
    """缩放图片"""
    base, ext = os.path.splitext(output_path)
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    final_output = f'{base}_{timestamp}{ext}'
    subprocess.run([
        'ffmpeg', '-i', input_path,
        '-vf', f'scale={max_size}:{max_size}:force_original_aspect_ratio=decrease',
        '-y',  # 覆盖输出
        final_output
    ], check=True)
    return final_output


def crop_boxes(image_path: str, results, output_dir: str, db_path: str, screenshot_id: int):
    """
    根据推理结果裁剪出检测框，并保存到数据库
    :param image_path: 原始图片路径
    :param results: YOLO 推理结果
    :param output_dir: 裁剪图片输出目录
    :param db_path: DuckDB 数据库路径
    :param screenshot_id: 截图记录 ID
    :return: (裁剪出的图片路径列表，detection_id 列表)
    """
    img = cv2.imread(image_path)
    if img is None:
        print(f"无法读取图片：{image_path}")
        return [], []

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    cropped_paths = []
    detection_ids = []

    for i, result in enumerate(results):
        boxes = result.boxes
        if len(boxes) == 0:
            print(f"  {Path(image_path).name}: 未检测到目标")
            continue

        for j, box in enumerate(boxes):
            # 获取 box 坐标 (xyxy 格式)
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
            conf = float(box.conf[0])
            cls = int(box.cls[0])
            cls_name = result.names[cls]

            # 裁剪
            cropped = img[y1:y2, x1:x2]
            if cropped.size == 0:
                print(f"  跳过无效裁剪区域：{x1},{y1},{x2},{y2}")
                continue

            # 保存
            base_name = Path(image_path).stem
            crop_path = Path(output_dir) / f"{base_name}_box{j}_{cls_name}_{conf:.2f}.png"
            cv2.imwrite(str(crop_path), cropped)
            cropped_paths.append(str(crop_path))
            print(f"  裁剪：{crop_path.name} (置信度：{conf:.2f}, 类别：{cls_name})")

            # 保存到数据库
            detection_id = db.save_detection(db_path, screenshot_id, j, cls_name,
                                             conf, x1, y1, x2, y2, str(crop_path))
            detection_ids.append(detection_id)

    return cropped_paths, detection_ids


def ocr_on_crops(cropped_paths: list, db_path: str, detection_ids: list):
    """
    对裁剪出的图片进行 OCR 文本提取，保存到 DuckDB
    :param cropped_paths: 裁剪图片路径列表
    :param db_path: DuckDB 数据库路径
    :param detection_ids: 对应的 detection_id 列表
    :return: OCR 结果列表
    """
    ocr = RapidOCR()
    results = []

    print(f"\n=== 步骤 4: OCR 文本提取 ===")
    print(f"对 {len(cropped_paths)} 张裁剪图片进行 OCR...")

    for i, crop_path in enumerate(cropped_paths):
        img = cv2.imread(crop_path)
        if img is None:
            print(f"  跳过无法读取的图片：{crop_path}")
            continue

        detection_id = detection_ids[i] if i < len(detection_ids) else None

        # RapidOCR 返回 (result, elapse) - elapse 可能是 dict 或 float
        ocr_result, elapse = ocr(img)

        # 提取文本信息
        text_blocks = []
        full_text = ""
        if ocr_result:
            for block in ocr_result:
                # block 格式：[[[x1,y1],[x2,y2],[x3,y3],[x4,y4]], text, confidence]
                bbox = block[0]
                text = block[1]
                confidence = float(block[2]) if len(block) > 2 else 0.0
                text_blocks.append({
                    "bbox": bbox,
                    "text": text,
                    "confidence": confidence
                })
                full_text += text + " "

        # elapse 可能是 dict {'det': xx, 'rec': xx, 'cls': xx} 或 float
        ocr_time_ms = 0.0
        if elapse:
            if isinstance(elapse, dict):
                # 取各阶段时间总和
                ocr_time_ms = sum(v for v in elapse.values() if isinstance(v, (int, float))) * 1000
            elif isinstance(elapse, (int, float)):
                ocr_time_ms = elapse * 1000

        # 保存到数据库
        if detection_id:
            db.save_ocr_result(db_path, detection_id, text_blocks, full_text.strip(), ocr_time_ms)

        result_entry = {
            "image_path": crop_path,
            "image_name": Path(crop_path).name,
            "detection_id": detection_id,
            "text_blocks": text_blocks,
            "full_text": full_text.strip(),
            "ocr_time_ms": round(ocr_time_ms, 2)
        }
        results.append(result_entry)

        # 打印简要结果
        if text_blocks:
            print(f"  {Path(crop_path).name}: \"{full_text.strip()}\"")
        else:
            print(f"  {Path(crop_path).name}: 未识别到文字")

    print(f"\nOCR 结果已保存到数据库：{db_path}")
    return results


def main():
    parser = argparse.ArgumentParser(description="Capture + YOLO 推理 + 裁剪检测框")
    parser.add_argument("--desktop", type=int, default=2, help="桌面编号 (1-9)")
    parser.add_argument("--model", required=False, help="YOLO 模型权重路径 (查询模式下可选)")
    parser.add_argument("--max-size", type=int, default=1024, help="截图缩放最大边长")
    parser.add_argument("--conf", type=float, default=0.25, help="推理置信度阈值")
    parser.add_argument("--output-dir", default="wechat/cropped", help="裁剪图片输出目录")
    parser.add_argument("--db-path", default=None, help="DuckDB 数据库路径 (默认：nvision_data.duckdb)")
    parser.add_argument("--skip-ocr", action="store_true", help="跳过 OCR 步骤")
    parser.add_argument("--return-desktop", type=int, default=None, help="完成后切换回的桌面编号 (默认不切换)")
    parser.add_argument("--query", action="store_true", help="查询最近的 OCR 结果并退出")
    parser.add_argument("--limit", type=int, default=10, help="查询结果数量限制 (配合 --query 使用)")
    args = parser.parse_args()

    # 如果是查询模式
    if args.query:
        db_path = args.db_path if args.db_path else db.get_db_path()
        if not Path(db_path).exists():
            raise SystemExit(f"数据库不存在：{db_path}")

        print(f"查询数据库：{db_path}")
        results = db.query_recent_data(db_path, args.limit)

        if not results:
            print("暂无数据")
            return

        print(f"\n最近 {len(results)} 条 OCR 结果:\n")
        for i, r in enumerate(results, 1):
            print(f"{i}. [{r['timestamp']}] Desktop {r['desktop']}")
            print(f"   类别：{r['class_name']} (检测置信度：{r['det_confidence']:.2f})")
            print(f"   裁剪图：{r['cropped_path']}")
            print(f"   OCR 文本：{r['full_text']}")
            print(f"   OCR 置信度：{r['ocr_confidence']:.2f}")
            print()

        return

    # 非查询模式必须指定模型
    if not args.model:
        raise SystemExit("错误：--model 参数是必需的")

    # 初始化数据库
    db_path = args.db_path if args.db_path else db.init_db()
    print(f"使用数据库：{db_path}")

    # 验证模型文件
    model_path = Path(args.model)
    if not model_path.exists():
        raise SystemExit(f"模型文件不存在：{model_path}")

    # 步骤 1: 运行 capture
    print(f"\n=== 步骤 1: 截取桌面 {args.desktop} ===")
    raw_path = f'wechat/desktop{args.desktop}_raw.png'
    small_path = f'wechat/desktop{args.desktop}_small.png'

    print(f"切换到 Desktop {args.desktop}...")
    switch_to_desktop(args.desktop)
    time.sleep(0.4)

    print(f"截取原始截图：{raw_path}")
    screenshot(raw_path)

    print(f"缩放截图：{small_path}")
    final_small_path = resize(raw_path, small_path, args.max_size)
    print(f"Done: {final_small_path}")

    # 保存截图记录到数据库
    screenshot_id = db.save_screenshot(db_path, args.desktop, raw_path, final_small_path,
                                       str(model_path), args.conf)
    print(f"截图记录已保存 (ID: {screenshot_id})")

    # 截图完成后立即切换回指定桌面（如果指定了）
    if args.return_desktop is not None:
        print(f"\n切换回 Desktop {args.return_desktop}...")
        switch_to_desktop(args.return_desktop)
        time.sleep(0.5)
        print(f"已切换到 Desktop {args.return_desktop}，继续处理...\n")

    # 步骤 2: YOLO 推理
    print(f"\n=== 步骤 2: YOLO 推理 ===")
    print(f"加载模型：{model_path}")
    model = YOLO(str(model_path))

    print(f"对 {final_small_path} 进行推理...")
    results = model.predict(
        source=final_small_path,
        conf=args.conf,
        save=True,
        project="runs/detect",
        name="capture_detect",
    )

    # 打印检测结果
    for r in results:
        n_boxes = len(r.boxes)
        print(f"  {Path(r.path).name}: 检测到 {n_boxes} 个目标")
        for box in r.boxes:
            cls = int(box.cls[0])
            conf = float(box.conf[0])
            print(f"    - {r.names[cls]} ({conf:.2f})")

    # 步骤 3: 裁剪检测框
    print(f"\n=== 步骤 3: 裁剪检测框 ===")
    cropped_paths, detection_ids = crop_boxes(final_small_path, results, args.output_dir,
                                              db_path, screenshot_id)

    if cropped_paths:
        print(f"\n完成！共裁剪 {len(cropped_paths)} 张图片：")
        for p in cropped_paths:
            print(f"  - {p}")
    else:
        print("\n未检测到目标，无裁剪输出")

    # 步骤 4: OCR 文本提取
    if not args.skip_ocr and cropped_paths:
        ocr_on_crops(cropped_paths, db_path, detection_ids)
    elif args.skip_ocr:
        print("\n跳过 OCR 步骤")
    elif not cropped_paths:
        print("\n无裁剪图片，跳过 OCR")

    return cropped_paths


if __name__ == "__main__":
    main()
