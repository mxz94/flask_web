import subprocess
import time
import os
import json
import requests
from datetime import datetime, timedelta

# 配置文件路径
CONFIG_FILE = "config.json"

# 缓存当天的日期类型，避免频繁请求 API
day_cache = {
    "date": None,
    "is_holiday_api": False
}

def load_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"读取配置文件失败: {e}")
        return None

def check_is_holiday_api():
    """
    调用 jiejiariapi.com 判断今天是否为法定节假日
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # 如果缓存中有今天的记录，直接返回
    if day_cache["date"] == today_str:
        return day_cache["is_holiday_api"]
    
    print(f"正在通过 API 查询今日 ({today_str}) 是否为法定节假日...")
    try:
        # 接口地址: https://api.jiejiariapi.com/v1/is_holiday
        url = "https://api.jiejiariapi.com/v1/is_holiday"
        params = {"date": today_str}
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        # 根据接口文档，返回包含 is_holiday (boolean)
        is_holiday = data.get("is_holiday", False)
        
        # 更新缓存
        day_cache["date"] = today_str
        day_cache["is_holiday_api"] = is_holiday
        
        if is_holiday:
            print(f"API 查询结果：今天是法定节假日 ({data.get('holiday', '未知')})")
        else:
            print("API 查询结果：今天不是法定节假日")
            
        return is_holiday
    except Exception as e:
        day_cache["date"] = today_str
        day_cache["is_holiday_api"] = False
        print(f"查询节假日 API 出错: {e}，将默认视为普通工作日")
        return False

def send_dingtalk_notification(webhook, message):
    if not webhook:
        return
    
    payload = {
        "msgtype": "text",
        "text": {
            "content": f"【录制告警】\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n内容: {message}"
        }
    }
    try:
        headers = {'Content-Type': 'application/json'}
        response = requests.post(webhook, data=json.dumps(payload), headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"发送钉钉通知失败: {response.text}")
    except Exception as e:
        print(f"发送钉钉通知出错: {e}")

def is_in_period(periods_config):
    """
    判断逻辑：
    1. 如果是周六或周日 -> 按照节假日 (holiday) 处理
    2. 如果是周一至周五 -> 调用 API 判断是否为法定节假日
       - 是法定节假日 -> 按照节假日 (holiday) 处理
       - 不是法定节假日 -> 按照工作日 (workday) 处理
    """
    weekday = datetime.now().weekday() # 0-4 为周一到周五，5-6 为周六周日
    
    is_weekend = (weekday >= 5)
    
    if is_weekend:
        # 周末直接按节假日算
        current_periods = periods_config.get("holiday", [])
        day_label = "周末"
    else:
        # 周一至周五，额外调用接口判断
        is_statutory_holiday = check_is_holiday_api()
        if is_statutory_holiday:
            current_periods = periods_config.get("holiday", [])
            day_label = "法定节假日"
        else:
            current_periods = periods_config.get("workday", [])
            day_label = "普通工作日"
    
    now_str = datetime.now().strftime("%H:%M")
    for period in current_periods:
        if period['start'] <= now_str <= period['end']:
            return True, day_label
            
    return False, day_label

def get_output_path(base_dir, device_id):
    # 以日期创建文件夹
    date_str = datetime.now().strftime("%Y-%m-%d")
    target_dir = os.path.join(base_dir, date_str)
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)
    
    # 以时间为文件名 (包含年月日时分秒)
    filename = f"{datetime.now().strftime('%Y-%m-%d_%H-%M')}.mp4"
    return os.path.join(target_dir, filename)

def record_segment(url, duration_secs, output_path, webhook):
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始录制段落...")
    print(f"保存至: {output_path}")
    
    command = [
        "ffmpeg",
        "-i", url,
        "-t", str(duration_secs),
        "-c", "copy",
        "-y",
        output_path
    ]
    
    try:
        # 使用 universal_newlines 兼容旧版本 Python
        process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        
        if process.returncode == 0:
            # 检查文件大小，如果太小（如小于 1MB），说明录制可能失败或被中断
            if os.path.exists(output_path):
                file_size = os.path.getsize(output_path)
                if file_size < 1024 * 1024:  # 1MB 阈值
                    print(f"警告：录制文件太小 ({file_size / 1024:.2f} KB)，可能由于并发限制导致录制失败，正在删除...")
                    os.remove(output_path)
                    error_msg = f"录制文件过小 ({file_size / 1024:.2f} KB)，疑似并发超限或流中断，已自动清理。"
                    send_dingtalk_notification(webhook, error_msg)
                    return False
            
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 录制成功。")
            return True
        else:
            error_msg = f"ffmpeg 退出码 {process.returncode}\n错误详情: {process.stderr[-200:]}"
            print(f"录制失败: {error_msg}")
            send_dingtalk_notification(webhook, error_msg)
            return False
    except Exception as e:
        error_msg = f"执行 ffmpeg 异常: {str(e)}"
        print(error_msg)
        send_dingtalk_notification(webhook, error_msg)
        return False

def calculate_duration_to_boundary(duration_mins):
    """
    计算距离下一个整点（根据 duration_mins 对齐）还剩多少秒
    例如：duration_mins=30, 当前 17:02, 则返回到 17:30 的秒数
    """
    now = datetime.now()
    seconds_since_midnight = now.hour * 3600 + now.minute * 60 + now.second
    duration_secs_total = duration_mins * 60
    
    next_boundary_seconds = ((seconds_since_midnight // duration_secs_total) + 1) * duration_secs_total
    remaining_secs = next_boundary_seconds - seconds_since_midnight
    
    # 如果距离边界太近（小于 10 秒），则合并到下一个周期，避免产生极短文件
    if remaining_secs < 10:
        remaining_secs += duration_secs_total
        
    return remaining_secs

def main():
    print("=== 乐橙服务器高级录制程序已启动 (对齐整点录制) ===")
    
    while True:
        config = load_config()
        if not config:
            time.sleep(60)
            continue
            
        stream_url = config.get("stream_url")
        device_id = config.get("device_id", "unknown")
        periods_config = config.get("periods", {})
        webhook = config.get("dingtalk_webhook")
        duration_mins = config.get("record_duration_mins", 30)
        if duration_mins < 1:
            duration_mins = 1
            
        base_dir = config.get("output_dir", "recordings")
        
        # 检查是否在录制时段内
        in_period, day_label = is_in_period(periods_config)
        
        if in_period:
            output_path = get_output_path(base_dir, device_id)
            
            # 计算动态时长，以对齐整点边界
            duration_secs = calculate_duration_to_boundary(duration_mins)
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 目标对齐时长: {duration_secs} 秒")
            
            # 执行录制
            success = record_segment(stream_url, duration_secs, output_path, webhook)
            
            if not success:
                print("本轮录制出错，将等待 10 秒后进入下一轮检查...")
                time.sleep(10)
        else:
            # 不在录制时段，每分钟检查一次
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 今日为{day_label}，当前不在录制时段内，等待中...", end="\r")
            time.sleep(60)

if __name__ == "__main__":
    main()
