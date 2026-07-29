#!/usr/bin/env python3
"""
用 gen_yolo_dataset.py 生成的数据训练 YOLO26，然后跑验证 + 推理，
推理结果自动保存成画好框的图片。

用法：
    # 训练 + 验证 + 对 dataset/images/val 里的图跑推理并出框选图
    python train_yolo.py --data dataset/data.yaml

    # 只测试，不训练（用已有权重）
    python train_yolo.py --data dataset/data.yaml --skip-train \
        --weights runs/detect/train/weights/best.pt --test-dir some_new_screenshots

    # 从零开始训练（不用预训练权重）
    python train_yolo.py --data dataset/data.yaml --from-scratch
"""

import argparse
from pathlib import Path

import torch
from ultralytics import YOLO


def pick_device(requested: str) -> str:
    """
    Mac (Apple Silicon) 上如果 torch 支持 MPS，就自动用 GPU，不是只能 CPU。
    requested='auto' 时按 mps -> cuda -> cpu 的顺序挑；也可以用 --device 强制指定。
    """
    if requested != "auto":
        return requested
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def train(model_cfg: str, data: str, epochs: int, imgsz: int, project: str, name: str, device: str):
    model = YOLO(model_cfg)
    model.train(
        data=data,
        epochs=epochs,
        imgsz=imgsz,
        project=project,
        name=name,
        device=device,
        # --- 针对 UI 自动化的关键参数优化 ---
        mosaic=0.0,  # 关闭马赛克增强（破坏 UI 版面结构）
        erasing=0.0,  # 关闭随机遮挡
        hsv_h=0.0,  # 关闭色相抖动（UI 颜色是极强的主征）
        hsv_s=0.1,  # 降低饱和度抖动
        hsv_v=0.1,  # 降低亮度抖动
        degrees=0.0,  # 禁用旋转
        shear=0.0,  # 禁用剪切
        fliplr=0.0,  # 禁用左右翻转（文字和图标不能镜像）
        scale=0.2,  # 减小缩放抖动
    )
    return model


def validate(model: YOLO, data: str):
    metrics = model.val(data=data)
    print("\n验证结果：")
    print(f"  mAP50    : {metrics.box.map50:.4f}")
    print(f"  mAP50-95 : {metrics.box.map:.4f}")
    return metrics


def predict_and_save(model: YOLO, test_dir: str, project: str, name: str, conf: float):
    test_path = Path(test_dir)
    images = sorted(
        p for p in test_path.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    ) if test_path.is_dir() else [test_path]

    if not images:
        print(f"未在 {test_dir} 找到图片，跳过推理")
        return None

    # save=True 会把画好框的图自动存到 project/name 下
    results = model.predict(
        source=[str(p) for p in images],
        conf=conf,
        save=True,
        project=project,
        name=name,
    )

    save_dir = results[0].save_dir if results else None
    print(f"\n推理完成，共 {len(images)} 张图，框选结果保存在：{save_dir}")

    for r in results:
        n_boxes = len(r.boxes)
        print(f"  {Path(r.path).name}: 检测到 {n_boxes} 个目标")

    return results


def main():
    parser = argparse.ArgumentParser(description="训练并测试 YOLO26 模型")
    parser.add_argument("--data", default="dataset/data.yaml", help="data.yaml 路径")
    parser.add_argument("--model-size", default="yolo26s", help="yolo26n/s/m/l/x")
    parser.add_argument("--from-scratch", action="store_true", help="不用预训练权重，从 .yaml 结构开始训练")
    parser.add_argument("--weights", default=None, help="指定已有权重路径（配合 --skip-train 使用）")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--conf", type=float, default=0.25, help="推理置信度阈值")
    parser.add_argument("--device", default="auto", help="mps/cuda/cpu，默认 auto（Mac 上自动优先用 MPS GPU）")
    parser.add_argument("--skip-train", action="store_true", help="跳过训练，直接用 --weights 做验证/推理")
    parser.add_argument("--skip-val", action="store_true", help="跳过验证")
    parser.add_argument("--test-dir", default=None, help="推理用的图片目录，默认取 data.yaml 里的 val 目录")
    parser.add_argument("--project", default="runs/detect", help="结果输出根目录")
    parser.add_argument("--name", default="wechat_msg_card", help="本次运行的子目录名")
    args = parser.parse_args()

    device = pick_device(args.device)
    print(f"使用设备: {device}")

    if args.skip_train:
        if not args.weights:
            raise SystemExit("--skip-train 时必须指定 --weights")
        model = YOLO(args.weights)
    else:
        model_cfg = f"{args.model_size}.yaml" if args.from_scratch else f"{args.model_size}.pt"
        model = train(model_cfg, args.data, args.epochs, args.imgsz, args.project, args.name, device)
        # 训练完之后用 best.pt 做后续验证/推理，效果比训练过程中的最后一轮权重更稳
        best_weights = Path(args.project) / args.name / "weights" / "best.pt"
        if best_weights.exists():
            model = YOLO(str(best_weights))

    if not args.skip_val:
        validate(model, args.data)

    test_dir = args.test_dir
    if test_dir is None:
        # 没指定就用 data.yaml 里配的 val 图片目录
        data_yaml_dir = Path(args.data).parent
        test_dir = str(data_yaml_dir / "images" / "val")

    predict_and_save(model, test_dir, args.project, f"{args.name}_predict", args.conf)


if __name__ == "__main__":
    main()
