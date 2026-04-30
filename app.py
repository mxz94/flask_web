import math
from pathlib import Path
import tinify
from flask import Flask, request, jsonify, render_template, send_from_directory,send_file
from flask_cors import CORS
from PIL import Image
import sqlite3
from PIL.ExifTags import TAGS, GPSTAGS
from pillow_heif import register_heif_opener
import os
import requests
import io
import json
from botocore.config import Config
import boto3
import shutil
import gpxpy
import tempfile
import time
from geopy.distance import geodesic
from datetime import datetime
from fit_tool.fit_file_builder import FitFileBuilder
from fit_tool.profile.messages.event_message import EventMessage
from fit_tool.profile.messages.lap_message import LapMessage
from fit_tool.profile.messages.session_message import SessionMessage
from fit_tool.profile.messages.activity_message import ActivityMessage
from fit_tool.profile.messages.device_info_message import DeviceInfoMessage
from fit_tool.profile.messages.file_id_message import FileIdMessage
from fit_tool.profile.messages.record_message import RecordMessage
from fit_tool.profile.profile_type import (
    FileType,
    TimerTrigger,
    Event,
    EventType,
    Sport,
    SubSport,
    SessionTrigger,
    Activity,
    ActivityType,
    LapTrigger,
)

import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("triggered_record.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

from gallery_utils import gallery_main

register_heif_opener()

app = Flask(__name__, static_url_path='', static_folder='./templates')
CORS(app, resources={r"/*": {"origins": "*"}})

db_path = '/www/wwwroot/malanxi/typecho/usr/670e1e78df263.db'
# x_pi = 3.14159265358979324 * 3000.0 / 180.0
pi = 3.1415926535897932384626  # π
a = 6378245.0  # 长半轴
ee = 0.00669342162296594323  # 偏心率平方

def ding(message):
    
    payload = {
        "msgtype": "text",
        "text": {
            "content": f"{message}"
        }
    }
    try:
        headers = {'Content-Type': 'application/json'}
        response = requests.post('https://oapi.dingtalk.com/robot/send?access_token=5575d8a5ffffdbc9ad5cd470e733911aece1d8c740a12031d1e96625d210e3ce', data=json.dumps(payload), headers=headers, timeout=10,
            proxies={"http": None, "https": None})
        if response.status_code != 200:
            print(f"发送钉钉通知失败: {response.text}")
    except Exception as e:
        print(f"发送钉钉通知出错: {e}")

def _transformlat(lng, lat):
    ret = -100.0 + 2.0 * lng + 3.0 * lat + 0.2 * lat * lat + \
          0.1 * lng * lat + 0.2 * math.sqrt(math.fabs(lng))
    ret += (20.0 * math.sin(6.0 * lng * pi) + 20.0 *
            math.sin(2.0 * lng * pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lat * pi) + 40.0 *
            math.sin(lat / 3.0 * pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(lat / 12.0 * pi) + 320 *
            math.sin(lat * pi / 30.0)) * 2.0 / 3.0
    return ret
def out_of_china(lng, lat):
    """
    判断是否在国内，不在国内不做偏移
    :param lng:
    :param lat:
    :return:
    """
    return not (lng > 73.66 and lng < 135.05 and lat > 3.86 and lat < 53.55)

def _transformlng(lng, lat):
    ret = 300.0 + lng + 2.0 * lat + 0.1 * lng * lng + \
          0.1 * lng * lat + 0.1 * math.sqrt(math.fabs(lng))
    ret += (20.0 * math.sin(6.0 * lng * pi) + 20.0 *
            math.sin(2.0 * lng * pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lng * pi) + 40.0 *
            math.sin(lng / 3.0 * pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(lng / 12.0 * pi) + 300.0 *
            math.sin(lng / 30.0 * pi)) * 2.0 / 3.0
    return ret

def wgs84_to_gcj02(lng, lat):
    """
    WGS84转GCJ02(火星坐标系)
    :param lng:WGS84坐标系的经度
    :param lat:WGS84坐标系的纬度
    :return:
    """
    if out_of_china(lng, lat):  # 判断是否在国内
        return [lng, lat]
    dlat = _transformlat(lng - 105.0, lat - 35.0)
    dlng = _transformlng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * pi
    magic = math.sin(radlat)
    magic = 1 - ee * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrtmagic) * pi)
    dlng = (dlng * 180.0) / (a / sqrtmagic * math.cos(radlat) * pi)
    mglat = lat + dlat
    mglng = lng + dlng
    return [mglng, mglat]

def get_gps_from_image_url(image_url):
    try:
        response = requests.get(image_url)
        response.raise_for_status()
    except requests.RequestException:
        return {"status": "error", "message": "无法下载图片"}
    temp_file = "./demo.jpg"
    with open(temp_file, 'wb') as temp_file:
        temp_file.write(response.content)
        temp_file_path = temp_file.name

        # try:
        image = Image.open(temp_file_path)
        exif_data = image._getexif()
        if not exif_data:
            return {"status": "error", "message": "没有找到 GPS 信息"}

        gps_info = {}
        for tag, value in exif_data.items():
            decoded = TAGS.get(tag, tag)
            if decoded == "GPSInfo":
                for t in value:
                    sub_decoded = GPSTAGS.get(t, t)
                    gps_info[sub_decoded] = value[t]
            if decoded == "DateTimeOriginal":
                date_time = value

        if 'GPSLatitude' in gps_info and 'GPSLongitude' in gps_info:
            lat = convert_to_degrees(gps_info['GPSLatitude'])
            if gps_info.get('GPSLatitudeRef') != 'N':
                lat = -lat

            lon = convert_to_degrees(gps_info['GPSLongitude'])
            if gps_info.get('GPSLongitudeRef') != 'E':
                lon = -lon

            return {"status": "success", "latitude": lat, "longitude": lon, "dateTime": date_time}
        else:
            return {"status": "error", "message": "没有找到 GPS 信息"}
    # finally:
    # os.remove(temp_file_path)

def convert_to_degrees(value):
    d, m, s = value
    return d + (m / 60.0) + (s / 3600.0)

def get_address_from_coordinates(longitude, latitude):
    url = f"https://restapi.amap.com/v3/geocode/regeo?output=json&location={longitude},{latitude}&key=310f991c4a6755a70f5abaf0307493d3&extensions=base"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        if data['status'] == "1":
            formatted_address = data['regeocode']['formatted_address']
            return {"status": "success", "formatted_address": formatted_address}
        else:
            return {"status": "error", "message": "未找到地址信息"}
    except requests.RequestException:
        return {"status": "error", "message": "请求失败"}

def extract_city_and_district(address):
    province_pos = address.find('省')
    if province_pos != -1:
        return address[province_pos + 1:]
    return address

def compress_image(image):
    tinify.key = "FrPpqqhhsrj2zWmbqyTH6z7xl7MMfC1K"

    source = tinify.from_file(image)
    copyrighted = source.preserve("copyright", "creation", "location")
    copyrighted.to_file(image)



# 设备常量 - 使用更标准的Garmin设备信息
MANUFACTURER = 1  # Garmin
GARMIN_PRODUCT = 3415  # Forerunner 245 - 更常见的Garmin设备
GARMIN_SOFTWARE_VERSION = 3.58  # 软件版本
GARMIN_SERIAL_NUMBER = 1234567890

def gpx_to_fit(gpx_data):
    """增强版GPX转FIT转换函数 - 更好的Garmin兼容性"""
    builder = FitFileBuilder(auto_define=True, min_string_size=50)

    # 使用GPX文件的实际时间，如果没有则使用当前时间
    if gpx_data.time:
        time_create = int(gpx_data.time.timestamp() * 1000)
    else:
        time_create = int(datetime.now().timestamp() * 1000)

    # 文件ID - 确保时间戳正确
    file_id = FileIdMessage()
    file_id.local_id = 0
    file_id.type = FileType.ACTIVITY
    file_id.manufacturer = MANUFACTURER
    file_id.product = GARMIN_PRODUCT
    file_id.time_created = time_create
    file_id.serial_number = GARMIN_SERIAL_NUMBER
    builder.add(file_id)

    # 设备信息 - 使用标准Garmin设备参数
    device = DeviceInfoMessage()
    device.local_id = 1
    device.serial_number = GARMIN_SERIAL_NUMBER
    device.manufacturer = MANUFACTURER
    device.garmin_product = GARMIN_PRODUCT
    device.software_version = GARMIN_SOFTWARE_VERSION
    device.device_index = 0
    device.source_type = 5
    device.product = GARMIN_PRODUCT
    builder.add(device)

    # 初始化变量
    distance = 0.0
    records = []
    prev_coord = None
    prev_time = None
    moving_time = 0
    total_distance = 0.0
    start_time = None
    end_time = None
    max_speed = 0.0
    min_altitude = float('inf')
    max_altitude = float('-inf')
    total_ascent = 0.0
    total_descent = 0.0
    prev_altitude = None

    # 处理所有轨迹点
    for track in gpx_data.tracks:
        for segment in track.segments:
            for i, pt in enumerate(segment.points):
                if pt.time is None:
                    continue
                    
                current_coord = (pt.latitude, pt.longitude)
                current_time = pt.time
                current_speed = 0.0
                current_altitude = pt.elevation if pt.elevation is not None else 0

                # 设置开始时间
                if start_time is None:
                    start_time = current_time
                    # 开始事件
                    start_event = EventMessage()
                    start_event.local_id = 2
                    start_event.event = Event.TIMER
                    start_event.event_type = EventType.START
                    start_event.event_group = 0
                    start_event.timer_trigger = TimerTrigger.MANUAL
                    start_event.timestamp = int(current_time.timestamp() * 1000)
                    builder.add(start_event)

                # 计算瞬时速度
                if prev_coord and prev_time:
                    delta = geodesic(prev_coord, current_coord).meters
                    dt = (current_time - prev_time).total_seconds()
                    if 0 < dt < 60:  # 有效时间间隔
                        moving_time += dt
                        distance += delta
                        total_distance = distance
                        current_speed = delta / dt  # m/s
                        # 限制速度在合理范围内 (0-65.535 m/s)
                        current_speed = max(0.0, min(current_speed, 65.535))
                        max_speed = max(max_speed, current_speed)
                    else:
                        current_speed = 0.0
                else:
                    current_speed = 0.0

                # 计算海拔变化
                if prev_altitude is not None:
                    altitude_diff = current_altitude - prev_altitude
                    if altitude_diff > 0:
                        total_ascent += altitude_diff
                    else:
                        total_descent += abs(altitude_diff)

                # 更新海拔统计
                if current_altitude > 0:
                    min_altitude = min(min_altitude, current_altitude)
                    max_altitude = max(max_altitude, current_altitude)

                # 创建记录点
                record = RecordMessage()
                record.local_id = 3
                record.position_lat = pt.latitude
                record.position_long = pt.longitude
                record.distance = distance
                record.altitude = current_altitude
                record.speed = current_speed
                record.enhanced_speed = current_speed
                record.timestamp = int(current_time.timestamp() * 1000)
                records.append(record)

                prev_coord = current_coord
                prev_time = current_time
                prev_altitude = current_altitude
                end_time = current_time

    # 添加所有记录点
    builder.add_all(records)

    # 计算统计数据
    avg_speed = (total_distance / moving_time) if moving_time > 0 else 0.0
    avg_speed = max(0.0, min(avg_speed, 65.535))
    max_speed = max(0.0, min(max_speed, 65.535))

    # Lap信息
    if start_time and end_time and records:
        lap = LapMessage()
        lap.local_id = 4
        lap.timestamp = int(end_time.timestamp() * 1000)
        lap.message_index = 0
        lap.start_time = int(start_time.timestamp() * 1000)
        lap.total_elapsed_time = moving_time
        lap.total_timer_time = moving_time
        lap.start_position_lat = records[0].position_lat
        lap.start_position_long = records[0].position_long
        lap.end_position_lat = records[-1].position_lat
        lap.end_position_long = records[-1].position_long
        lap.total_distance = total_distance
        lap.sport = Sport.CYCLING
        lap.sub_sport = SubSport.GENERIC
        lap.avg_speed = avg_speed
        lap.enhanced_avg_speed = avg_speed
        lap.max_speed = max_speed
        lap.enhanced_max_speed = max_speed
        lap.total_ascent = total_ascent
        lap.total_descent = total_descent
        lap.min_altitude = min_altitude if min_altitude != float('inf') else 0
        lap.max_altitude = max_altitude if max_altitude != float('-inf') else 0
        lap.trigger = LapTrigger.MANUAL
        builder.add(lap)

        # Session信息
        session = SessionMessage()
        session.local_id = 5
        session.timestamp = int(end_time.timestamp() * 1000)
        session.start_time = int(start_time.timestamp() * 1000)
        session.total_elapsed_time = moving_time
        session.total_timer_time = moving_time
        session.start_position_lat = records[0].position_lat
        session.start_position_long = records[0].position_long
        session.sport = Sport.CYCLING
        session.sub_sport = SubSport.GENERIC
        session.first_lap_index = 0
        session.num_laps = 1
        session.trigger = SessionTrigger.ACTIVITY_END
        session.event = Event.SESSION
        session.event_type = EventType.STOP
        session.total_distance = total_distance
        session.avg_speed = avg_speed
        session.enhanced_avg_speed = avg_speed
        session.max_speed = max_speed
        session.enhanced_max_speed = max_speed
        session.total_ascent = total_ascent
        session.total_descent = total_descent
        session.min_altitude = min_altitude if min_altitude != float('inf') else 0
        session.max_altitude = max_altitude if max_altitude != float('-inf') else 0
        builder.add(session)

        # 结束事件
        stop_event = EventMessage()
        stop_event.local_id = 2
        stop_event.event = Event.TIMER
        stop_event.event_type = EventType.STOP
        stop_event.event_group = 0
        stop_event.timer_trigger = TimerTrigger.MANUAL
        stop_event.timestamp = int(end_time.timestamp() * 1000)
        builder.add(stop_event)

        # Activity消息
        activity = ActivityMessage()
        activity.local_id = 6
        activity.timestamp = int(end_time.timestamp() * 1000)
        activity.total_timer_time = moving_time
        activity.num_sessions = 1
        activity.type = Activity.MANUAL
        activity.event = Event.ACTIVITY
        activity.event_type = EventType.STOP
        activity.event_group = 0
        builder.add(activity)

    return builder.build()

@app.route('/convert', methods=['POST'])
def convert_gpx_to_fit():
    temp_fit_path = None
    try:
        if 'gpxFile' not in request.files:
            return '没有文件', 400

        gpx_file = request.files['gpxFile']
        if gpx_file.filename == '':
            return '没有选择文件', 400

        # 解析GPX文件
        gpx = gpxpy.parse(gpx_file)

        # 创建临时文件
        temp_fit_path = tempfile.mktemp(suffix='.fit')

        # 转换为FIT并保存到临时文件
        fit_file = gpx_to_fit(gpx)
        fit_file.to_file(temp_fit_path)

        # 读取临时文件并发送
        with open(temp_fit_path, 'rb') as f:
            fit_data = f.read()

        # 删除临时文件
        if os.path.exists(temp_fit_path):
            os.remove(temp_fit_path)

        return send_file(
            io.BytesIO(fit_data),
            as_attachment=True,
            download_name=gpx_file.filename.replace('.gpx', '.fit'),
            mimetype='application/octet-stream'
        )

    except Exception as e:
        print(f"转换错误: {str(e)}")
        if temp_fit_path and os.path.exists(temp_fit_path):
            os.remove(temp_fit_path)
        return {'error': str(e)}, 500

@app.route('/')
def home():
    return render_template('index.html')


@app.route('/gallery')
def gallery():
    gallery_main()
    return {'msg': 'success'}, 200

@app.route('/<path:path>')
def serve_static(path):
    try:
        return send_from_directory('./templates', path)
    except Exception as e:
        print(f"静态文件访问错误: {str(e)}")
        return str(e), 404

@app.route('/upload', methods=['POST'])
def convert_heic_to_jpg_and_upload():
    title = request.form.get('title', '')
    pwd = request.form.get('pwd', '')
    files = request.files.getlist('files')
    upload_results = []
    if pwd != 'qq67607301':
        return jsonify({"message": "pwd is error"})

    for file in files:
        file.save(file.filename)
        if file.filename.lower().endswith('.heic'):
            img = Image.open(file)
            exif = img.info.get('exif')
            icc_profile = img.info.get('icc_profile')
            output_file = os.path.splitext(file.filename)[0] + '.jpg'
            img.save(output_file, exif=exif, icc_profile=icc_profile)


            compress_image(output_file)
            upload_url = upload_image(output_file, None)
            os.remove(output_file)
        else:

            compress_image(file.filename)
            upload_url = upload_image(file.filename, None)
        os.remove(file.filename)

        data = post_to_plog(title, upload_url, "1")
        print(data)
        upload_results.append({"filename": file.filename, "upload_url": upload_url, "data": json.dumps(data, ensure_ascii=False, indent=4)})

    return jsonify({"message": "All files processed", "results": str(upload_results)})


def post_to_plog(title, str_value, mid="1"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT cid FROM typecho_fields WHERE str_value = ?", (str_value,))
    existing = cursor.fetchone()

    if existing:
        return {"status": "error", "message": "The str_value already exists in the database.", "cid": existing[0]}
    timestamp = int(datetime.now().timestamp())
    gps_result = get_gps_from_image_url(str_value)
    if gps_result['status'] == 'success':
        data = wgs84_to_gcj02(gps_result['longitude'], gps_result['latitude'])
        address_result = get_address_from_coordinates(data[0], data[1])
        if address_result['status'] == 'success':
            if title:
                title += "|"
            title += extract_city_and_district(address_result['formatted_address']) + "|" + gps_result["dateTime"]
            timestamp = int(datetime.strptime(gps_result["dateTime"], "%Y:%m:%d %H:%M:%S").timestamp())

    cursor.execute("SELECT MAX(cid) as max_cid FROM typecho_contents")
    max_cid = cursor.fetchone()[0] or 0
    new_cid = max_cid + 1
    cursor.execute("INSERT INTO typecho_contents (cid, title, slug, created, modified, text, authorId, type, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (new_cid, title, new_cid, timestamp, timestamp, str(gps_result), 1, 'post', 'publish'))

    cursor.execute("INSERT INTO typecho_fields (cid, name, type, str_value) VALUES (?, ?, ?, ?)",
                   (new_cid, 'img', 'str', str_value))

    conn.commit()
    conn.close()

    return {"status": "success", "message": "Data inserted successfully.", "cid": new_cid}

def resize_and_adjust_quality(input_file, scale=0.3, quality=50):
    # 检查文件是否为图像
    if os.path.isfile(input_file) and input_file.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif')):
        with Image.open(input_file) as img:
            # 获取原始尺寸
            original_width, original_height = img.size

            # 计算新的尺寸（等比例缩放）
            new_width = int(original_width * scale)
            new_height = int(original_height * scale)

            # 缩放图像
            resized_img = img.resize((new_width, new_height), Image.LANCZOS)

            # 保存图像，设置质量
            resized_img.save(input_file, quality=quality)

def copy_file_to_directory(source_file, target_directory):
    # 确保目标目录存在
    if not os.path.exists(target_directory):
        os.makedirs(target_directory)

    # 构建目标文件路径
    target_file = os.path.join(target_directory, os.path.basename(source_file))

    # 复制文件并覆盖
    shutil.copy2(source_file, target_file)
    print(f"Copied {source_file} to {target_file}")

def upload_image(file:str, prefix= None):

    # 访问密钥 ID
    access_key = 'ad692e01f74450943b4122a84164835e'
    # 机密访问密钥
    secret_key = "fcba81ff9094e0204be641cb4e80e78660f43278aecf65e4433aa9a7ac6becf8"
    # 存储桶的 URL
    url = 'https://52666f83ef7dec7e1f33bc0afc91c693.r2.cloudflarestorage.com'
    filename = Path(file).name

    # 创建一个 S3 客户端，这里指定了 R2 的端点
    config = Config(signature_version='s3v4')
    s3_client = boto3.client(
        's3',
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        endpoint_url=url,
        config=config
    )
    # 你要上传到存储桶的名字
    bucket_name = 'mxz'
    # 本地文件 文件名
    bucket_file_name = f'plog/{filename}'
    if prefix:
        bucket_file_name = f'plog/{prefix}/{filename}'
        # 使用 S3 客户端上传文件
        s3_client.upload_file(file, bucket_name, bucket_file_name)
        copy_file_to_directory(file, f"/www/wwwroot/malanxi/index/plog/{prefix}")

    else:
        s3_client.upload_file(file, bucket_name, bucket_file_name)
        copy_file_to_directory(file, "/www/wwwroot/malanxi/index/plog")
        resize_and_adjust_quality(file)
        upload_image(file, "thumbnail")


    # return "https://pub-4232cd0528364004a537285f400807bf.r2.dev/" + bucket_file_name
    return "https://malanxi.top/" + bucket_file_name

from lechange_api import LechangeClient
# Replace with your actual appId and appSecret
APP_ID = "lc023b439a8a7c4b0b"
APP_SECRET = "2575c4063864488ca49d114fa7cbc2"

client = LechangeClient(APP_ID, APP_SECRET)

# In-memory cache for accessToken
cache = {
    "access_token": None,
    "expires_at": 0
}

def get_cached_access_token():
    now = int(time.time())
    # If token is missing or expiring in less than 5 minutes, refresh it
    if not cache["access_token"] or cache["expires_at"] - now < 300:
        print("Refreshing access token...")
        token_info = client.get_access_token()
        if token_info and token_info.get("result", {}).get("code") == "0":
            data = token_info["result"]["data"]
            cache["access_token"] = data["accessToken"]
            # accessToken is usually valid for 24 hours (86400s), but let's use the returned expire value if available
            # If not available, default to 24 hours
            expires_in = data.get("expire", 86400)
            cache["expires_at"] = now + expires_in
        else:
            return None
    return cache["access_token"]

@app.route('/kitToken', methods=['GET'])
def get_kit_token():
    device_id = request.args.get('deviceId')
    channel_id = request.args.get('channelId', '0')
    kit_type = request.args.get('type', '0')

    if not device_id:
        return jsonify({"code": "1", "msg": "deviceId is required"}), 400

    access_token = get_cached_access_token()
    if not access_token:
        return jsonify({"code": "1", "msg": "Failed to get access token"}), 500

    kit_info = client.get_kit_token(access_token, device_id, channel_id, kit_type)
    if kit_info and kit_info.get("result", {}).get("code") == "0":
        return jsonify(kit_info["result"]["data"])
    else:
        return jsonify(kit_info), 500
      
RECORDINGS_DIR = "/www/wwwroot/malanxi/index/lc/records"

@app.route('/recordings/dates', methods=['GET'])
def list_recording_dates():
    """获取所有有录像的日期目录"""
    if not os.path.exists(RECORDINGS_DIR):
        return jsonify([])
    
    # 获取所有子目录并排序（倒序，最新的日期在前）
    dates = [d for d in os.listdir(RECORDINGS_DIR) if os.path.isdir(os.path.join(RECORDINGS_DIR, d))]
    dates.sort(reverse=True)
    return jsonify(dates)

@app.route('/recordings/files/<date_str>', methods=['GET'])
def list_recording_files(date_str):
    """获取指定日期的所有录像文件"""
    date_path = os.path.join(RECORDINGS_DIR, date_str)
    if not os.path.exists(date_path):
        return jsonify([])
    
    # 获取所有 .mp4 文件并排序
    files = [f for f in os.listdir(date_path) if f.endswith('.mp4')]
    files.sort(reverse=True)
    
    # 返回文件信息，包括 URL
    result = []
    for f in files:
        result.append({
            "name": f,
            "url": f"/api/recordings/{date_str}/{f}",
            "size": os.path.getsize(os.path.join(date_path, f))
        })
    return jsonify(result)

@app.route('/recordings/<path:filename>')
def serve_recording(filename):
    """直接提供视频文件下载/播放"""
    return send_from_directory(RECORDINGS_DIR, filename)


from upload import start_async_upload

# --- 录像管理 API ---

@app.route('/upload/today', methods=['POST', 'GET'])
def trigger_upload_today():
    """手动触发上传今天的录像到阿里云盘 (异步)"""
    success, result = start_async_upload(RECORDINGS_DIR)
    
    if not success:
        return jsonify({"code": 1, "msg": result}), 404
    
    return jsonify({
        "code": 0, 
        "msg": "上传任务已在后台启动，请稍后在云盘查看kan", 
        "date": result
    })
    
from triggered_record import RecordingManager
    
recorder = RecordingManager()

@app.route('/lcnotice', methods=['POST', 'GET'])
def lcnotice():
    # ding("检测到移动")
    logging.info(f"收到回调消息")
    duration = recorder.config.get("trigger_duration_mins", 2)
    ding("检测到移动" + str(duration))
    recorder.trigger(duration_mins=duration)
    return jsonify({
        "code": 0, 
        "msg": "kan", 
        "date": {}
    })
    
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)