import os
import json
from aligo import Aligo
import shutil
from datetime import datetime, timedelta

# === 配置信息 ===
# 阿里云盘父目录 ID
PARENT_FILE_ID = "6960d19d13a0749179314e8999ef0f51622667e2"

# 代理设置（保留原脚本设置）
os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:7890'
os.environ['HTTP_PROXY'] = 'http://127.0.0.1:7890'

def cleanup_yesterday(base_dir):
    """
    清理昨天的本地录像文件夹
    """
    yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    yesterday_path = os.path.join(base_dir, yesterday_str)
    
    if os.path.exists(yesterday_path):
        try:
            print(f"正在清理昨天 ({yesterday_str}) 的本地录像...")
            # 使用 shutil.rmtree 递归删除文件夹及其内容
            shutil.rmtree(yesterday_path)
            print(f"成功删除本地目录: {yesterday_path}")
        except Exception as e:
            print(f"删除昨天目录时出错: {e}")
    else:
        print(f"昨日目录不存在，无需清理: {yesterday_str}")
        
def scan_and_upload(target_dir):
    """使用 aligo.upload_folder 上传整个文件夹到阿里云盘"""
    print(f"开始上传目录: {target_dir}")
    if not os.path.exists(target_dir):
        print(f"错误: 目录 {target_dir} 不存在")
        return False

    try:
        # 初始化 Aligo
        aligo = Aligo()
        print("阿里云盘初始化成功")
        
        # 使用 upload_folder 直接上传整个文件夹
        # 它会自动处理子目录和文件
        res = aligo.upload_folder(target_dir, parent_file_id=PARENT_FILE_ID)
        
        if res:
            print(f"文件夹上传任务已提交/完成: {os.path.basename(target_dir)}")
            return True
        else:
            print(f"文件夹 {target_dir} 上传失败")
            return False
    except Exception as e:
        print(f"上传过程中出现异常: {e}")
        return False

import threading
from datetime import datetime

def start_async_upload(base_dir):
    """
    异步启动今天的录像上传任务
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    # today_str = "2026-02-28"
    upload_dir = os.path.join(base_dir, today_str)
    
    if not os.path.exists(upload_dir):
        print(f"今日录像目录不存在: {upload_dir}")
        return False, f"今日录像目录不存在: {today_str}"
    
    def run_upload():
        try:
            print(f"开始后台上传任务: {today_str}")
            success = scan_and_upload(upload_dir)
            print(f"后台上传任务已完成: {today_str}")
            # 2. 上传成功后执行清理
            if success:
                print(f"上传已确认，准备清理旧文件...")
                cleanup_yesterday(base_dir)
            else:
                print("上传未成功，跳过清理步骤以防数据丢失。")
        except Exception as e:
            print(f"后台上传任务出错: {e}")

    thread = threading.Thread(target=run_upload)
    thread.start()
    return True, today_str

if __name__ == '__main__':
    # 基础目录
    BASE_DIR = "/www/wwwroot/malanxi/index/lc/records"
    start_async_upload(BASE_DIR)
