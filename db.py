#!/usr/bin/env python3
"""
DuckDB 数据库管理模块
用于存储裁剪图片路径和 OCR 结果
"""

import duckdb
import json
from pathlib import Path
from datetime import datetime


def get_db_path() -> str:
    """获取数据库文件路径"""
    return str(Path(__file__).parent / "nvision_data.duckdb")


def init_db(db_path: str = None):
    """初始化数据库表结构"""
    if db_path is None:
        db_path = get_db_path()
    
    conn = duckdb.connect(db_path)
    
    # 创建截图记录表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS screenshots (
            id INTEGER PRIMARY KEY,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            desktop INTEGER NOT NULL,
            raw_path VARCHAR NOT NULL,
            small_path VARCHAR NOT NULL,
            model_path VARCHAR NOT NULL,
            conf_threshold FLOAT
        )
    """)
    
    # 创建检测框表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS detections (
            id INTEGER PRIMARY KEY,
            screenshot_id INTEGER REFERENCES screenshots(id),
            box_index INTEGER NOT NULL,
            class_name VARCHAR NOT NULL,
            confidence FLOAT NOT NULL,
            x1 INTEGER,
            y1 INTEGER,
            x2 INTEGER,
            y2 INTEGER,
            cropped_path VARCHAR NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 创建 OCR 结果表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ocr_results (
            id INTEGER PRIMARY KEY,
            detection_id INTEGER REFERENCES detections(id),
            text_block_index INTEGER,
            bbox VARCHAR,
            text TEXT,
            confidence FLOAT,
            full_text TEXT,
            ocr_time_ms FLOAT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 创建 ID 计数器表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS id_counters (
            table_name VARCHAR PRIMARY KEY,
            next_id INTEGER DEFAULT 1
        )
    """)
    
    # 初始化计数器
    for table in ['screenshots', 'detections', 'ocr_results']:
        conn.execute("""
            INSERT OR IGNORE INTO id_counters (table_name, next_id) VALUES (?, 1)
        """, [table])
    
    conn.commit()
    conn.close()
    return db_path


def get_next_id(db_path: str, table_name: str) -> int:
    """获取下一个 ID"""
    conn = duckdb.connect(db_path)
    
    # 获取当前 ID
    cursor = conn.execute("SELECT next_id FROM id_counters WHERE table_name = ?", [table_name])
    row = cursor.fetchone()
    current_id = row[0] if row else 1
    
    # 更新计数器
    conn.execute("UPDATE id_counters SET next_id = next_id + 1 WHERE table_name = ?", [table_name])
    conn.commit()
    conn.close()
    
    return current_id


def init_db(db_path: str = None):
    """初始化数据库表结构"""
    if db_path is None:
        db_path = get_db_path()
    
    conn = duckdb.connect(db_path)
    
    # 创建截图记录表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS screenshots (
            id INTEGER PRIMARY KEY,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            desktop INTEGER NOT NULL,
            raw_path VARCHAR NOT NULL,
            small_path VARCHAR NOT NULL,
            model_path VARCHAR NOT NULL,
            conf_threshold FLOAT
        )
    """)
    
    # 创建检测框表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS detections (
            id INTEGER PRIMARY KEY,
            screenshot_id INTEGER REFERENCES screenshots(id),
            box_index INTEGER NOT NULL,
            class_name VARCHAR NOT NULL,
            confidence FLOAT NOT NULL,
            x1 INTEGER,
            y1 INTEGER,
            x2 INTEGER,
            y2 INTEGER,
            cropped_path VARCHAR NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 创建 OCR 结果表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ocr_results (
            id INTEGER PRIMARY KEY,
            detection_id INTEGER REFERENCES detections(id),
            text_block_index INTEGER,
            bbox VARCHAR,
            text TEXT,
            confidence FLOAT,
            full_text TEXT,
            ocr_time_ms FLOAT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 创建 ID 计数器表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS id_counters (
            table_name VARCHAR PRIMARY KEY,
            next_id INTEGER DEFAULT 1
        )
    """)
    
    # 初始化计数器
    for table in ['screenshots', 'detections', 'ocr_results']:
        conn.execute("""
            INSERT OR IGNORE INTO id_counters (table_name, next_id) VALUES (?, 1)
        """, [table])
    
    conn.commit()
    conn.close()
    return db_path


def save_screenshot(db_path: str, desktop: int, raw_path: str, small_path: str, 
                    model_path: str, conf_threshold: float) -> int:
    """保存截图记录，返回 screenshot_id"""
    conn = duckdb.connect(db_path)
    
    screenshot_id = get_next_id(db_path, 'screenshots')
    
    conn.execute("""
        INSERT INTO screenshots (id, desktop, raw_path, small_path, model_path, conf_threshold)
        VALUES (?, ?, ?, ?, ?, ?)
    """, [
        int(screenshot_id), 
        int(desktop), 
        str(raw_path), 
        str(small_path), 
        str(model_path), 
        float(conf_threshold)
    ])
    
    conn.commit()
    conn.close()
    
    return screenshot_id


def save_detection(db_path: str, screenshot_id: int, box_index: int, class_name: str,
                   confidence: float, x1: int, y1: int, x2: int, y2: int, 
                   cropped_path: str) -> int:
    """保存检测框记录，返回 detection_id"""
    conn = duckdb.connect(db_path)
    
    detection_id = get_next_id(db_path, 'detections')
    
    # 确保所有数值都是 Python 原生类型（不是 numpy 类型）
    conn.execute("""
        INSERT INTO detections (id, screenshot_id, box_index, class_name, confidence, 
                                x1, y1, x2, y2, cropped_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        int(detection_id), 
        int(screenshot_id), 
        int(box_index), 
        str(class_name), 
        float(confidence), 
        int(x1), 
        int(y1), 
        int(x2), 
        int(y2), 
        str(cropped_path)
    ])
    
    conn.commit()
    conn.close()
    
    return detection_id


def save_ocr_result(db_path: str, detection_id: int, text_blocks: list, 
                    full_text: str, ocr_time_ms: float):
    """保存 OCR 结果"""
    conn = duckdb.connect(db_path)
    
    for i, block in enumerate(text_blocks):
        bbox_json = json.dumps(block.get('bbox', []))
        ocr_id = get_next_id(db_path, 'ocr_results')
        
        conn.execute("""
            INSERT INTO ocr_results (id, detection_id, text_block_index, bbox, text, 
                                     confidence, full_text, ocr_time_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            int(ocr_id),
            int(detection_id), 
            int(i), 
            str(bbox_json), 
            str(block.get('text', '')), 
            float(block.get('confidence', 0.0)),
            str(full_text),
            float(ocr_time_ms)
        ])
    
    conn.commit()
    conn.close()


def get_latest_screenshot(db_path: str = None) -> dict:
    """获取最新的截图记录"""
    if db_path is None:
        db_path = get_db_path()
    
    conn = duckdb.connect(db_path)
    cursor = conn.execute("""
        SELECT id, desktop, raw_path, small_path, model_path, conf_threshold, timestamp
        FROM screenshots
        ORDER BY timestamp DESC
        LIMIT 1
    """)
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            'id': row[0],
            'desktop': row[1],
            'raw_path': row[2],
            'small_path': row[3],
            'model_path': row[4],
            'conf_threshold': row[5],
            'timestamp': row[6]
        }
    return None


def get_latest_detections(db_path: str = None) -> list:
    """获取最新截图的所有检测框"""
    if db_path is None:
        db_path = get_db_path()
    
    conn = duckdb.connect(db_path)
    
    # 先获取最新的 screenshot_id
    latest = get_latest_screenshot(db_path)
    if not latest:
        conn.close()
        return []
    
    cursor = conn.execute("""
        SELECT id, box_index, class_name, confidence, x1, y1, x2, y2, cropped_path
        FROM detections
        WHERE screenshot_id = ?
        ORDER BY box_index
    """, [latest['id']])
    
    results = []
    for row in cursor.fetchall():
        results.append({
            'id': row[0],
            'box_index': row[1],
            'class_name': row[2],
            'confidence': row[3],
            'x1': row[4],
            'y1': row[5],
            'x2': row[6],
            'y2': row[7],
            'cropped_path': row[8]
        })
    
    conn.close()
    return results


def get_ocr_results_for_detection(db_path: str, detection_id: int) -> dict:
    """获取指定检测框的 OCR 结果"""
    conn = duckdb.connect(db_path)
    
    cursor = conn.execute("""
        SELECT text_block_index, bbox, text, confidence, full_text, ocr_time_ms
        FROM ocr_results
        WHERE detection_id = ?
        ORDER BY text_block_index
    """, [detection_id])
    
    text_blocks = []
    full_text = None
    ocr_time_ms = None
    
    for row in cursor.fetchall():
        text_blocks.append({
            'index': row[0],
            'bbox': json.loads(row[1]) if row[1] else [],
            'text': row[2],
            'confidence': row[3]
        })
        if full_text is None:
            full_text = row[4]
        if ocr_time_ms is None:
            ocr_time_ms = row[5]
    
    conn.close()
    
    return {
        'text_blocks': text_blocks,
        'full_text': full_text,
        'ocr_time_ms': ocr_time_ms
    }


def query_recent_data(db_path: str = None, limit: int = 10) -> list:
    """查询最近的 OCR 结果（关联截图和检测信息）"""
    if db_path is None:
        db_path = get_db_path()
    
    conn = duckdb.connect(db_path)
    
    cursor = conn.execute("""
        SELECT 
            s.timestamp,
            s.desktop,
            d.class_name,
            d.confidence as det_confidence,
            d.cropped_path,
            o.text,
            o.confidence as ocr_confidence,
            o.full_text
        FROM screenshots s
        JOIN detections d ON s.id = d.screenshot_id
        JOIN ocr_results o ON d.id = o.detection_id
        ORDER BY s.timestamp DESC
        LIMIT ?
    """, [limit])
    
    results = []
    for row in cursor.fetchall():
        results.append({
            'timestamp': row[0],
            'desktop': row[1],
            'class_name': row[2],
            'det_confidence': row[3],
            'cropped_path': row[4],
            'text': row[5],
            'ocr_confidence': row[6],
            'full_text': row[7]
        })
    
    conn.close()
    return results


if __name__ == "__main__":
    # 测试
    db_path = init_db()
    print(f"数据库初始化完成：{db_path}")
    
    # 查询最近数据
    recent = query_recent_data(db_path, limit=5)
    print(f"\n最近 {len(recent)} 条记录:")
    for r in recent:
        print(f"  [{r['timestamp']}] Desktop {r['desktop']}: {r['full_text']}")
