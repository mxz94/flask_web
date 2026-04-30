import subprocess
import time
import os
import json
import threading
import logging
from datetime import datetime, timedelta

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("triggered_record.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# 配置文件路径 (复用 server_record.py 的配置)
CONFIG_FILE = "config.json"


class RecordingManager:
    def __init__(self):
        self.process = None
        self.stop_time = None
        self.lock = threading.Lock()
        self.monitor_thread = None
        self.config = self.load_config()

    def load_config(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logging.error(f"读取配置文件失败: {e}")
            return {}

    def get_output_path(self):
        base_dir = self.config.get("output_dir", "recordings")
        device_id = self.config.get("device_id", "unknown")
        
        # 以日期创建文件夹
        date_str = datetime.now().strftime("%Y-%m-%d")
        target_dir = os.path.join(base_dir, date_str)
        if not os.path.exists(target_dir):
            os.makedirs(target_dir)
        
        # 以时间为文件名
        filename = f"{datetime.now().strftime('%Y-%m-%d_%H-%M')}.mp4"
        return os.path.join(target_dir, filename)

    def start_recording_process(self, stream_url, output_path):
        command = [
            "ffmpeg",
            "-i", stream_url,
            "-c", "copy",
            "-y",
            output_path
        ]
        logging.info(f"启动录制: {' '.join(command)}")
        # 使用 subprocess.Popen 不阻塞
        return subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)

    def stop_recording_process(self):
        if self.process:
            logging.info("停止录制...")
            try:
                # 尝试优雅停止 (发送 q 给 ffmpeg 往往不管用，直接 terminate)
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
            except Exception as e:
                logging.error(f"停止录制异常: {e}")
            finally:
                self.process = None

    def monitor_loop(self):
        logging.info("监控线程启动")
        while True:
            with self.lock:
                if not self.process:
                    break
                
                # 检查进程是否意外退出
                if self.process.poll() is not None:
                    logging.warning("FFmpeg 进程意外退出")
                    self.process = None
                    break

                # 检查是否到达停止时间
                if datetime.now() > self.stop_time:
                    logging.info("到达停止时间，结束录制")
                    self.stop_recording_process()
                    break
            
            time.sleep(1)
        logging.info("监控线程结束")

    def trigger(self, duration_mins=2):
        """
        触发录制或延长录制时间
        """
        # 重新加载配置以防 URL 变更
        self.config = self.load_config()
        stream_url = self.config.get("stream_url")
        if not stream_url:
            logging.error("未配置 stream_url")
            return False

        with self.lock:
            new_stop_time = datetime.now() + timedelta(minutes=duration_mins)
            
            if self.process and self.process.poll() is None:
                # 正在录制，仅延长结束时间
                if new_stop_time > self.stop_time:
                    logging.info(f"正在录制中，延长录制时间至: {new_stop_time}")
                    self.stop_time = new_stop_time
                else:
                    logging.info("正在录制中，当前结束时间晚于新请求时间，忽略")
            else:
                # 未在录制，开始新录制
                logging.info(f"开始新录制，计划结束时间: {new_stop_time}")
                self.stop_time = new_stop_time
                output_path = self.get_output_path()
                self.process = self.start_recording_process(stream_url, output_path)
                
                # 启动监控线程
                self.monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
                self.monitor_thread.start()
        return True


