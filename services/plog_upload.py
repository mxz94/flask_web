import math
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

import boto3
import requests
import tinify
from botocore.config import Config
from PIL import Image
from PIL.ExifTags import GPSTAGS, TAGS


db_path = "/www/wwwroot/malanxi/typecho/usr/670e1e78df263.db"
pi = 3.1415926535897932384626
a = 6378245.0
ee = 0.00669342162296594323


def _transformlat(lng, lat):
    ret = -100.0 + 2.0 * lng + 3.0 * lat + 0.2 * lat * lat + 0.1 * lng * lat + 0.2 * math.sqrt(math.fabs(lng))
    ret += (20.0 * math.sin(6.0 * lng * pi) + 20.0 * math.sin(2.0 * lng * pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lat * pi) + 40.0 * math.sin(lat / 3.0 * pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(lat / 12.0 * pi) + 320 * math.sin(lat * pi / 30.0)) * 2.0 / 3.0
    return ret


def _transformlng(lng, lat):
    ret = 300.0 + lng + 2.0 * lat + 0.1 * lng * lng + 0.1 * lng * lat + 0.1 * math.sqrt(math.fabs(lng))
    ret += (20.0 * math.sin(6.0 * lng * pi) + 20.0 * math.sin(2.0 * lng * pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lng * pi) + 40.0 * math.sin(lng / 3.0 * pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(lng / 12.0 * pi) + 300.0 * math.sin(lng / 30.0 * pi)) * 2.0 / 3.0
    return ret


def out_of_china(lng, lat):
    return not (lng > 73.66 and lng < 135.05 and lat > 3.86 and lat < 53.55)


def wgs84_to_gcj02(lng, lat):
    if out_of_china(lng, lat):
        return [lng, lat]
    dlat = _transformlat(lng - 105.0, lat - 35.0)
    dlng = _transformlng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * pi
    magic = math.sin(radlat)
    magic = 1 - ee * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrtmagic) * pi)
    dlng = (dlng * 180.0) / (a / sqrtmagic * math.cos(radlat) * pi)
    return [lng + dlng, lat + dlat]


def convert_to_degrees(value):
    d, m, s = value
    return d + (m / 60.0) + (s / 3600.0)


def get_gps_from_image_url(image_url):
    try:
        response = requests.get(image_url)
        response.raise_for_status()
    except requests.RequestException:
        return {"status": "error", "message": "无法下载图片"}

    temp_file_path = "./demo.jpg"
    with open(temp_file_path, "wb") as temp_file:
        temp_file.write(response.content)

    image = Image.open(temp_file_path)
    exif_data = image._getexif()
    if not exif_data:
        return {"status": "error", "message": "没有找到 GPS 信息"}

    gps_info = {}
    date_time = None
    for tag, value in exif_data.items():
        decoded = TAGS.get(tag, tag)
        if decoded == "GPSInfo":
            for t in value:
                sub_decoded = GPSTAGS.get(t, t)
                gps_info[sub_decoded] = value[t]
        if decoded == "DateTimeOriginal":
            date_time = value

    if "GPSLatitude" in gps_info and "GPSLongitude" in gps_info:
        lat = convert_to_degrees(gps_info["GPSLatitude"])
        if gps_info.get("GPSLatitudeRef") != "N":
            lat = -lat

        lon = convert_to_degrees(gps_info["GPSLongitude"])
        if gps_info.get("GPSLongitudeRef") != "E":
            lon = -lon

        return {"status": "success", "latitude": lat, "longitude": lon, "dateTime": date_time}

    return {"status": "error", "message": "没有找到 GPS 信息"}


def get_address_from_coordinates(longitude, latitude):
    url = f"https://restapi.amap.com/v3/geocode/regeo?output=json&location={longitude},{latitude}&key=310f991c4a6755a70f5abaf0307493d3&extensions=base"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        if data["status"] == "1":
            formatted_address = data["regeocode"]["formatted_address"]
            return {"status": "success", "formatted_address": formatted_address}
        return {"status": "error", "message": "未找到地址信息"}
    except requests.RequestException:
        return {"status": "error", "message": "请求失败"}


def extract_city_and_district(address):
    province_pos = address.find("省")
    if province_pos != -1:
        return address[province_pos + 1:]
    return address


def compress_image(image):
    tinify.key = "FrPpqqhhsrj2zWmbqyTH6z7xl7MMfC1K"
    source = tinify.from_file(image)
    copyrighted = source.preserve("copyright", "creation", "location")
    copyrighted.to_file(image)


def post_to_plog(title, str_value, mid="1"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT cid FROM typecho_fields WHERE str_value = ?", (str_value,))
    existing = cursor.fetchone()

    if existing:
        conn.close()
        return {"status": "error", "message": "The str_value already exists in the database.", "cid": existing[0]}

    timestamp = int(datetime.now().timestamp())
    gps_result = get_gps_from_image_url(str_value)
    if gps_result["status"] == "success":
        data = wgs84_to_gcj02(gps_result["longitude"], gps_result["latitude"])
        address_result = get_address_from_coordinates(data[0], data[1])
        if address_result["status"] == "success":
            if title:
                title += "|"
            title += extract_city_and_district(address_result["formatted_address"]) + "|" + gps_result["dateTime"]
            timestamp = int(datetime.strptime(gps_result["dateTime"], "%Y:%m:%d %H:%M:%S").timestamp())

    cursor.execute("SELECT MAX(cid) as max_cid FROM typecho_contents")
    max_cid = cursor.fetchone()[0] or 0
    new_cid = max_cid + 1
    cursor.execute(
        "INSERT INTO typecho_contents (cid, title, slug, created, modified, text, authorId, type, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (new_cid, title, new_cid, timestamp, timestamp, str(gps_result), 1, "post", "publish"),
    )

    cursor.execute(
        "INSERT INTO typecho_fields (cid, name, type, str_value) VALUES (?, ?, ?, ?)",
        (new_cid, "img", "str", str_value),
    )

    conn.commit()
    conn.close()

    return {"status": "success", "message": "Data inserted successfully.", "cid": new_cid}


def resize_and_adjust_quality(input_file, scale=0.3, quality=50):
    if os.path.isfile(input_file) and input_file.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif")):
        with Image.open(input_file) as img:
            original_width, original_height = img.size
            new_width = int(original_width * scale)
            new_height = int(original_height * scale)
            resized_img = img.resize((new_width, new_height), Image.LANCZOS)
            resized_img.save(input_file, quality=quality)


def copy_file_to_directory(source_file, target_directory):
    if not os.path.exists(target_directory):
        os.makedirs(target_directory)

    target_file = os.path.join(target_directory, os.path.basename(source_file))
    shutil.copy2(source_file, target_file)
    print(f"Copied {source_file} to {target_file}")


def upload_image(file: str, prefix=None):
    access_key = "ad692e01f74450943b4122a84164835e"
    secret_key = "fcba81ff9094e0204be641cb4e80e78660f43278aecf65e4433aa9a7ac6becf8"
    url = "https://52666f83ef7dec7e1f33bc0afc91c693.r2.cloudflarestorage.com"
    filename = Path(file).name

    config = Config(signature_version="s3v4")
    s3_client = boto3.client(
        "s3",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        endpoint_url=url,
        config=config,
    )

    bucket_name = "mxz"
    bucket_file_name = f"plog/{filename}"
    if prefix:
        bucket_file_name = f"plog/{prefix}/{filename}"
        s3_client.upload_file(file, bucket_name, bucket_file_name)
        copy_file_to_directory(file, f"/www/wwwroot/malanxi/index/plog/{prefix}")
    else:
        s3_client.upload_file(file, bucket_name, bucket_file_name)
        copy_file_to_directory(file, "/www/wwwroot/malanxi/index/plog")
        resize_and_adjust_quality(file)
        upload_image(file, "thumbnail")

    return "https://malanxi.top/" + bucket_file_name
