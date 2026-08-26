#!/bin/bash
# 循环截图检测：只截图 → YOLO 检测 → OCR → 打印捕捉到的消息
# 用法：bash loop_print.sh   按 Ctrl+C 停止

set -e

# ============ 配置 ============
MODEL_PATH="bestv3.pt"
DESKTOP=2
RETURN_DESKTOP=3
INTERVAL=60
MAX_KEEP=30

# ============ 颜色 ============
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# ============ 前置检查 ============
if [ ! -f "$MODEL_PATH" ]; then
    echo -e "${RED}错误：模型文件不存在 ${MODEL_PATH}${NC}"
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo -e "${RED}错误：未找到 .venv${NC}"
    exit 1
fi

source .venv/bin/activate

echo -e "${BLUE}======================================${NC}"
echo -e "${BLUE}   nvision 消息监控（仅打印）${NC}"
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
        ls -1t "${dir}"/${pattern} 2>/dev/null | tail -n "$delete_count" | while read f; do
            rm -f "${f}"
        done
    fi
}

# ============ 主循环 ============
loop_count=0

while true; do
    loop_count=$((loop_count + 1))
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    echo -e "\n${BLUE}[${timestamp}] ===== 第 ${loop_count} 轮 =====${NC}"

    # 截图 + 检测 + 裁剪 + OCR，输出存到临时文件
    tmp_out=$(mktemp)
    python capture_and_detect.py \
        --model "$MODEL_PATH" \
        --desktop "$DESKTOP" \
        --return-desktop "$RETURN_DESKTOP" \
        > "$tmp_out" 2>&1 || {
            echo -e "${RED}本轮检测失败：${NC}"
            cat "$tmp_out"
            rm -f "$tmp_out"
            if [[ $INTERVAL -gt 0 ]]; then sleep $INTERVAL; fi
            continue
        }

    # 清理旧截图
    cleanup_old_images "wechat" "desktop${DESKTOP}_small_*.png"
    cleanup_old_images "wechat/cropped" "*.png"

    # 只打印 OCR 出的消息
    msgs=$(grep -E '^\s+\S.*\.png: ".*"' "$tmp_out" | sed -E 's/.*\.png: "(.*)"/\1/')
    rm -f "$tmp_out"

    if [ -z "$msgs" ]; then
        echo -e "${YELLOW}（本轮未捕捉到消息）${NC}"
    else
        n=$(echo "$msgs" | wc -l | tr -d ' ')
        echo -e "${GREEN}捕捉到 ${n} 条消息：${NC}"
        i=1
        while IFS= read -r line; do
            echo -e "${CYAN}[${i}]${NC} ${line}"
            i=$((i + 1))
        done <<< "$msgs"
    fi

    # 等待下一轮
    if [[ $INTERVAL -gt 0 ]]; then
        sleep $INTERVAL
    fi
done
