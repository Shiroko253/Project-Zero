# Discord 機器人相關庫
import discord  # 核心庫，用於與 Discord API 進行交互
import discord.state  # 提供機器人狀態管理的內部工具
from discord.ext import commands  # 提供擴展功能，例如命令框架
from discord.ui import View, Button, Select  # 用於構建互動式界面，例如按鈕和選擇框

# 異步處理相關庫
import asyncio  # 用於異步編程，支持機器人的非阻塞操作
import aiohttp  # 用於進行異步 HTTP 請求，例如抓取 API 數據
import aiofiles  # 用於異步文件操作，適合讀取或寫入大文件

# 標準庫
import os  # 提供操作系統功能，例如環境變量管理
import sys  # 提供與 Python 解釋器相關的功能
import json  # 用於處理 JSON 格式數據的序列化與反序列化
import logging  # 用於記錄運行時的日誌和錯誤信息
import subprocess  # 用於執行系統命令或外部程序
import time  # 提供時間相關的函數，例如獲取當前時間
import random  # 用於生成隨機數或隨機選擇數據
import re  # 正則表達式庫，用於字符串模式匹配和替換
from datetime import datetime, timedelta, timezone  # 提供日期和時間操作功能

# 配置與環境管理相關庫
from dotenv import load_dotenv  # 用於加載 .env 文件中的環境變量
import yaml  # 用於處理 YAML 文件格式的讀取和寫入
from filelock import FileLock  # 用於文件加鎖，防止多個進程同時修改文件

# 其他工具
import psutil  # 用於檢查系統性能和資源使用情況，例如 CPU 和內存占用
from urllib.parse import urlencode  # 用於編碼 URL 查詢參數


# 加載變量環境，從 .env 文件中讀取環境變量，例如 DISCORD_TOKEN_MAIN_BOT 和 AUTHOR_ID
# 確保 .env 文件與此腳本位於同一目錄，並包含以下內容：
# DISCORD_TOKEN_MAIN_BOT=your_bot_token_here
# AUTHOR_ID=your_discord_id_here
load_dotenv()

# 硬編碼的 token 和 discord_user_id，TOKEN 是機器人的身份令牌，AUTHOR_ID 是作者的 Discord ID
TOKEN = os.getenv('DISCORD_TOKEN_MAIN_BOT')
AUTHOR_ID = int(os.getenv('AUTHOR_ID', 0))
LOG_FILE_PATH = "feedback_log.txt"  # 日誌文件的路徑

# 如果 token 或 AUTHOR_ID 缺失，則拋出異常，確保環境變量正確設置
# TOKEN 是機器人的身份令牌，沒有它無法啟動機器人。
# AUTHOR_ID 是機器人管理員的 Discord ID，用於特定權限操作。
if not TOKEN or not AUTHOR_ID:
    raise ValueError("缺少必要的環境變量 DISCORD_TOKEN_MAIN_BOT 或 AUTHOR_ID")

# 配置基礎的 log 記錄器，用於記錄機器人的運行狀態和錯誤
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(filename='main-error.log', encoding='utf-8', mode='w'),  # 將錯誤記錄保存到文件中
        logging.StreamHandler()  # 在控制台輸出錯誤
    ]
)

# 初始化 Discord 機器人的 intents 和 bot 實例
intents = discord.Intents.default()
intents.message_content = True  # 啟用接收消息內容的權限
intents.guilds = True  # 啟用與服務器相關的事件權限
intents.members = True  # 啟用成員相關的事件權限
bot = commands.Bot(command_prefix='!', intents=intents)  # 設置機器人命令前綴為 "!"

# 事件處理器：監聽消息事件
@bot.event
async def on_message(message):
    global last_activity_time  # 全局變量，用於記錄最後活動時間

    # 忽略機器人自己的消息，避免出現循環回應。
    if message.author == bot.user:
        return

    # 確保其他命令處理器能夠正確處理消息，例如處理 "/help" 等命令。
    await bot.process_commands(message)

# 嘗試設置機器人的狀態，例如閒置狀態和活動內容
# Discord 機器人狀態（status）是用戶看到機器人名稱旁邊的圖標，例如 "線上" 或 "閒置"。
# Discord 活動（activity）是機器人的自定義狀態文本，例如 "正在玩某遊戲"。
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")  # 在控制台輸出機器人的名稱和 ID
    print("------")  # 分割線，用於美化輸出

    print("斜線指令已自動同步。")  # 提示斜線命令已經自動同步

    try:
        # 嘗試設置機器人的狀態，例如閒置狀態和活動內容
        await bot.change_presence(
            status=discord.Status.idle,  # 設置機器人狀態為閑置
            activity=discord.Activity(type=discord.ActivityType.playing, name='Blue Archive')  # 設置活動狀態為正在玩遊戲
            # 其他可選活動：
            # activity=discord.Streaming(name='Live Stream', url='https://twitch.tv/username')  # 設置為直播狀態
            # activity=discord.Activity(type=discord.ActivityType.listening, name='Spotify')  # 設置為聆聽狀態
            # activity=discord.Activity(type=discord.ActivityType.watching, name='YouTube Video')  # 設置為觀看狀態
            # activity=discord.Activity(type=discord.ActivityType.competing, name='eSports Tournament')  # 設置為競賽狀態
        )
        print("已設置機器人的狀態。")  # 提示狀態設置成功
    except Exception as e:
        print(f"Failed to set presence: {e}")  # 如果設置失敗，輸出錯誤信息

    # 全局變量 last_activity_time 記錄了機器人最後一次活動的時間。
    # 這可以用於監控機器人是否處於空閒狀態，或根據活動狀態執行特定操作。
    global last_activity_time
    last_activity_time = time.time()

# 主函數部分：啟動機器人，處理啟動錯誤
try:
    bot.run(TOKEN, reconnect=True)  # 啟動機器人，啟用自動重連功能
except discord.LoginFailure:
    print("無效的機器人令牌。請檢查 TOKEN。")  # 如果登錄失敗，通常是令牌格式錯誤或未正確設置。
except Exception as e:
    print(f"機器人啟動時發生錯誤: {e}")  # 捕捉其他啟動錯誤，例如網絡問題或權限問題。
