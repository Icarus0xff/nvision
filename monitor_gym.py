#!/usr/bin/env python3
"""
健身房排期监控脚本
每秒检测一次，从 DuckDB 读取最新 OCR 文本，匹配健身房申请通知
"""

import time
import re
import json
from pathlib import Path
from datetime import datetime

import db

# 已处理的 detection_id 记录文件
_PROCESSED_FILE = Path(__file__).parent / '.gym_processed.json'


# 健身房排期文本的关键特征（简化版）
GYM_PATTERNS = {
    'gym': r'健身房',
    'date': r'\d+\s*月\s*\d+\s*日',
    'email': r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
}


def check_gym_notification(text: str) -> dict:
    """
    检查文本是否为健身房排期通知（简化版：匹配 2 个以上即可）
    :param text: OCR 识别的完整文本
    :return: 匹配结果字典
    """
    if not text:
        return {'is_gym_notice': False, 'matched_patterns': []}
    
    matched = []
    for pattern_name, pattern in GYM_PATTERNS.items():
        if re.search(pattern, text, re.IGNORECASE):
            matched.append(pattern_name)
    
    # 匹配 2 个以上且必须包含"健身房"就判定为健身房通知
    is_gym_notice = len(matched) >= 2 and 'gym' in matched
    
    return {
        'is_gym_notice': is_gym_notice,
        'matched_patterns': matched,
        'match_count': len(matched),
        'text_preview': text[:100] + '...' if len(text) > 100 else text
    }


def extract_gym_info(text: str) -> dict:
    """
    从健身房通知中提取关键信息（简化版）
    :param text: OCR 文本
    :return: 提取的信息字典
    """
    info = {'date_range': None, 'email': None}
    
    # 提取日期（允许空格）
    date_match = re.search(r'(\d+\s*月\s*\d+\s*日.*?\d+\s*月\s*\d+\s*日)', text, re.DOTALL)
    if date_match:
        info['date_range'] = date_match.group(0)
    
    # 提取邮箱
    email_match = re.search(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', text)
    if email_match:
        info['email'] = email_match.group(1)
    
    return info


def monitor(db_path: str = None, interval: int = 1, show_all: bool = False):
    """
    持续监控数据库中的 OCR 结果
    :param db_path: 数据库路径
    :param interval: 检测间隔（秒）
    :param show_all: 是否显示所有 OCR 结果（包括不匹配的）
    """
    if db_path is None:
        db_path = db.get_db_path()
    
    if not Path(db_path).exists():
        print(f"数据库不存在：{db_path}")
        return
    
    print(f"🔍 开始监控健身房排期通知")
    print(f"数据库：{db_path}")
    print(f"检测间隔：{interval} 秒")
    print(f"按 Ctrl+C 停止\n")
    
    last_checked_id = 0
    last_gym_notice = None
    
    try:
        while True:
            # 查询最新的 OCR 结果
            results = db.query_recent_data(db_path, limit=1)
            
            if results:
                latest = results[0]
                full_text = latest.get('full_text', '')
                timestamp = latest.get('timestamp', '')
                
                # 检查是否匹配健身房通知
                match_result = check_gym_notification(full_text)
                
                # 只有当发现新的健身房通知时才提醒
                if match_result['is_gym_notice']:
                    # 避免重复提醒同一条
                    if last_gym_notice != full_text:
                        print("\n" + "="*60)
                        print(f"🚨 发现健身房排期通知！")
                        print(f"时间：{timestamp}")
                        print(f"匹配特征：{', '.join(match_result['matched_patterns'])}")
                        print(f"匹配度：{match_result['match_count']}/{len(GYM_PATTERNS)}")
                        print(f"\n📋 完整文本：\n{full_text}")
                        
                        # 提取关键信息
                        gym_info = extract_gym_info(full_text)
                        if gym_info['date_range'] or gym_info['email']:
                            print(f"\n📌 关键信息：")
                            if gym_info['date_range']:
                                print(f"   使用期：{gym_info['date_range']}")
                            if gym_info['email']:
                                print(f"   申请邮箱：{gym_info['email']}")
                        
                        print("="*60 + "\n")
                        
                        last_gym_notice = full_text
                elif show_all:
                    # 显示所有 OCR 结果（调试用）
                    preview = full_text[:50] + '...' if len(full_text) > 50 else full_text
                    print(f"[{timestamp}] OCR: {preview} (匹配：{match_result['match_count']}/{len(GYM_PATTERNS)})")
            
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print("\n\n⏹️  监控已停止")


def _load_processed_ids() -> set:
    """加载已处理的 detection_id 集合"""
    if _PROCESSED_FILE.exists():
        try:
            data = json.loads(_PROCESSED_FILE.read_text())
            return set(data.get('processed_detection_ids', []))
        except (json.JSONDecodeError, KeyError):
            return set()
    return set()


def _save_processed_ids(ids: set):
    """保存已处理的 detection_id 集合"""
    # 只保留最近 200 条，避免文件无限增长
    ids_list = sorted(ids)[-200:]
    _PROCESSED_FILE.write_text(json.dumps({'processed_detection_ids': ids_list}, indent=2))


def check_once(db_path: str = None) -> bool:
    """
    只检查一次最新的 OCR 结果，已处理过的不会重复触发
    :param db_path: 数据库路径
    :return: True 如果检测到**新的**健身房通知，否则 False
    """
    if db_path is None:
        db_path = db.get_db_path()
    
    # 加载已处理记录
    processed_ids = _load_processed_ids()
    
    # 查询最近的 OCR 结果（多查几条以覆盖多个 detection）
    results = db.query_recent_data(db_path, limit=30)
    
    if not results:
        print("暂无 OCR 数据")
        return False
    
    # 遍历结果，找到未处理的健身房通知
    skipped_keys = set()
    for r in results:
        full_text = r.get('full_text', '') or ''
        match_result = check_gym_notification(full_text)
        
        if match_result['is_gym_notice']:
            # 用日期范围作为唯一标识（同一通知的多个 text_block 共享同一 full_text）
            gym_info = extract_gym_info(full_text)
            notice_key = gym_info.get('date_range') or full_text[:80]
            
            # 检查是否已处理
            if notice_key in processed_ids:
                skipped_keys.add(notice_key)
                continue
            
            # 新的健身房通知！
            print(f"最新 OCR 文本：\n{full_text}\n")
            print("✅ 匹配到新的健身房排期通知！")
            print(f"匹配特征：{', '.join(match_result['matched_patterns'])}")
            
            if gym_info['date_range'] or gym_info['email']:
                print(f"\n关键信息：")
                if gym_info['date_range']:
                    print(f"  使用期：{gym_info['date_range']}")
                if gym_info['email']:
                    print(f"  申请邮箱：{gym_info['email']}")
            
            # 标记为已处理
            processed_ids.add(notice_key)
            _save_processed_ids(processed_ids)
            
            return True
    
    # 没有找到未处理的健身房通知
    if skipped_keys:
        print(f"⏭️ 健身房通知已处理过，跳过（{len(skipped_keys)} 条，标识：{', '.join(skipped_keys)}）")
    latest = results[0]
    full_text = latest.get('full_text', '') or ''
    print(f"最新 OCR 文本：\n{full_text}\n")
    print("❌ 未匹配到新的健身房排期通知")
    match_result = check_gym_notification(full_text)
    print(f"匹配特征：{match_result['matched_patterns']} ({match_result['match_count']}/{len(GYM_PATTERNS)})")
    return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="健身房排期监控")
    parser.add_argument("--db-path", default=None, help="DuckDB 数据库路径")
    parser.add_argument("--interval", type=int, default=1, help="检测间隔（秒）")
    parser.add_argument("--show-all", action="store_true", help="显示所有 OCR 结果")
    parser.add_argument("--check-once", action="store_true", help="只检查一次")
    args = parser.parse_args()
    
    print("🏋️ 健身房排期监控（简化版）\n")
    
    if args.check_once:
        detected = check_once(args.db_path)
        # 返回退出码：检测到健身房返回 0，否则返回 1
        import sys
        sys.exit(0 if detected else 1)
    else:
        monitor(args.db_path, args.interval, args.show_all)
