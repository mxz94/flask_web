import subprocess
import time
import os
import json
import threading
import logging
from datetime import datetime, timedelta

# 配置日志
logger = logging.getLogger("triggered_record")
logger.setLevel(logging.INFO)
if not logger.handlers:
    file_handler = logging.FileHandler("triggered_record.log", encoding='utf-8')
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)

def log_info(msg): logger.info(msg)
def log_error(msg): logger.error(msg)
def log_warning(msg): logger.warning(msg)

CONFIG_FILE = "config.json"

class RecordingManager:
    def __init__(self):
        self.process = None
        self.stop_time = None
        self.lock = threading.Lock()
        self.monitor_thread = None
        self.config = self.load_config()
        self.current_ts_path = None
        self.final_mp4_path = None
        self.is_running = False # 显式控制录制状态

    def load_config(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            log_error(f"读取配置文件失败: {e}")
            return {}

    def get_output_path(self):
        base_dir = self.config.get("output_dir", "recordings")
        date_str = datetime.now().strftime("%Y-%m-%d")
        target_dir = os.path.join(base_dir, date_str)
        if not os.path.exists(target_dir):
            os.makedirs(target_dir)
        filename = f"{datetime.now().strftime('%Y-%m-%d_%H-%M')}.mp4"
        return os.path.join(target_dir, filename)

    def start_recording_process(self, stream_url, ts_path):
        """启动或重启 FFmpeg 进程"""
        # 核心改进：添加强力重连参数和时间戳修复
        command = [
            "ffmpeg",
            "-reconnect", "1",
            "-reconnect_at_eof", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "5",
            "-fflags", "+genpts", # 重新生成时间戳，解决时长显示不准
            "-i", stream_url,
            "-c", "copy",
            "-y",
            "-f", "mpegts", # 显式指定格式以便追加
            ts_path
        ]
        log_info(f"执行命令: {' '.join(command)}")
        # 注意：这里使用 stderr=subprocess.DEVNULL 避免管道堵塞导致进程卡死
        return subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def stop_recording_process(self):
        log_info("正在彻底停止录制...")
        self.is_running = False # 先置位，防止监控线程重启进程
        if self.process:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except:
                    self.process.kill()
            self.process = None
        
        # 延迟一下确保文件句柄释放再转换
        time.sleep(1)
        self.convert_ts_to_mp4()

    def convert_ts_to_mp4(self):
        if self.current_ts_path and os.path.exists(self.current_ts_path):
            try:
                if os.path.getsize(self.current_ts_path) < 10*1024: # 小于10KB认为是无效录制
                    log_warning("录制文件过小，删除")
                    os.remove(self.current_ts_path)
                    return

                log_info(f"转封装中 -> {self.final_mp4_path}")
                command = [
                    "ffmpeg", "-i", self.current_ts_path,
                    "-c", "copy", "-movflags", "faststart", "-y",
                    self.final_mp4_path
                ]
                result = subprocess.run(command, capture_output=True)
                if result.returncode == 0:
                    log_info("转换成功，删除临时文件")
                    os.remove(self.current_ts_path)
                else:
                    log_error(f"转换失败: {result.stderr.decode()}")
            except Exception as e:
                log_error(f"转换异常: {e}")
            finally:
                self.current_ts_path = None
                self.final_mp4_path = None

    def monitor_loop(self):
        log_info("监控线程启动")
        stream_url = self.config.get("stream_url")
        
        while self.is_running:
            with self.lock:
                # 检查是否到期
                if datetime.now() >= self.stop_time:
                    log_info("录制时长已满，准备结束")
                    break
                
                # 核心改进：检查进程，如果意外退出则重启续录
                if self.process is None or self.process.poll() is not None:
                    log_warning("检测到 FFmpeg 异常退出，尝试续录...")
                    self.process = self.start_recording_process(stream_url, self.current_ts_path)
            
            time.sleep(2) # 检查频率不宜过快
        
        self.stop_recording_process()
        log_info("监控线程正常结束")

    def trigger(self, duration_mins=5): # 默认改为5分钟
        self.config = self.load_config()
        stream_url = self.config.get("stream_url")
        if not stream_url:
            log_error("未配置 stream_url")
            return False

        with self.lock:
            now = datetime.now()
            new_stop_time = datetime.now() + timedelta(minutes=duration_mins)
            # 计算新的结束时间
            if self.is_running and self.stop_time > now:
                self.stop_time = new_stop_time
                log_info(f"延长录制，新结束时间: {self.stop_time.strftime('%H:%M:%S')}")
            else:
                self.stop_time = new_stop_time
                self.is_running = True
                output_path = self.get_output_path()
                self.final_mp4_path = output_path
                self.current_ts_path = output_path.replace(".mp4", ".ts")
                
                log_info(f"开启新录制，预计结束时间: {self.stop_time.strftime('%H:%M:%S')}")
                self.process = self.start_recording_process(stream_url, self.current_ts_path)
                
                self.monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
                self.monitor_thread.start()
        return True