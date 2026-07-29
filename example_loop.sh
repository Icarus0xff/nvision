#!/bin/bash
# 循环截图检测示例脚本
# 循环执行：截图 → YOLO 检测 → 裁剪 → OCR → 关键词匹配 → 触发动作

set -e

# ============ 配置（根据你的环境修改） ============
MODEL_PATH="best.pt"          # YOLO 模型权重路径
DESKTOP=2                      # 截图的 macOS 桌面编号 (1-9)
RETURN_DESKTOP=1               # 截图后切回的桌面
INTERVAL=60                    # 检测间隔（秒）
MAX_KEEP=30                    # 最多保留的历史图片数

# ============ 颜色输出 ============
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ============ 前置检查 ============
if [ ! -f "$MODEL_PATH" ]; then
    echo -e "${RED}错误：模型文件不存在 ${MODEL_PATH}${NC}"
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo -e "${RED}错误：未找到 .venv，请先创建虚拟环境${NC}"
    exit 1
fi

source .venv/bin/activate

echo -e "${BLUE}======================================${NC}"
echo -e "${BLUE}   nvision 循环检测${NC}"
echo -e "${BLUE}======================================${NC}"
echo -e "模型：${YELLOW}${MODEL_PATH}${NC}"
echo -e "截图桌面：${YELLOW}Desktop ${DESKTOP}${NC}"
echo -e "返回桌面：${YELLOW}Desktop ${RETURN_DESKTOP}${NC}"
echo -e "检测间隔：${YELLOW}${INTERVAL}秒${NC}"
echo ""
echo -e "${BLUE}按 Ctrl+C 停止${NC}"
echo ""

# ============ 清理旧文件 ============
cleanup_old_images() {
    local dir="$1"
    local pattern="$2"
    local count
    count=$(ls -1t "${dir}"/${pattern} 2>/dev/null | wc -l | tr -d ' ')
    if [ "$count" -gt "$MAX_KEEP" ]; then
        local delete_count=$((count - MAX_KEEP))
        echo -e "${YELLOW}清理 ${dir}/${pattern}：${count} 张 → 保留 ${MAX_KEEP} 张${NC}"
        ls -1t "${dir}"/${pattern} 2>/dev/null | tail -n "$delete_count" | while read f; do
            rm -f "${dir}/${f}"
        done
    fi
}

# ============ 主循环 ============
loop_count=0

while true; do
    loop_count=$((loop_count + 1))
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    echo -e "\n${BLUE}[${timestamp}] ===== 第 ${loop_count} 次检测 =====${NC}"

    # 截图 + 检测 + 裁剪 + OCR + 入库
    python capture_and_detect.py \
        --model "$MODEL_PATH" \
        --desktop "$DESKTOP" \
        --return-desktop "$RETURN_DESKTOP"

    # 清理旧截图
    cleanup_old_images "wechat" "desktop${DESKTOP}_small_*.png"
    cleanup_old_images "wechat/cropped" "*.png"

    # ---- 在这里添加你的自定义逻辑 ----
    # 例如：关键词匹配后发送通知、执行自动化操作等
    #
    # if python monitor_gym.py --check-once; then
    #     echo -e "${GREEN}检测到目标！${NC}"
    #     # 播放提示音
    #     afplay /System/Library/Sounds/Glass.aiff
    #     # 发送通知
    #     osascript -e 'display notification "检测到目标" with title "nvision"'
    # fi

    # 等待下一次检测
    if [[ $INTERVAL -gt 0 ]]; then
        sleep $INTERVAL
    fi
done
