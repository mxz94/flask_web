#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
照片管理工具 - 查询和更新SQLite数据库
功能：查询指定条件的照片，根据ID更新country、city、location_name
调用map_utils.py进行地理编码
"""

import sqlite3

import requests

# 数据库配置
DB_PATH = '/www/server/panel/data/compose/chronoframe/data/app.sqlite3'

def get_address_from_coordinates(longitude, latitude):
    url = f"https://restapi.amap.com/v3/geocode/regeo?output=json&location={longitude},{latitude}&key=310f991c4a6755a70f5abaf0307493d3&extensions=base"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        if data['status'] == "1":
            return {"status": "success", "data": data}
        else:
            return {"status": "error", "message": "未找到地址信息"}
    except requests.RequestException:
        return {"status": "error", "message": "请求失败"}

# 连接数据库
def connect_database():
    """连接数据库"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row  # 使结果可以按列名访问
        return conn
    except sqlite3.Error as e:
        print(f"数据库连接失败: {e}")
        return None

# 查询照片数据
def query_photos():
    """查询照片数据"""
    conn = connect_database()
    if not conn:
        return {"success": False, "error": "数据库连接失败"}

    try:
        cursor = conn.cursor()
        sql = "SELECT * FROM photos WHERE country IS NULL AND latitude IS NOT NULL"
        cursor.execute(sql)
        photos = [dict(row) for row in cursor.fetchall()]

        return {
            "success": True,
            "count": len(photos),
            "data": photos
        }
    except sqlite3.Error as e:
        return {"success": False, "error": f"查询失败: {e}"}
    finally:
        conn.close()

# 更新照片信息
def update_photo(photo_id, **kwargs):
    """更新照片信息"""
    conn = connect_database()
    if not conn:
        return {"success": False, "error": "数据库连接失败"}

    try:
        cursor = conn.cursor()

        # 检查记录是否存在
        cursor.execute("SELECT id FROM photos WHERE id = ?", (photo_id,))
        if not cursor.fetchone():
            return {"success": False, "error": "记录不存在"}

        # 构建动态更新SQL
        update_fields = []
        update_values = []

        if 'country' in kwargs and kwargs['country']:
            update_fields.append("country = ?")
            update_values.append(kwargs['country'].strip())

        if 'city' in kwargs and kwargs['city']:
            update_fields.append("city = ?")
            update_values.append(kwargs['city'].strip())

        if 'location_name' in kwargs and kwargs['location_name']:
            update_fields.append("location_name = ?")
            update_values.append(kwargs['location_name'].strip())

        if not update_fields:
            return {"success": False, "error": "没有提供要更新的字段"}

        # 添加ID到更新值
        update_values.append(photo_id)

        # 构建SQL
        update_sql = f"UPDATE photos SET {', '.join(update_fields)} WHERE id = ?"
        cursor.execute(update_sql, update_values)
        conn.commit()

        # 获取更新后的记录
        cursor.execute("SELECT id, country, city, location_name FROM photos WHERE id = ?", (photo_id,))
        updated_record = dict(cursor.fetchone())

        return {
            "success": True,
            "message": "更新成功",
            "updated_fields": update_fields,
            "data": updated_record
        }

    except sqlite3.Error as e:
        return {"success": False, "error": f"更新失败: {e}"}
    finally:
        conn.close()

# 自动地理编码
def auto_geocode_photos():
    """自动为没有地理信息的照片进行地理编码"""
    conn = connect_database()
    if not conn:
        return {"success": False, "error": "数据库连接失败"}

    try:
        cursor = conn.cursor()

        # 查询有经纬度但没有地址信息的照片
        sql = """
        SELECT id, latitude, longitude, country, city, location_name 
        FROM photos 
        WHERE latitude IS NOT NULL 
        AND longitude IS NOT NULL 
        AND (country IS NULL OR city IS NULL OR location_name IS NULL)
        """
        cursor.execute(sql)
        photos = [dict(row) for row in cursor.fetchall()]

        updated_count = 0
        results = []

        for photo in photos:
            try:
                # 调用map_utils获取地址信息
                result = get_address_from_coordinates(photo['longitude'], photo['latitude'])
                if result['status'] == 'success':
                    address = result['data']['regeocode']["addressComponent"]
                    formattedAddress = result['data']['regeocode']["formatted_address"]
                    # 解析地址信息
                    country = address["country"] or address["province"] or "中国"  # 默认中国
                    city =  address["city"] or address["province"]
                    location_name = address["township"]
                    # 更新数据库
                    strd = formattedAddress.split(city)
                    if len(strd) > 1:
                        location_name = strd[1]
                    update_data = {}
                    if not photo['country']:
                        update_data['country'] = country
                    if not photo['city']:
                        update_data['city'] = city
                    if not photo['location_name']:
                        update_data['location_name'] = location_name

                    if update_data:
                        update_result = update_photo(photo['id'], **update_data)
                        if update_result['success']:
                            updated_count += 1
                            results.append({
                                "id": photo['id'],
                                "address": address,
                                "updated": update_data
                            })

            except Exception as e:
                print(f"处理照片 {photo['id']} 时出错: {e}")
                continue

        return {
            "success": True,
            "message": f"自动地理编码完成，更新了 {updated_count} 条记录",
            "updated_count": updated_count,
            "results": results
        }

    except sqlite3.Error as e:
        return {"success": False, "error": f"自动地理编码失败: {e}"}
    finally:
        conn.close()


# 主程序
def gallery_main():
    """主函数 - 查询、地理编码、更新"""
    print("🧪 照片管理工具")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # 1. 查询需要处理照片
    print("🔍 查询需要处理照片...")
    result = query_photos()

    if not result['success']:
        print(f"❌ 查询失败: {result['error']}")
        return

    photos = result['data']
    print(f"找到 {len(photos)} 条需要处理的记录")

    if not photos:
        print("✅ 没有需要处理的照片")
        return

    # 显示照片信息
    print("\n📋 照片列表:")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    for i, photo in enumerate(photos, 1):
        print(f"{i}. ID: {photo['id']}, 纬度: {photo['latitude']}, 经度: {photo['longitude']}")

    # 2. 自动地理编码
    print("\n🌍 开始自动地理编码...")
    geocode_result = auto_geocode_photos()

    if geocode_result['success']:
        print(f"✅ {geocode_result['message']}")

        if geocode_result['results']:
            print("\n📋 更新详情:")
            for item in geocode_result['results']:
                print(f"  ID {item['id']}: {item['address']}")
                print(f"    更新: {item['updated']}")
    else:
        print(f"❌ 地理编码失败: {geocode_result['error']}")

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("🎉 处理完成！")

