import cv2
import numpy as np

# 1. 读取图像
img_path = 'grafana_8_misc001-prd_20260731-113944.png'
img = cv2.imread(img_path)
if img is None:
    print(f'错误：无法读取图片 {img_path}')
    exit()

h, w = img.shape[:2]
print(f'图像尺寸: {w}x{h}')

# ========================================================================
# Grafana 暗色主题面板检测策略：
#   1. 面板间隙颜色 BGR≈(23,18,17)，比面板背景(31,27,24)更暗
#   2. 先通过间隙颜色创建掩码，再投影分析找行/列分隔线
#   3. 逐行分析（因为上下行面板列数/宽度可能不同）
#   4. 过滤掉侧边栏、滚动条等非面板区域
# ========================================================================

# 2. 创建"间隙掩码"
gap_b, gap_g, gap_r = 23, 18, 17
tolerance = 5
lower = np.array([gap_b - tolerance, gap_g - tolerance, gap_r - tolerance], dtype=np.uint8)
upper = np.array([gap_b + tolerance, gap_g + tolerance, gap_r + tolerance], dtype=np.uint8)
gap_mask = cv2.inRange(img, lower, upper)

# 3. 找到内容区域（排除底部纯黑区域）
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
row_means = gray.mean(axis=1)
content_bottom = h
for y in range(h - 1, -1, -1):
    if row_means[y] > 20:
        content_bottom = y + 1
        break

# 4. 找水平分隔线（面板行之间的间隙）
row_gap_ratio = gap_mask[:content_bottom, :].mean(axis=1) / 255.0
row_smooth = np.convolve(row_gap_ratio, np.ones(5) / 5, mode='same')

h_gap_threshold = 0.3
in_gap = False
gap_start = 0
h_gaps = []

for i in range(len(row_smooth)):
    if row_smooth[i] > h_gap_threshold:
        if not in_gap:
            gap_start = i
            in_gap = True
    else:
        if in_gap:
            gap_end = i
            width = gap_end - gap_start
            if width >= 3:
                # 水平覆盖度：这条间隙跨了多少列
                horiz_coverage = gap_mask[gap_start:gap_end, :].mean() / 255.0 * 100
                center = (gap_start + gap_end) // 2
                h_gaps.append((gap_start, gap_end, center, width, horiz_coverage))
            in_gap = False

if in_gap:
    gap_end = len(row_smooth)
    width = gap_end - gap_start
    if width >= 3:
        horiz_coverage = gap_mask[gap_start:gap_end, :].mean() / 255.0 * 100
        center = (gap_start + gap_end) // 2
        h_gaps.append((gap_start, gap_end, center, width, horiz_coverage))

# 区分：标题栏间隙 vs 面板行间隙
# 面板行间隙：水平覆盖度高(>60%)、宽度窄(3-20px)
# 标题栏区域：宽度较大、覆盖度可能也高
panel_row_gaps = []
header_gap = None

for start, end, center, width, coverage in h_gaps:
    if width <= 25 and coverage > 60:
        panel_row_gaps.append((start, end, center))
    elif width > 25 and coverage > 60:
        header_gap = (start, end, center)

print(f'标题栏间隙: {header_gap}')
print(f'面板行间隙: {panel_row_gaps}')

# 5. 构建面板行区域
if header_gap:
    row_regions = []
    # 第一行面板从 header_gap 结束开始
    current_y = header_gap[1]
    for gap in panel_row_gaps:
        row_regions.append((current_y, gap[0]))
        current_y = gap[1]
    row_regions.append((current_y, content_bottom))
else:
    row_regions = [(0, content_bottom)]

print(f'\n面板行区域 ({len(row_regions)} 行):')
for i, (y1, y2) in enumerate(row_regions):
    print(f'  Row {i + 1}: y=[{y1}, {y2}) height={y2 - y1}px')

# 6. 逐行找垂直间隙，构建面板
panels = []

for row_idx, (row_y1, row_y2) in enumerate(row_regions):
    row_height = row_y2 - row_y1
    if row_height < 50:  # 太窄的行跳过
        continue

    # 该行的间隙掩码
    row_gap = gap_mask[row_y1:row_y2, :]
    col_gap_ratio = row_gap.mean(axis=0) / 255.0
    col_smooth = np.convolve(col_gap_ratio, np.ones(5) / 5, mode='same')

    # 找垂直间隙
    v_gap_threshold = 0.3
    in_gap = False
    gap_start = 0
    v_gaps = []

    for i in range(len(col_smooth)):
        if col_smooth[i] > v_gap_threshold:
            if not in_gap:
                gap_start = i
                in_gap = True
        else:
            if in_gap:
                gap_end = i
                width = gap_end - gap_start
                if width >= 3:
                    # 垂直覆盖度
                    vert_coverage = row_gap[:, gap_start:gap_end].mean() / 255.0 * 100
                    v_gaps.append((gap_start, gap_end, (gap_start + gap_end) // 2, width, vert_coverage))
                in_gap = False

    if in_gap:
        gap_end = len(col_smooth)
        width = gap_end - gap_start
        if width >= 3:
            vert_coverage = row_gap[:, gap_start:gap_end].mean() / 255.0 * 100
            v_gaps.append((gap_start, gap_end, (gap_start + gap_end) // 2, width, vert_coverage))

    # 过滤：只保留垂直覆盖度高的间隙（真正的面板分隔线）
    # 覆盖度低的是面板内部的文字/图表产生的假间隙
    real_v_gaps = [g for g in v_gaps if g[4] > 60]

    print(f'\n  Row {row_idx + 1} 垂直间隙 (覆盖度>60%):')
    for start, end, center, width, vc in real_v_gaps:
        print(f'    x=[{start},{end}) center={center} width={width}px vc={vc:.0f}%')

    # 构建该行的列边界
    col_bounds = [0] + [g[2] for g in real_v_gaps] + [w]

    for col_idx in range(len(col_bounds) - 1):
        x1 = col_bounds[col_idx]
        x2 = col_bounds[col_idx + 1]
        pw = x2 - x1
        ph = row_height

        # 计算区域属性
        region = gray[max(0, row_y1):min(h, row_y2), max(0, x1):min(w, x2)]
        if region.size == 0:
            continue
        avg_brightness = region.mean()

        # 过滤条件：
        # - 跳过太小的区域（侧边栏图标、滚动条）
        # - 跳过纯黑区域
        # - 跳过太窄的区域（<100px宽，可能是边栏装饰）
        # - 跳过左侧边栏（x=0..308，Grafana导航侧栏）
        # - 跳过右侧边缘区域
        if pw < 100:
            continue
        if ph < 50:
            continue
        if avg_brightness < 22:
            continue
        # 侧边栏判断：如果左边界是0，且右边界在第一个垂直间隙处
        # 侧边栏的特征是宽度较窄、亮度较低、且紧贴左边
        if x1 == 0 and pw < 400 and avg_brightness < 35:
            continue
        # 右侧边缘区域判断
        if x2 >= w - 80 and pw < 100:
            continue

        panels.append((x1, row_y1, pw, ph, avg_brightness, row_idx + 1, col_idx + 1))

# 7. 输出结果
print(f'\n{"="*60}')
print(f'成功检测到 {len(panels)} 个子 Panel 区域！')
print(f'{"="*60}')

for i, (x, y, pw, ph, br, row, col) in enumerate(panels):
    print(f'  Panel {i + 1} (Row{row}-Col{col}): pos=({x},{y}) size={pw}x{ph} brightness={br:.1f}')

# 8. 绘制结果
res = img.copy()
colors = [
    (0, 255, 0),    # 绿
    (255, 0, 0),    # 蓝
    (0, 255, 255),  # 黄
    (255, 0, 255),  # 品红
    (0, 165, 255),  # 橙
    (255, 255, 0),  # 青
    (0, 128, 255),  # 深橙
    (128, 0, 255),  # 紫
]

for i, (x, y, pw, ph, br, row, col) in enumerate(panels):
    color = colors[i % len(colors)]
    cv2.rectangle(res, (x, y), (x + pw, y + ph), color, 3)
    # 半透明填充
    overlay = res.copy()
    cv2.rectangle(overlay, (x, y), (x + pw, y + ph), color, -1)
    cv2.addWeighted(overlay, 0.15, res, 0.85, 0, res)
    # 标签
    label = f'P{i + 1}'
    cv2.putText(res, label, (x + 10, y + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

cv2.imwrite('result_cards_final.jpg', res)
print(f'\n结果已保存至 result_cards_final.jpg')
