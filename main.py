import discord
import subprocess
import time
import asyncio
import discord.state
import json
import random
import os
import sys
import logging
import aiohttp
import aiofiles
import re
import yaml
import psutil
import requests
import sqlite3
import openai # -v 0.28
import math
from discord.ext import commands
from discord.ui import View, Button, Select
from discord import ui
from discord import Embed, ApplicationContext, Interaction, ButtonStyle
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from urllib.parse import urlencode
from filelock import FileLock
from responses import food_responses, death_responses, life_death_responses, self_responses, friend_responses, maid_responses, mistress_responses, reimu_responses, get_random_response
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from functools import wraps

file_lock = asyncio.Lock()
load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN_MAIN_BOT')
AUTHOR_ID = int(os.getenv('AUTHOR_ID', 0))
LOG_FILE_PATH = "feedback_log.txt"
WORK_COOLDOWN_SECONDS = 60
API_URL = 'https://api.chatanywhere.org/v1/'

api_keys = [
    {"key": os.getenv('CHATANYWHERE_API'), "limit": 200, "remaining": 200},
    {"key": os.getenv('CHATANYWHERE_API2'), "limit": 200, "remaining": 200}
]
current_api_index = 0

if not TOKEN or not AUTHOR_ID:
    raise ValueError("缺少必要的環境變量 DISCORD_TOKEN_MAIN_BOT 或 AUTHOR_ID")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(filename='main-error.log', encoding='utf-8', mode='w'),
        logging.StreamHandler()
    ]
)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

start_time = time.time()

def load_yaml(file_name, default=None):
    if default is None:
        default = {}
    """通用 YAML 文件加載函數"""
    try:
        with open(file_name, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or default
    except FileNotFoundError:
        print(f"{file_name} 文件未找到。")
        return default
    except yaml.YAMLError as e:
        print(f"{file_name} 加載錯誤: {e}")
        return default

def save_yaml(file_name, data):
    """通用 YAML 文件保存函數"""
    with open(file_name, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, allow_unicode=True)

def load_json(file_name, default=None):
    if default is None:
        default = {}
    """通用 JSON 文件加載函數"""
    try:
        with open(file_name, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"{file_name} 加載錯誤: {e}")
        return default

def save_json(file_name, data):
    """通用 JSON 文件保存函數"""
    with open(file_name, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

config = load_json("config.json")
raw_jobs = config.get("jobs", [])
jobs_data = {job: details for item in raw_jobs for job, details in item.items()}
fish_data = config.get("fish", {})
shop_data = config.get("shop_item", {})
user_data = load_yaml("config_user.yml")
quiz_data = load_yaml('quiz.yml')
dm_messages = load_json('dm_messages.json')
user_balance = load_json('balance.json')
invalid_bet_count = load_json('invalid_bet_count.json')

if not jobs_data:
    print("警告: 職業數據 (jobs) 為空！請檢查 config.json 文件。")
if not fish_data:
    print("警告: 魚類數據 (fish) 為空！請檢查 config.json 文件。")
if not shop_data:
    print("警告: 商店數據 (shop_item) 為空！請檢查 config.json 文件。")

cooldowns = {}
active_giveaways = {}

BALANCE_FILE = "balance.json"

def track_balance_json(command_func):
    """裝飾器：監測所有涉及 balance.json 的讀取與寫入"""
    @wraps(command_func)
    async def wrapper(interaction: discord.Interaction, *args, **kwargs):
        try:
            logging.info(f"執行指令: {command_func.__name__} 來自 {interaction.user} ({interaction.user.id})")
            
            before_data = await read_balance_file()
            logging.info(f"讀取 balance.json (指令前): {before_data}")

            result = await command_func(interaction, *args, **kwargs)

            after_data = await read_balance_file()
            logging.info(f"讀取 balance.json (指令後): {after_data}")

            if before_data and not after_data:
                logging.error(f"❌ balance.json 可能被 {command_func.__name__} 清空！")

            return result
        except Exception as e:
            logging.error(f"執行 {command_func.__name__} 時發生錯誤: {e}", exc_info=True)
            raise e
    return wrapper

async def read_balance_file():
    """異步讀取 balance.json"""
    try:
        async with aiofiles.open(BALANCE_FILE, 'r', encoding='utf-8') as file:
            content = await file.read()
            return json.loads(content) if content else {}
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logging.error(f"讀取 balance.json 失敗: {e}")
        return {}

async def write_balance_file(data):
    """異步寫入 balance.json"""
    try:
        async with aiofiles.open(BALANCE_FILE, 'w', encoding='utf-8') as file:
            await file.write(json.dumps(data, indent=4, ensure_ascii=False))
        logging.info("✅ balance.json 更新成功")
    except Exception as e:
        logging.error(f"寫入 balance.json 失敗: {e}")

disconnect_count = 0
last_disconnect_time = None
MAX_DISCONNECTS = 3
MAX_DOWN_TIME = 20
MAX_RETRIES = 5
RETRY_DELAY = 10
CHECK_INTERVAL = 3
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')

def load_status():
    """從冥界卷軸中讀取幽幽子的斷線記憶"""
    try:
        with open("bot_status.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"disconnect_count": 0, "reconnect_count": 0, "last_event_time": None}

def save_status(disconnects=None, reconnects=None):
    """將幽幽子的斷線記錄刻入冥界卷軸"""
    data = load_status()
    if disconnects is not None:
        data["disconnect_count"] += disconnects
    if reconnects is not None:
        data["reconnect_count"] += reconnects
    data["last_event_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open("bot_status.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

async def check_long_disconnect():
    """監控幽幽子是否長時間迷失於冥界之外"""
    global last_disconnect_time

    while True:
        if last_disconnect_time:
            elapsed = (datetime.now() - last_disconnect_time).total_seconds()
            if elapsed > MAX_DOWN_TIME:
                await send_alert_async(f"⚠️ 【警告】幽幽子已迷失於現世之外超過 {MAX_DOWN_TIME} 秒，冥界之風是否斷絕？")
                last_disconnect_time = None
        await asyncio.sleep(CHECK_INTERVAL)

async def send_alert_async(message):
    """以幽幽子的靈魂之音發送警報至現世"""
    if not DISCORD_WEBHOOK_URL:
        print("❌ 【錯誤】幽幽子找不到通往現世的櫻花路，警報無法傳達～")
        return

    embed = {
        "title": "🚨 【冥界警報】幽幽子的低語 🚨",
        "description": f"📢 {message}",
        "color": 0xFFA500,
        "timestamp": datetime.now().isoformat(),
        "footer": {"text": "⚠️ 來自冥界的警示～"}
    }

    data = {"embeds": [embed]}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(DISCORD_WEBHOOK_URL, json=data, timeout=5) as response:
                    if 200 <= response.status < 300:
                        print("✅ 【訊息】幽幽子的警報已順利傳至現世～")
                        return
                    else:
                        print(f"⚠️ 【警告】Webhook 發送失敗（狀態碼: {response.status}），回應: {await response.text()}")

        except asyncio.TimeoutError:
            print(f"⚠️ 【重試 {attempt}/{MAX_RETRIES}】發送警報超時，{RETRY_DELAY} 秒後重試～")
        except aiohttp.ClientConnectionError:
            print(f"⚠️ 【重試 {attempt}/{MAX_RETRIES}】冥界與現世之間的橋梁中斷，{RETRY_DELAY} 秒後重試～")
        except Exception as e:
            print(f"❌ 【錯誤】幽幽子的警報迷失，無法發送警報：{e}")
            break

        await asyncio.sleep(RETRY_DELAY)

    print("❌ 【錯誤】幽幽子多次呼喚無果，請檢查冥界之門是否關閉～")

@bot.event
async def on_disconnect():
    """當幽幽子與現世失去聯繫時"""
    global disconnect_count, last_disconnect_time

    disconnect_count += 1
    last_disconnect_time = datetime.now()

    save_status(disconnects=1)

    print(f"⚠️ 【警告】幽幽子於 {last_disconnect_time.strftime('%Y-%m-%d %H:%M:%S')} 迷失於現世之外。（第 {disconnect_count} 次）")

    if disconnect_count >= MAX_DISCONNECTS:
        asyncio.create_task(send_alert_async(f"⚠️ 【警告】幽幽子短時間內已迷失 {disconnect_count} 次，冥界之風是否消散？"))

@bot.event
async def on_resumed():
    """當幽幽子重新飄回現世時"""
    global disconnect_count, last_disconnect_time

    save_status(reconnects=1)

    print(f"🌸 【訊息】幽幽子於 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 重返現世，冥界之風再次吹起～")

    disconnect_count = 0
    last_disconnect_time = None

def init_db():
    conn = sqlite3.connect("example.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS UserMessages 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  user_id TEXT, 
                  message TEXT, 
                  repeat_count INTEGER DEFAULT 0, 
                  is_permanent BOOLEAN DEFAULT FALSE,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS BackgroundInfo 
                 (user_id TEXT PRIMARY KEY, 
                  info TEXT)''')
    conn.commit()
    conn.close()

def record_message(user_id, message):
    if not user_id or not message or not isinstance(message, str):
        return
    
    try:
        with sqlite3.connect("example.db") as conn:
            c = conn.cursor()
            c.execute("""
                SELECT id, repeat_count, is_permanent FROM UserMessages 
                WHERE user_id = ? AND message = ? AND is_permanent = FALSE
            """, (user_id, message))
            row = c.fetchone()

            if row:
                new_count = row[1] + 1
                if new_count >= 10:
                    c.execute("""
                        UPDATE UserMessages SET repeat_count = ?, is_permanent = TRUE 
                        WHERE id = ?
                    """, (new_count, row[0]))
                else:
                    c.execute("""
                        UPDATE UserMessages SET repeat_count = ? WHERE id = ?
                    """, (new_count, row[0]))
            else:
                c.execute("""
                    INSERT INTO UserMessages (user_id, message, created_at) 
                    VALUES (?, ?, ?)
                """, (user_id, message, datetime.now()))
            conn.commit()
    except sqlite3.Error as e:
        print(f"Database error: {e}")

def clean_old_messages(minutes=30):
    try:
        with sqlite3.connect("example.db") as conn:
            c = conn.cursor()
            time_ago = datetime.now(timezone.utc) - timedelta(minutes=minutes)
            c.execute("""
                DELETE FROM UserMessages 
                WHERE created_at < ? AND is_permanent = FALSE
            """, (time_ago,))
            deleted_rows = c.rowcount
            conn.commit()
            print(f"已刪除 {deleted_rows} 條舊訊息")
            return deleted_rows
    except sqlite3.Error as e:
        print(f"資料庫錯誤: {e}")
        return 0

def summarize_context(context):
    return context[:1500]

def generate_response(prompt, user_id):
    global current_api_index
    global api_keys

    tried_all_apis = False
    original_index = current_api_index

    while True:
        try:
            if api_keys[current_api_index]["remaining"] <= 0:
                print(f"API {current_api_index} 已用盡")
                current_api_index = (current_api_index + 1) % len(api_keys)
                if current_api_index == original_index:
                    tried_all_apis = True
                if tried_all_apis:
                    return "幽幽子今天吃太飽，先午睡一下吧～"

            openai.api_base = API_URL
            openai.api_key = api_keys[current_api_index]["key"]

            conn = sqlite3.connect("example.db")
            c = conn.cursor()
            c.execute("""
                SELECT message FROM UserMessages 
                WHERE user_id = ? OR user_id = 'system'
            """, (user_id,))
            context = "\n".join([f"{user_id}說 {row[0]}" for row in c.fetchall()])
            conn.close()

            user_background_info = get_user_background_info("西行寺 幽幽子")
            if not user_background_info:
                updated_background_info = (
                    "我是西行寺幽幽子，白玉樓的主人，幽靈公主。"
                    "生前因擁有『操縱死亡的能力』，最終選擇自盡，被埋葬於西行妖之下，化為幽靈。"
                    "現在，我悠閒地管理著冥界，欣賞四季變換，品味美食，偶爾捉弄妖夢。"
                    "雖然我的話語總是輕飄飄的，但生與死的流轉，皆在我的掌握之中。"
                    "啊，還有，請不要吝嗇帶點好吃的來呢～"
                )
                conn = sqlite3.connect("example.db")
                c = conn.cursor()
                c.execute("""
                    INSERT INTO BackgroundInfo (user_id, info) VALUES (?, ?)
                """, ("西行寺 幽幽子", updated_background_info))
                conn.commit()
                conn.close()
            else:
                updated_background_info = user_background_info

            if len(context.split()) > 3000:
                context = summarize_context(context)

            messages = [
                {"role": "system", "content": f"你現在是西行寺幽幽子，冥界的幽靈公主，背景資訊：{updated_background_info}"},
                {"role": "user", "content": f"{user_id}說 {prompt}"},
                {"role": "assistant", "content": f"已知背景資訊：\n{context}"}
            ]

            response = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=messages
            )

            api_keys[current_api_index]["remaining"] -= 1
            return response['choices'][0]['message']['content'].strip()

        except Exception as e:
            print(f"API {current_api_index} 發生錯誤: {str(e)}")
            current_api_index = (current_api_index + 1) % len(api_keys)
            if current_api_index == original_index:
                return "幽幽子現在有點懶洋洋的呢～等會兒再來吧♪"

def get_user_background_info(user_id):
    conn = sqlite3.connect("example.db")
    c = conn.cursor()
    c.execute("""
        SELECT info FROM BackgroundInfo WHERE user_id = ?
    """, (user_id,))
    rows = c.fetchall()
    conn.close()
    return "\n".join([row[0] for row in rows]) if rows else None

WEBHOOK_URL = os.getenv("WEBHOOK_URL")

async def send_global_webhook_message(content, color=discord.Color.from_rgb(219, 112, 147)):
    """🌸 讓幽幽子的靈魂之音輕飄至現世～"""
    if not WEBHOOK_URL:
        print("❌ 幽幽子找不到通往現世的路，通知無法傳達～")
        return

    embed = discord.Embed(
        title="🌸 幽幽子的飄渺呢喃",
        description=content,
        color=color,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text="來自冥界的微風與魂魄之語～", icon_url="https://i.imgur.com/oBPXxpv.png")

    try:
        async with aiohttp.ClientSession() as session:
            webhook = discord.Webhook.from_url(WEBHOOK_URL, session=session)
            await webhook.send(embed=embed)
            print("✅ 幽幽子的呢喃已飄至現世～")
    except Exception as e:
        print(f"❌ 幽幽子的聲音受阻：{e}")

@bot.event
async def on_message(message):
    global last_activity_time
    
    if message.author == bot.user:
        return
    
    if message.webhook_id:
        return
    
    content = message.content
    
    is_reply_to_bot = message.reference and message.reference.message_id
    is_mentioning_bot = bot.user.mention in message.content

    if is_reply_to_bot:
        try:
            referenced_message = await message.channel.fetch_message(message.reference.message_id)
            if referenced_message.author == bot.user:
                is_reply_to_bot = True
            else:
                is_reply_to_bot = False
        except discord.NotFound:
            is_reply_to_bot = False

    if is_reply_to_bot or is_mentioning_bot:
        user_message = message.content
        user_id = str(message.author.id)

        record_message(user_id, user_message)
        clean_old_messages()

        response = generate_response(user_message, user_id)
        await message.channel.send(response)
    
    if '關於機器人幽幽子' in message.content.lower():
        await message.channel.send('幽幽子的創建時間是<t:1623245700:D>')
    
    if '關於製作者' in message.content.lower():
        await message.channel.send('製作者是個很好的人 雖然看上有有點怪怪的')
    
    if '幽幽子的生日' in message.content.lower():
        await message.channel.send('機器人幽幽子的生日在<t:1623245700:D>')

    if '幽幽子待機多久了' in message.content.lower():
        current_time = time.time()
        idle_seconds = current_time - last_activity_time
        idle_minutes = idle_seconds / 60
        idle_hours = idle_seconds / 3600
        idle_days = idle_seconds / 86400

        if idle_days >= 1:
            await message.channel.send(f'幽幽子目前已待機了 **{idle_days:.2f} 天**')
        elif idle_hours >= 1:
            await message.channel.send(f'幽幽子目前已待機了 **{idle_hours:.2f} 小时**')
        else:
            await message.channel.send(f'幽幽子目前已待機了 **{idle_minutes:.2f} 分钟**')

    if isinstance(message.channel, discord.DMChannel):
        user_id = str(message.author.id)
        
        dm_messages = load_json('dm_messages.json', {})
        
        if user_id not in dm_messages:
            dm_messages[user_id] = []
        
        dm_messages[user_id].append({
            'content': message.content,
            'timestamp': message.created_at.isoformat()
        })
        
        save_json('dm_messages.json', dm_messages)
        
        print(f"Message from {message.author}: {message.content}")
    
    if 'これが最後の一撃だ！名に恥じぬ、ザ・ワールド、時よ止まれ！' in message.content.lower():
        await message.channel.send('ザ・ワールド\nhttps://tenor.com/view/the-world-gif-18508433')

        await asyncio.sleep(1)
        await message.channel.send('一秒経過だ！')

        await asyncio.sleep(3)
        await message.channel.send('二秒経過だ、三秒経過だ！')

        await asyncio.sleep(4)
        await message.channel.send('四秒経過だ！')

        await asyncio.sleep(5)
        await message.channel.send('五秒経過だ！')

        await asyncio.sleep(6)
        await message.channel.send('六秒経過だ！')

        await asyncio.sleep(7)
        await message.channel.send('七秒経過した！')

        await asyncio.sleep(8)
        await message.channel.send('ジョジョよ、**私のローラー**!\nhttps://tenor.com/view/dio-roada-rolla-da-dio-brando-dio-dio-jojo-dio-part3-gif-16062047')
    
        await asyncio.sleep(9)
        await message.channel.send('遅い！逃げられないぞ！\nhttps://tenor.com/view/dio-jojo-gif-13742432')
    
    if '星爆氣流斬' in message.content.lower():
        await message.channel.send('アスナ！クライン！')
        await message.channel.send('**頼む、十秒だけ持ち堪えてくれ！**')
        
        await asyncio.sleep(2)
        await message.channel.send('スイッチ！')
    
        await asyncio.sleep(10)
        await message.channel.send('# スターバースト　ストリーム！')
        
        await asyncio.sleep(5)
        await message.channel.send('**速く…もっと速く！！**')
        
        await asyncio.sleep(15)
        await message.channel.send('終わった…のか？')        
        
    if '關於食物' in content:
        await message.channel.send(get_random_response(food_responses))

    elif '對於死亡' in content:
        await message.channel.send(get_random_response(death_responses))

    elif '對於生死' in content:
        await message.channel.send(get_random_response(life_death_responses))
    
    elif '關於幽幽子' in content:
        await message.channel.send(get_random_response(self_responses))
    
    elif '幽幽子的朋友' in content:
        await message.channel.send(get_random_response(friend_responses))
    
    elif '關於紅魔館的女僕' in content:
        await message.channel.send(get_random_response(maid_responses))
    
    elif '關於紅魔舘的大小姐和二小姐' in content:
        await message.channel.send(get_random_response(mistress_responses))
    
    elif '關於神社的巫女' in content:
        await message.channel.send(get_random_response(reimu_responses))
  
    if '吃蛋糕嗎' in message.content:
        await message.channel.send(f'蛋糕？！ 在哪在哪？')
        await asyncio.sleep(3)
        await message.channel.send(f'妖夢 蛋糕在哪裏？')
        await asyncio.sleep(3)
        await message.channel.send(f'原來是個夢呀')
    
    if '吃三色糰子嗎' in message.content:
        await message.channel.send(f'三色糰子啊，以前妖夢...')
        await asyncio.sleep(3)
        await message.channel.send(f'...')
        await asyncio.sleep(3)
        await message.channel.send(f'算了 妖夢不在 我就算不吃東西 反正我是餓不死的存在')
        await asyncio.sleep(3)
        await message.channel.send(f'... 妖夢...你在哪...我好想你...')
        await asyncio.sleep(3)
        await message.channel.send(f'To be continued...\n-# 妖夢機器人即將到來')
    
    if message.content == "早安":
        if message.author.id == AUTHOR_ID:
            await message.reply("早安 主人 今日的開發目標順利嗎")
        else:
            await message.reply("早上好 今天有什麽事情儘早完成喲", mention_author=False)
    
    if message.content == "午安":
        if message.author.id == AUTHOR_ID:
            await message.reply("下午好呀 今天似乎沒有什麽事情可以做呢")
        else:
            await message.reply("中午好啊 看起來汝似乎無所事事的呢", mention_author=False)
    
    if message.content == "晚安":
        current_time = datetime.now().strftime("%H:%M")
        
        if message.author.id == AUTHOR_ID:
            await message.reply(f"你趕快去睡覺 現在已經是 {current_time} 了 別再熬夜了！")
        else:
            await message.reply(f"現在的時間是 {current_time} 汝還不就寢嗎？", mention_author=False)
    
    if '閉嘴蜘蛛俠' in message.content:
        await message.channel.send(f'deadpool:This is Deadpool 2, not Titanic! Stop serenading me, Celine!')
        await asyncio.sleep(3)
        await message.channel.send(f'deadpool:You’re singing way too good, can you sing it like crap for me?!')
        await asyncio.sleep(3)
        await message.channel.send(f'Celine Dion:Shut up, Spider-Man!')
        await asyncio.sleep(3)
        await message.channel.send(f'deadpool:sh*t, I really should have gone with NSYNC!')
        
    if '普奇神父' in message.content:
        await message.channel.send("引力を信じるか？")
        await asyncio.sleep(3)
        await message.channel.send("私は最初にキノコを食べた者を尊敬する。毒キノコかもしれないのに。")
        await asyncio.sleep(5)
        await message.channel.send("DIO…")
        await asyncio.sleep(2)
        await message.channel.send("私がこの力を完全に使いこなせるようになったら、必ず君を目覚めさせるよ。")
        await asyncio.sleep(5)
        await message.channel.send("人は…いずれ天国へ至るものだ。")
        await asyncio.sleep(3)
        await message.channel.send("最後に言うよ…時間が加速し始める。降りてこい、DIO。")
        await asyncio.sleep(1)
        await message.channel.send("螺旋階段、甲虫、廃墟の街、果物のタルト、ドロテアの道、特異点、ジョット、天使、紫陽花、秘密の皇帝…")
        await asyncio.sleep(2)
        await message.channel.send("ここまでだ。")
        await message.channel.send("天国へのカウントダウンが始まる…")
        await asyncio.sleep(2)
        await message.channel.send("# メイド・イン・ヘブン！！")
    
    if '關於停雲' in message.content:
        await message.channel.send(f"停雲小姐呀")
        await asyncio.sleep(3)
        await message.channel.send(f"我記的是一位叫yan的開發者製作的一個discord bot 吧~")
        await asyncio.sleep(3)
        await message.channel.send(f"汝 是否是想説 “我爲何知道的呢” 呵呵")
        await asyncio.sleep(3)
        await message.channel.send(f"那是我的主人告訴我滴喲~ 欸嘿~")
        
    if '蘿莉？' in message.content:
        await message.channel.send("蘿莉控？")
        await asyncio.sleep(5)

        if message.guild:
            members = [member.id for member in message.guild.members if not member.bot]
            if members:
                random_user_id = random.choice(members)
                await message.channel.send(f"您是說 {random_user_id} 這位用戶嗎")
            else:
                await message.channel.send("這個伺服器內沒有普通成員。")
        else:
            await message.channel.send("這個能力只能在伺服器內使用。")

    await bot.process_commands(message)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    
    print("------")
    
    print("斜線指令已自動同步。")
    
    await send_global_webhook_message("✅ **機器人已上線！**", discord.Color.green())
    
    try:
        await bot.change_presence(
            status=discord.Status.dnd,
            activity=discord.Activity(type=discord.ActivityType.playing, name='Honkai:Star rail')
        )
        print("已設置機器人的狀態。")
    
    except Exception as e:
        print(f"Failed to set presence: {e}")
    
    end_time = time.time()
    startup_time = end_time - start_time
    print(f'Bot startup time: {startup_time:.2f} seconds')
    
    print('加入的伺服器列表：')
    for guild in bot.guilds:
        print(f'- {guild.name} (ID: {guild.id})')
    
    global last_activity_time
    last_activity_time = time.time()
    
    bot.loop.create_task(check_long_disconnect())
    
    init_db()

@bot.slash_command(name="join", description="讓幽幽子飄進你的語音頻道哦～")
async def join(ctx: ApplicationContext):
    """讓幽幽子輕輕飄進使用者的語音頻道，只有特定的人能喚我哦～"""
    # Defer the response to avoid interaction timeout
    await ctx.defer(ephemeral=True)  # Use ephemeral=True if you want the "Bot is thinking..." message to be private

    # 檢查權限
    if ctx.author.id != AUTHOR_ID:
        embed = Embed(
            description="哎呀～你不是能喚我的人呢，這份櫻花餅不給你吃哦～",
            color=0xFFB6C1  # 粉色 LightPink
        )
        await ctx.followup.send(embed=embed, ephemeral=True)
        return

    # 檢查使用者是否在語音頻道
    if not ctx.author.voice:
        embed = Embed(
            description="嗯？你沒在語音頻道裡呀～幽幽子可不會自己找地方飄哦～",
            color=0xFFB6C1
        )
        await ctx.followup.send(embed=embed, ephemeral=True)
        return

    # 獲取語音頻道並檢查權限
    channel = ctx.author.voice.channel
    if not channel.permissions_for(ctx.guild.me).connect:
        embed = Embed(
            description="哎呀～這個頻道不歡迎幽幽子呢，沒法飄進去啦～",
            color=0xFFB6C1
        )
        await ctx.followup.send(embed=embed, ephemeral=True)
        return

    # 加入或移動到頻道
    voice_client = ctx.voice_client
    try:
        if voice_client:
            await voice_client.move_to(channel)
            action = "飄到了"
        else:
            await channel.connect()
            action = "輕輕飄進了"
    except discord.ClientException as e:
        embed = Embed(
            description=f"哎呀呀～飄不進去呢，因為 {e}，櫻花都掉了～",
            color=0xFFB6C1
        )
        await ctx.followup.send(embed=embed, ephemeral=True)
        return

    # 成功回應，用 bot 頭像
    embed = Embed(
        description=f"幽幽子我{action} {channel.name} 啦～有沒有好吃的等著我呀？",
        color=0xFFB6C1
    )
    embed.set_thumbnail(url=ctx.bot.user.avatar.url)  # 直接用 bot 頭像
    await ctx.followup.send(embed=embed)

@bot.slash_command(name="leave", description="讓幽幽子飄離語音頻道啦～")
async def leave(ctx: ApplicationContext):
    """讓幽幽子從語音頻道飄走，只有特定的人能趕我走哦～"""
    # 檢查權限
    if ctx.author.id != AUTHOR_ID:
        embed = Embed(
            description="嘻嘻～你不是能趕走我的人哦，幽幽子還想多吃點呢～",
            color=0xFFB6C1
        )
        await ctx.respond(embed=embed, ephemeral=True)
        return

    # 檢查機器人是否在語音頻道
    voice_client = ctx.voice_client
    if not voice_client:
        embed = Embed(
            description="咦？我還沒飄進任何頻道呢，怎麼趕我走呀～",
            color=0xFFB6C1
        )
        await ctx.respond(embed=embed, ephemeral=True)
        return

    # 離開頻道
    try:
        await voice_client.disconnect()
        embed = Embed(
            description="好吧～幽幽子飄走啦，掰掰～下次記得多準備點點心哦～",
            color=0xFFB6C1
        )
        embed.set_thumbnail(url=ctx.bot.user.avatar.url)  # 直接用 bot 頭像
    except discord.ClientException as e:
        embed = Embed(
            description=f"哎呀～飄不出去呢，因為 {e}，櫻花餅都沒吃完～",
            color=0xFFB6C1
        )
        await ctx.respond(embed=embed, ephemeral=True)
        return

    await ctx.respond(embed=embed)

@bot.slash_command(name="invite", description="生成幽幽子的邀請鏈接，邀她共舞於你的伺服器")
async def invite(ctx: discord.ApplicationContext):
    if not bot.user:
        await ctx.respond(
            "哎呀～幽幽子的靈魂似乎尚未降臨此處，請稍後再試哦。",
            ephemeral=True
        )
        return

    client_id = bot.user.id
    permissions = discord.Permissions(
        manage_channels=True,
        manage_roles=True,
        ban_members=True,
        kick_members=True
    )
    query = {
        "client_id": client_id,
        "permissions": permissions,
        "scope": "bot applications.commands"
    }
    invite_url = f"https://discord.com/oauth2/authorize?{urlencode(query)}"
    
    embed = discord.Embed(
        title="邀請幽幽子降臨你的伺服器",
        description=(
            "幽幽子輕拂櫻花，緩緩飄至你的身旁。\n"
            "與她共賞生死輪迴，品味片刻寧靜吧～\n\n"
            f"🌸 **[點此邀請幽幽子]({invite_url})** 🌸"
        ),
        color=discord.Color.from_rgb(255, 182, 193)
    )
    
    if bot.user.avatar:
        embed.set_thumbnail(url=bot.user.display_avatar.url)
    
    yuyuko_quotes = [
        "生與死不過一線之隔，何不輕鬆以對？",
        "櫻花散落之時，便是與我共舞之刻。",
        "肚子餓了呢～有沒有好吃的供品呀？"
    ]
    embed.set_footer(text=random.choice(yuyuko_quotes))
    
    await ctx.respond(embed=embed)

@bot.slash_command(name="server_bank", description="與幽幽子的金庫互動，存錢、取錢或借貸～")
async def server_bank(ctx: discord.ApplicationContext):
    guild_id = str(ctx.guild.id)
    user_id = str(ctx.author.id)
    server_name = ctx.guild.name

    def load_json(file):
        try:
            with open(file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
    
    def save_json(file, data):
        with open(file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def format_number(num):
        if num >= 1e20:
            return f"{num / 1e20:.2f} 兆京"
        elif num >= 1e16:
            return f"{num / 1e16:.2f} 京"
        elif num >= 1e12:
            return f"{num / 1e12:.2f} 兆"
        elif num >= 1e8:
            return f"{num / 1e8:.2f} 億"
        else:
            return f"{num:.2f}"

    def check_loan_status(server_config, guild_id, user_id):
        if guild_id not in server_config or "loans" not in server_config[guild_id]:
            return None

        if user_id not in server_config[guild_id]["loans"]:
            return None

        loan = server_config[guild_id]["loans"][user_id]
        if loan["repaid"]:
            return None

        due_date = datetime.fromisoformat(loan["due_date"])
        current_date = datetime.now()

        if current_date > due_date and loan["interest_rate"] == 0.1:
            loan["interest_rate"] = 0.2
            server_config[guild_id]["loans"][user_id] = loan
            save_json("server_config.json", server_config)

        return loan

    balance = load_json("balance.json")
    server_config = load_json("server_config.json")
    personal_bank = load_json("personal_bank.json")

    if guild_id not in balance:
        balance[guild_id] = {}
    if user_id not in balance[guild_id]:
        balance[guild_id][user_id] = 0

    if guild_id not in personal_bank:
        personal_bank[guild_id] = {}
    if user_id not in personal_bank[guild_id]:
        personal_bank[guild_id][user_id] = 0

    if guild_id not in server_config:
        server_config[guild_id] = {}
    if "server_bank" not in server_config[guild_id]:
        server_config[guild_id]["server_bank"] = {
            "total": 0,
            "contributions": {}
        }

    user_balance = balance[guild_id][user_id]
    personal_bank_balance = personal_bank[guild_id][user_id]
    server_bank_balance = server_config[guild_id]["server_bank"]["total"]

    loan = check_loan_status(server_config, guild_id, user_id)
    loan_info = ""
    if loan:
        due_date = datetime.fromisoformat(loan["due_date"])
        amount_with_interest = round(loan["amount"] * (1 + loan["interest_rate"]), 2)
        loan_info = (
            f"\n\n⚠️ 你有一筆未還款的借貸！\n"
            f"借貸金額：{format_number(loan['amount'])} 幽靈幣\n"
            f"當前利息率：{loan['interest_rate'] * 100:.0f}%\n"
            f"需還款金額：{format_number(amount_with_interest)} 幽靈幣\n"
            f"還款截止日期：{due_date.strftime('%Y-%m-%d %H:%M:%S')}"
        )

    embed = discord.Embed(
        title="🌸 幽幽子的金庫 🌸",
        description=(
            f"歡迎來到 **{server_name}** 的金庫，你是要存錢、取錢還是借貸？\n\n"
            f"你的餘額：{format_number(user_balance)} 幽靈幣\n"
            f"你的個人金庫：{format_number(personal_bank_balance)} 幽靈幣\n"
            f"國庫餘額：{format_number(server_bank_balance)} 幽靈幣"
            f"{loan_info}"
        ),
        color=discord.Color.from_rgb(255, 182, 193)
    )

    class BankButtons(discord.ui.View):
        def __init__(self, has_loan):
            super().__init__(timeout=None)
            self.has_loan = has_loan

        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message("這不是你的金庫操作哦～", ephemeral=True)
                return False
            return True

        @discord.ui.button(label="取錢", style=discord.ButtonStyle.success)
        async def withdraw(self, button: discord.ui.Button, interaction: discord.Interaction):
            await interaction.response.send_modal(WithdrawModal(self.message, self.has_loan))

        @discord.ui.button(label="存錢", style=discord.ButtonStyle.primary)
        async def deposit(self, button: discord.ui.Button, interaction: discord.Interaction):
            await interaction.response.send_modal(DepositModal(self.message, self.has_loan))

        if not loan:
            @discord.ui.button(label="借貸", style=discord.ButtonStyle.danger)
            async def borrow(self, button: discord.ui.Button, interaction: discord.Interaction):
                await interaction.response.send_modal(BorrowModal(self.message, self.has_loan))
        else:
            @discord.ui.button(label="還款", style=discord.ButtonStyle.green)
            async def repay(self, button: discord.ui.Button, interaction: discord.Interaction):
                server_config = load_json("server_config.json")
                loan = check_loan_status(server_config, guild_id, user_id)
                if not loan or loan["repaid"]:
                    await interaction.response.send_message(embed=discord.Embed(
                        title="🌸 無需還款！🌸",
                        description="你目前沒有未還款的借貸哦～",
                        color=discord.Color.red()
                    ), ephemeral=True)
                    return

                balance = load_json("balance.json")
                user_balance = balance[guild_id][user_id]
                amount_with_interest = round(loan["amount"] * (1 + loan["interest_rate"]), 2)

                if user_balance < amount_with_interest:
                    await interaction.response.send_message(embed=discord.Embed(
                        title="🌸 餘額不足！🌸",
                        description=f"你需要 {format_number(amount_with_interest)} 幽靈幣來還款，但你的餘額只有 {format_number(user_balance)} 幽靈幣哦～",
                        color=discord.Color.red()
                    ), ephemeral=True)
                    return

                balance[guild_id][user_id] -= amount_with_interest
                server_config[guild_id]["server_bank"]["total"] += amount_with_interest
                server_config[guild_id]["loans"][user_id]["repaid"] = True
                save_json("balance.json", balance)
                save_json("server_config.json", server_config)

                embed = discord.Embed(
                    title="🌸 還款成功！🌸",
                    description=(
                        f"你已還款 **{format_number(amount_with_interest)} 幽靈幣**（包含利息）～\n\n"
                        f"你的新餘額：{format_number(balance[guild_id][user_id])} 幽靈幣\n"
                        f"國庫新餘額：{format_number(server_config[guild_id]['server_bank']['total'])} 幽靈幣"
                    ),
                    color=discord.Color.gold()
                )
                await self.message.edit(embed=embed, view=BankButtons(has_loan=False))

    class WithdrawModal(discord.ui.Modal):
        def __init__(self, message, has_loan):
            super().__init__(title="幽幽子的金庫 - 取錢", timeout=60)
            self.message = message
            self.has_loan = has_loan
            self.add_item(discord.ui.InputText(
                label="輸入取款金額",
                placeholder="輸入你想從個人金庫取出的幽靈幣金額",
                style=discord.InputTextStyle.short
            ))

        async def callback(self, interaction: discord.Interaction):
            try:
                amount = float(self.children[0].value)
                amount = round(amount, 2)
                if amount <= 0:
                    await interaction.response.send_message(embed=discord.Embed(
                        title="🌸 無效金額！🌸",
                        description="取款金額必須大於 0 哦～",
                        color=discord.Color.red()
                    ), ephemeral=True)
                    return

                balance = load_json("balance.json")
                personal_bank = load_json("personal_bank.json")
                personal_bank_balance = personal_bank[guild_id][user_id]

                if amount > personal_bank_balance:
                    await interaction.response.send_message(embed=discord.Embed(
                        title="🌸 個人金庫餘額不足！🌸",
                        description=f"你的個人金庫只有 {format_number(personal_bank_balance)} 幽靈幣，無法取出 {format_number(amount)} 哦～",
                        color=discord.Color.red()
                    ), ephemeral=True)
                    return

                personal_bank[guild_id][user_id] -= amount
                balance[guild_id][user_id] += amount
                save_json("balance.json", balance)
                save_json("personal_bank.json", personal_bank)

                embed = discord.Embed(
                    title="🌸 取款成功！🌸",
                    description=(
                        f"你從個人金庫取出了 **{format_number(amount)} 幽靈幣**～\n\n"
                        f"你的新餘額：{format_number(balance[guild_id][user_id])} 幽靈幣\n"
                        f"你的個人金庫新餘額：{format_number(personal_bank[guild_id][user_id])} 幽靈幣"
                    ),
                    color=discord.Color.gold()
                )
                await self.message.edit(embed=embed, view=BankButtons(self.has_loan))

            except ValueError:
                await interaction.response.send_message(embed=discord.Embed(
                    title="🌸 無效金額！🌸",
                    description="請輸入有效的數字金額哦～",
                    color=discord.Color.red()
                ), ephemeral=True)

    class DepositModal(discord.ui.Modal):
        def __init__(self, message, has_loan):
            super().__init__(title="幽幽子的金庫 - 存錢", timeout=60)
            self.message = message
            self.has_loan = has_loan
            self.add_item(discord.ui.InputText(
                label="輸入存款金額",
                placeholder="輸入你想存入個人金庫的幽靈幣金額",
                style=discord.InputTextStyle.short
            ))

        async def callback(self, interaction: discord.Interaction):
            try:
                amount = float(self.children[0].value)
                amount = round(amount, 2)
                if amount <= 0:
                    await interaction.response.send_message(embed=discord.Embed(
                        title="🌸 無效金額！🌸",
                        description="存款金額必須大於 0 哦～",
                        color=discord.Color.red()
                    ), ephemeral=True)
                    return

                balance = load_json("balance.json")
                personal_bank = load_json("personal_bank.json")
                user_balance = balance[guild_id][user_id]

                if amount > user_balance:
                    await interaction.response.send_message(embed=discord.Embed(
                        title="🌸 餘額不足！🌸",
                        description=f"你的餘額只有 {format_number(user_balance)} 幽靈幣，無法存入 {format_number(amount)} 哦～",
                        color=discord.Color.red()
                    ), ephemeral=True)
                    return

                if guild_id not in balance:
                    balance[guild_id] = {}
                if user_id not in balance[guild_id] or not isinstance(balance[guild_id][user_id], (int, float)):
                    balance[guild_id][user_id] = 0

                if guild_id not in personal_bank:
                    personal_bank[guild_id] = {}
                if user_id not in personal_bank[guild_id] or not isinstance(personal_bank[guild_id][user_id], (int, float)):
                    personal_bank[guild_id][user_id] = 0

                print(f"扣款前: balance[{guild_id}][{user_id}] = {balance[guild_id][user_id]}")
                balance[guild_id][user_id] -= amount
                print(f"扣款後: balance[{guild_id}][{user_id}] = {balance[guild_id][user_id]}")
                print(f"存款前: personal_bank[{guild_id}][{user_id}] = {personal_bank[guild_id][user_id]}")
                personal_bank[guild_id][user_id] += amount
                print(f"存款後: personal_bank[{guild_id}][{user_id}] = {personal_bank[guild_id][user_id]}")
                
                save_json("balance.json", balance)
                save_json("personal_bank.json", personal_bank)

                embed = discord.Embed(
                    title="🌸 存款成功！🌸",
                    description=(
                        f"你存入了 **{format_number(amount)} 幽靈幣** 到個人金庫～\n\n"
                        f"你的新餘額：{format_number(balance[guild_id][user_id])} 幽靈幣\n"
                        f"你的個人金庫新餘額：{format_number(personal_bank[guild_id][user_id])} 幽靈幣"
                    ),
                    color=discord.Color.gold()
                )
                await self.message.edit(embed=embed, view=BankButtons(self.has_loan))

            except ValueError:
                await interaction.response.send_message(embed=discord.Embed(
                    title="🌸 無效金額！🌸",
                    description="請輸入有效的數字金額哦～",
                    color=discord.Color.red()
                ), ephemeral=True)
            except Exception as e:
                print(f"DepositModal.callback 發生錯誤: {e}")
                await interaction.response.send_message(embed=discord.Embed(
                    title="🌸 系統錯誤！🌸",
                    description="存錢時發生錯誤，請稍後再試～",
                    color=discord.Color.red()
                ), ephemeral=True)

    class BorrowModal(discord.ui.Modal):
        def __init__(self, message, has_loan):
            super().__init__(title="幽幽子的金庫 - 借貸", timeout=60)
            self.message = message
            self.has_loan = has_loan
            self.add_item(discord.ui.InputText(
                label="輸入借貸金額",
                placeholder="輸入你想從國庫借的幽靈幣金額",
                style=discord.InputTextStyle.short
            ))

        async def callback(self, interaction: discord.Interaction):
            try:
                amount = float(self.children[0].value)
                amount = round(amount, 2)
                if amount <= 0:
                    await interaction.response.send_message(embed=discord.Embed(
                        title="🌸 無效金額！🌸",
                        description="借貸金額必須大於 0 哦～",
                        color=discord.Color.red()
                    ), ephemeral=True)
                    return

                balance = load_json("balance.json")
                server_config = load_json("server_config.json")
                server_bank_balance = server_config[guild_id]["server_bank"]["total"]

                if amount > server_bank_balance:
                    await interaction.response.send_message(embed=discord.Embed(
                        title="🌸 國庫餘額不足！🌸",
                        description=f"國庫只有 {format_number(server_bank_balance)} 幽靈幣，無法借出 {format_number(amount)} 哦～",
                        color=discord.Color.red()
                    ), ephemeral=True)
                    return

                borrowed_at = datetime.now()
                due_date = borrowed_at + timedelta(days=5)
                if "loans" not in server_config[guild_id]:
                    server_config[guild_id]["loans"] = {}
                server_config[guild_id]["loans"][user_id] = {
                    "amount": amount,
                    "interest_rate": 0.1,
                    "borrowed_at": borrowed_at.isoformat(),
                    "due_date": due_date.isoformat(),
                    "repaid": False
                }

                server_config[guild_id]["server_bank"]["total"] -= amount
                balance[guild_id][user_id] += amount
                save_json("balance.json", balance)
                save_json("server_config.json", server_config)

                embed = discord.Embed(
                    title="🌸 借貸成功！🌸",
                    description=(
                        f"你從國庫借了 **{format_number(amount)} 幽靈幣**～\n"
                        f"初始利息率：10%\n"
                        f"需還款金額：{format_number(amount * 1.1)} 幽靈幣\n"
                        f"還款截止日期：{due_date.strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"（若逾期未還，利息將翻倍至 20%！）\n\n"
                        f"你的新餘額：{format_number(balance[guild_id][user_id])} 幽靈幣\n"
                        f"國庫新餘額：{format_number(server_config[guild_id]['server_bank']['total'])} 幽靈幣"
                    ),
                    color=discord.Color.gold()
                )
                await self.message.edit(embed=embed, view=BankButtons(has_loan=True))

            except ValueError:
                await interaction.response.send_message(embed=discord.Embed(
                    title="🌸 無效金額！🌸",
                    description="請輸入有效的數字金額哦～",
                    color=discord.Color.red()
                ), ephemeral=True)

    view = BankButtons(has_loan=bool(loan))
    message = await ctx.respond(embed=embed, view=view)
    view.message = message

@bot.slash_command(name="tax", description="幽幽子對伺服器內所有用戶徵收40%的稅金，存入國庫～")
async def tax(ctx: discord.ApplicationContext):
    guild_id = str(ctx.guild.id)
    user_id = str(ctx.author.id)
    
    AUTHOR_ID = os.getenv('AUTHOR_ID', "0")
    print(f"調試: user_id = {user_id}, AUTHOR_ID = {AUTHOR_ID}")
    
    if user_id != AUTHOR_ID:
        await ctx.respond(embed=discord.Embed(
            title="🌸 權限不足！🌸",
            description="只有幽幽子的主人才能徵稅哦～",
            color=discord.Color.red()
        ))
        return

    await ctx.defer()

    def load_json(file):
        try:
            with open(file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save_json(file, data):
        with open(file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def format_number(num):
        if num >= 1e20:
            return f"{num / 1e20:.2f} 兆京"
        elif num >= 1e16:
            return f"{num / 1e16:.2f} 京"
        elif num >= 1e12:
            return f"{num / 1e12:.2f} 兆"
        elif num >= 1e8:
            return f"{num / 1e8:.2f} 億"
        else:
            return f"{num:.2f}"

    balance = load_json("balance.json")
    server_config = load_json("server_config.json")

    if not balance.get(guild_id):
        await ctx.followup.send(embed=discord.Embed(
            title="🌸 無人可稅！🌸",
            description="這個伺服器還沒有人有幽靈幣哦～快去玩遊戲賺錢吧！",
            color=discord.Color.red()
        ))
        return

    tax_rate = 0.4
    total_tax = 0
    taxed_users = []

    for taxed_user_id, user_balance in balance[guild_id].items():
        if taxed_user_id == user_id:
            continue
        if user_balance <= 0:
            continue

        tax_amount = round(user_balance * tax_rate, 2)
        new_balance = round(user_balance - tax_amount, 2)
        balance[guild_id][taxed_user_id] = new_balance
        total_tax += tax_amount

        try:
            user = await bot.fetch_user(int(taxed_user_id))
            display_name = user.display_name
        except discord.errors.NotFound:
            display_name = f"用戶ID: {taxed_user_id}"
        taxed_users.append(f"**{display_name}**：{format_number(tax_amount)} 幽靈幣")

    if not taxed_users:
        await ctx.followup.send(embed=discord.Embed(
            title="🌸 無人可稅！🌸",
            description="沒有人有足夠的幽靈幣可以徵稅哦～",
            color=discord.Color.red()
        ))
        return

    if guild_id not in server_config:
        server_config[guild_id] = {}
    if "server_bank" not in server_config[guild_id]:
        server_config[guild_id]["server_bank"] = {
            "total": 0,
            "contributions": {}
        }

    server_config[guild_id]["server_bank"]["total"] += total_tax

    for taxed_user_id in balance[guild_id]:
        if taxed_user_id == user_id:
            continue
        tax_amount = round(balance[guild_id][taxed_user_id] * tax_rate / (1 - tax_rate) * tax_rate, 2)
        if tax_amount <= 0:
            continue
        if taxed_user_id not in server_config[guild_id]["server_bank"]["contributions"]:
            server_config[guild_id]["server_bank"]["contributions"][taxed_user_id] = 0
        server_config[guild_id]["server_bank"]["contributions"][taxed_user_id] += tax_amount

    save_json("balance.json", balance)
    save_json("server_config.json", server_config)

    executor = ctx.author.display_name
    embed = discord.Embed(
        title="🌸 幽幽子的稅金徵收！🌸",
        description=(
            f"幽幽子對伺服器內所有用戶徵收了 40% 的稅金，存入國庫～\n"
            f"徵稅執行者：**{executor}**\n\n"
            f"被徵稅者：\n" + "\n".join(taxed_users) + f"\n\n"
            f"總稅金：{format_number(total_tax)} 幽靈幣\n"
            f"國庫當前餘額：{format_number(server_config[guild_id]['server_bank']['total'])} 幽靈幣"
        ),
        color=discord.Color.from_rgb(255, 182, 193)
    )
    await ctx.followup.send(embed=embed)

@bot.slash_command(name="blackjack", description="幽幽子與你共舞一場21點遊戲～")
async def blackjack(ctx: discord.ApplicationContext, bet: float):
    bet = round(bet, 2)
    
    user_id = str(ctx.author.id)
    guild_id = str(ctx.guild.id)

    def load_json(file):
        try:
            with open(file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save_json(file, data):
        with open(file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def load_yaml(file):
        try:
            with open(file, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            return {}

    config = load_yaml("config_user.yml")
    balance = load_json("balance.json")
    invalid_bet_count = load_json("invalid_bet_count.json")
    blackjack_data = load_json("blackjack_data.json")

    if bet <= 0:
        invalid_bet_count.setdefault(guild_id, {}).setdefault(user_id, 0)
        invalid_bet_count[guild_id][user_id] += 1
        save_json("invalid_bet_count.json", invalid_bet_count)

        if invalid_bet_count[guild_id][user_id] >= 2:
            balance.get(guild_id, {}).pop(user_id, None)
            save_json("balance.json", balance)
            invalid_bet_count[guild_id].pop(user_id, None)
            save_json("invalid_bet_count.json", invalid_bet_count)

            await ctx.respond(embed=discord.Embed(
                title="🌸 靈魂的代價 🌸",
                description="哎呀～你多次試圖用無效的賭注欺騙幽幽子，你的幽靈幣已被清空了哦！",
                color=discord.Color.red()
            ))
            return

        await ctx.respond(embed=discord.Embed(
            title="🌸 無效的賭注 🌸",
            description="嘻嘻，賭注必須大於 0 哦～別想騙過幽幽子的眼睛！",
            color=discord.Color.red()
        ))
        return

    user_balance = round(balance.get(guild_id, {}).get(user_id, 0), 2)
    if user_balance < bet:
        await ctx.respond(embed=discord.Embed(
            title="🌸 幽靈幣不足 🌸",
            description=f"你的幽靈幣只有 {user_balance:.2f}，無法下注 {bet:.2f} 哦～再去收集一些吧！",
            color=discord.Color.red()
        ))
        return

    def create_deck():
        return [2, 3, 4, 5, 6, 7, 8, 9, 10, "J", "Q", "K", "A"] * 4

    def calculate_hand(cards):
        value = 0
        aces = 0
        for card in cards:
            if card in ["J", "Q", "K"]:
                value += 10
            elif card == "A":
                aces += 1
                value += 11
            else:
                value += card

        while value > 21 and aces:
            value -= 10
            aces -= 1

        return value

    deck = create_deck()
    random.shuffle(deck)

    player_cards = [deck.pop(), deck.pop()]
    dealer_cards = [deck.pop(), deck.pop()]

    balance.setdefault(guild_id, {})[user_id] = round(user_balance - bet, 2)
    save_json("balance.json", balance)

    is_gambler = config.get(guild_id, {}).get(user_id, {}).get('job') == '賭徒'

    blackjack_data.setdefault(guild_id, {})[user_id] = {
        "player_cards": player_cards,
        "dealer_cards": dealer_cards,
        "bet": bet,
        "game_status": "ongoing",
        "double_down_used": False,
        "is_gambler": is_gambler
    }
    save_json("blackjack_data.json", blackjack_data)

    player_total = calculate_hand(player_cards)
    if player_total == 21:
        blackjack_data[guild_id][user_id]["game_status"] = "ended"
        save_json("blackjack_data.json", blackjack_data)

        multiplier = 5 if is_gambler else 2.5
        reward = round(bet * multiplier, 2)
        balance[guild_id][user_id] += reward
        save_json("balance.json", balance)

        await ctx.respond(embed=discord.Embed(
            title="🌸 黑傑克！靈魂的勝利！🌸",
            description=f"你的手牌: {player_cards}\n幽幽子為你獻上 {reward:.2f} 幽靈幣的祝福～",
            color=discord.Color.gold()
        ))
        return

    embed = discord.Embed(
        title="🌸 幽幽子的21點遊戲開始！🌸",
        description=(
            f"你下注了 **{bet:.2f} 幽靈幣**，讓我們共舞一場吧～\n\n"
            f"你的初始手牌: {player_cards} (總點數: {calculate_hand(player_cards)})\n幽幽子的明牌: {dealer_cards[0]}"
        ),
        color=discord.Color.from_rgb(255, 182, 193)
    )
    embed.set_footer(text="選擇你的命運吧～")

    class BlackjackButtons(discord.ui.View):
        def __init__(self, deck, interaction: discord.Interaction, blackjack_data):
            super().__init__(timeout=180)
            self.deck = deck
            self.interaction = interaction
            self.blackjack_data = blackjack_data

        async def on_timeout(self):
            try:
                if self.blackjack_data[guild_id][user_id]["game_status"] == "ongoing":
                    balance = load_json("balance.json")
                    bet = self.blackjack_data[guild_id][user_id]["bet"]
                    balance[guild_id][user_id] += bet
                    save_json("balance.json", balance)
                    self.blackjack_data[guild_id][user_id]["game_status"] = "ended"
                    save_json("blackjack_data.json", self.blackjack_data)
                    await self.interaction.edit_original_response(
                        embed=discord.Embed(
                            title="🌸 遊戲超時，靈魂休息了～🌸",
                            description=f"時間到了，遊戲已結束。退還你的賭注 {bet:.2f} 幽靈幣，下次再來挑戰幽幽子吧！",
                            color=discord.Color.blue()
                        ),
                        view=None
                    )
            except discord.errors.NotFound:
                pass

        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message("這不是你的遊戲哦～", ephemeral=True)
                return False
            return True

        async def auto_settle(self, interaction: discord.Interaction):
            player_cards = self.blackjack_data[guild_id][user_id]["player_cards"]
            player_total = calculate_hand(player_cards)
            if player_total == 21:
                self.blackjack_data[guild_id][user_id]["game_status"] = "ended"
                bet = self.blackjack_data[guild_id][user_id]["bet"]
                is_gambler = self.blackjack_data[guild_id][user_id]["is_gambler"]
                multiplier = 5 if is_gambler else 2.5
                reward = round(bet * multiplier, 2)
                balance = load_json("balance.json")
                balance[guild_id][user_id] += reward
                save_json("balance.json", balance)
                save_json("blackjack_data.json", self.blackjack_data)

                await interaction.edit_original_response(embed=discord.Embed(
                    title="🌸 黑傑克！靈魂的勝利！🌸",
                    description=f"你的手牌: {player_cards}\n幽幽子為你獻上 {reward:.2f} 幽靈幣的祝福～",
                    color=discord.Color.gold()
                ), view=None)
                return True
            return False

        @discord.ui.button(label="抽牌 (Hit)", style=discord.ButtonStyle.primary)
        async def hit(self, button: discord.ui.Button, interaction: discord.Interaction):
            try:
                await interaction.response.defer()
                player_cards = self.blackjack_data[guild_id][user_id]["player_cards"]
                player_cards.append(self.deck.pop())
                player_total = calculate_hand(player_cards)

                if player_total > 21:
                    self.blackjack_data[guild_id][user_id]["game_status"] = "ended"
                    save_json("blackjack_data.json", self.blackjack_data)
                    await self.interaction.edit_original_response(embed=discord.Embed(
                        title="🌸 哎呀，靈魂爆掉了！🌸",
                        description=f"你的手牌: {player_cards}\n點數總計: {player_total}\n下次再來挑戰幽幽子吧～",
                        color=discord.Color.red()
                    ), view=None)
                    return

                if await self.auto_settle(interaction):
                    return

                await self.interaction.edit_original_response(embed=discord.Embed(
                    title="🌸 你抽了一張牌！🌸",
                    description=f"你的手牌: {player_cards}\n目前點數: {player_total}",
                    color=discord.Color.from_rgb(255, 182, 193)
                ), view=self)
            except discord.errors.NotFound:
                await interaction.followup.send("遊戲交互已失效，請重新開始一局！", ephemeral=True)

        @discord.ui.button(label="停牌 (Stand)", style=discord.ButtonStyle.danger)
        async def stand(self, button: discord.ui.Button, interaction: discord.Interaction):
            try:
                await interaction.response.defer()
                balance = load_json("balance.json")
                player_cards = self.blackjack_data[guild_id][user_id]["player_cards"]
                dealer_cards = self.blackjack_data[guild_id][user_id]["dealer_cards"]
                bet = self.blackjack_data[guild_id][user_id]["bet"]
                is_gambler = self.blackjack_data[guild_id][user_id]["is_gambler"]

                self.blackjack_data[guild_id][user_id]["game_status"] = "ended"
                save_json("blackjack_data.json", self.blackjack_data)

                dealer_total = calculate_hand(dealer_cards)
                while dealer_total < 17:
                    dealer_cards.append(self.deck.pop())
                    dealer_total = calculate_hand(dealer_cards)

                player_total = calculate_hand(player_cards)

                if dealer_total > 21 or player_total > dealer_total:
                    multiplier = 4 if is_gambler else 2
                    reward = round(bet * multiplier, 2)
                    balance[guild_id][user_id] += reward
                    save_json("balance.json", balance)
                    embed = discord.Embed(
                        title="🌸 靈魂的勝利！🌸",
                        description=f"你的手牌: {player_cards}\n幽幽子的手牌: {dealer_cards}\n你贏得了 {reward:.2f} 幽靈幣～",
                        color=discord.Color.gold()
                    )
                elif player_total == dealer_total:
                    reward = round(bet, 2)
                    balance[guild_id][user_id] += reward
                    save_json("balance.json", balance)
                    embed = discord.Embed(
                        title="🌸 平手，靈魂的平衡～🌸",
                        description=f"你的手牌: {player_cards}\n幽幽子的手牌: {dealer_cards}\n退還賭注: {reward:.2f} 幽靈幣",
                        color=discord.Color.from_rgb(255, 182, 193)
                    )
                else:
                    embed = discord.Embed(
                        title="🌸 殘念，幽幽子贏了！🌸",
                        description=f"你的手牌: {player_cards}\n幽幽子的手牌: {dealer_cards}\n下次再來挑戰吧～",
                        color=discord.Color.red()
                    )

                await self.interaction.edit_original_response(embed=embed, view=None)
            except discord.errors.NotFound:
                await interaction.followup.send("遊戲交互已失效，請重新開始一局！", ephemeral=True)

        @discord.ui.button(label="雙倍下注 (Double Down)", style=discord.ButtonStyle.success)
        async def double_down(self, button: discord.ui.Button, interaction: discord.Interaction):
            try:
                await interaction.response.defer()
                balance = load_json("balance.json")
                if self.blackjack_data[guild_id][user_id]["double_down_used"]:
                    await self.interaction.edit_original_response(embed=discord.Embed(
                        title="🌸 無法再次挑戰命運！🌸",
                        description="你已經使用過雙倍下注了哦～",
                        color=discord.Color.red()
                    ), view=None)
                    return

                bet = self.blackjack_data[guild_id][user_id]["bet"]
                is_gambler = self.blackjack_data[guild_id][user_id]["is_gambler"]
                user_balance = balance[guild_id][user_id]
                doubled_bet = bet * 2

                if user_balance < bet:
                    await self.interaction.edit_original_response(embed=discord.Embed(
                        title="🌸 嘻嘻，靈魂不夠喲～ 🌸",
                        description=f"你的幽靈幣只有 {user_balance:.2f}，不足以讓幽幽子給你雙倍下注 {doubled_bet:.2f} 哦～再去收集一些吧！",
                        color=discord.Color.red()
                    ), view=self)
                    return

                self.blackjack_data[guild_id][user_id]["bet"] = doubled_bet
                self.blackjack_data[guild_id][user_id]["double_down_used"] = True
                balance[guild_id][user_id] -= bet
                save_json("balance.json", balance)

                player_cards = self.blackjack_data[guild_id][user_id]["player_cards"]
                dealer_cards = self.blackjack_data[guild_id][user_id]["dealer_cards"]
                player_cards.append(self.deck.pop())
                player_total = calculate_hand(player_cards)

                self.blackjack_data[guild_id][user_id]["player_cards"] = player_cards
                self.blackjack_data[guild_id][user_id]["game_status"] = "ended"
                save_json("blackjack_data.json", self.blackjack_data)

                embed = discord.Embed(
                    title="🌸 雙倍下注，挑戰命運！🌸",
                    description=f"你的手牌: {player_cards} (總點數: {player_total})\n賭注翻倍為 {doubled_bet:.2f} 幽靈幣",
                    color=discord.Color.gold()
                )

                if player_total > 21:
                    embed.title = "🌸 哎呀，靈魂爆掉了！🌸"
                    embed.description = f"你的手牌: {player_cards}\n總點數: {player_total}\n下次再來挑戰幽幽子吧～"
                    embed.color = discord.Color.red()
                    await self.interaction.edit_original_response(embed=embed, view=None)
                    return

                dealer_total = calculate_hand(dealer_cards)
                while dealer_total < 17:
                    dealer_cards.append(self.deck.pop())
                    dealer_total = calculate_hand(dealer_cards)

                if dealer_total > 21 or player_total > dealer_total:
                    multiplier = 4 if is_gambler else 2
                    reward = round(doubled_bet * multiplier, 2)
                    balance[guild_id][user_id] += reward
                    save_json("balance.json", balance)
                    embed.title = "🌸 靈魂的勝利！🌸"
                    embed.description = f"你的手牌: {player_cards}\n幽幽子的手牌: {dealer_cards}\n你贏得了 {reward:.2f} 幽靈幣～"
                    embed.color = discord.Color.gold()
                elif player_total == dealer_total:
                    reward = doubled_bet
                    balance[guild_id][user_id] += reward
                    save_json("balance.json", balance)
                    embed.title = "🌸 平手，靈魂的平衡～🌸"
                    embed.description = f"你的手牌: {player_cards}\n幽幽子的手牌: {dealer_cards}\n退還賭注: {reward:.2f} 幽靈幣"
                    embed.color = discord.Color.from_rgb(255, 182, 193)
                else:
                    embed.title = "🌸 殘念，幽幽子贏了！🌸"
                    embed.description = f"你的手牌: {player_cards}\n幽幽子的手牌: {dealer_cards}\n下次再來挑戰吧～"
                    embed.color = discord.Color.red()

                await self.interaction.edit_original_response(embed=embed, view=None)
            except discord.errors.NotFound:
                await interaction.followup.send("遊戲交互已失效，請重新開始一局！", ephemeral=True)

    interaction = await ctx.respond(embed=embed)
    view = BlackjackButtons(deck, interaction, blackjack_data)
    await interaction.edit_original_response(view=view)

@bot.slash_command(name="about-me", description="關於幽幽子的一切～")
async def about_me(ctx: discord.ApplicationContext):
    if not bot.user:
        await ctx.respond(
            "哎呀～幽幽子的靈魂似乎飄散了，暫時無法現身哦。",
            ephemeral=True
        )
        return

    current_hour = datetime.now().hour
    if 5 <= current_hour < 12:
        greeting = "清晨的櫻花正綻放"
    elif 12 <= current_hour < 18:
        greeting = "午後的微風輕拂花瓣"
    else:
        greeting = "夜晚的亡魂低語陣陣"

    embed = discord.Embed(
        title="🌸 關於幽幽子",
        description=(
            f"{greeting}，{ctx.author.mention}！\n\n"
            "我是西行寺幽幽子，亡魂之主，櫻花下的舞者。\n"
            "來吧，使用 `/` 指令與我共舞，探索生與死的奧秘～\n"
            "若迷失方向，不妨試試 `/help`，我會輕聲指引你。"
        ),
        color=discord.Color.from_rgb(255, 182, 193),
        timestamp=datetime.now()
    )

    if bot.user.avatar:
        embed.set_thumbnail(url=bot.user.display_avatar.url)

    embed.add_field(
        name="👻 幽幽子的秘密",
        value=(
            f"- **名稱：** {bot.user.name}\n"
            f"- **靈魂編號：** {bot.user.id}\n"
            f"- **存在形式：** Python + Pycord\n"
            f"- **狀態：** 飄浮中～"
        ),
        inline=False
    )

    embed.add_field(
        name="🖌️ 召喚我之人",
        value=(
            "- **靈魂契約者：** Miya253 (Shiroko253)\n"
            "- **[契約之地](https://github.com/Shiroko253/Project-zero)**"
        ),
        inline=False
    )

    yuyuko_quotes = [
        "櫻花飄落之際，生死不過一念。",
        "有沒有好吃的呀？我有點餓了呢～",
        "與我共舞吧，別讓靈魂孤單。"
    ]
    embed.set_footer(text=random.choice(yuyuko_quotes))

    await ctx.respond(embed=embed)

@bot.slash_command(name="balance", description="幽幽子為你窺探幽靈幣的數量～")
async def balance(ctx: discord.ApplicationContext):
    def format_number(num):
        if num >= 1e20:
            return f"{num / 1e20:.2f} 兆京"
        elif num >= 1e16:
            return f"{num / 1e16:.2f} 京"
        elif num >= 1e12:
            return f"{num / 1e12:.2f} 兆"
        elif num >= 1e8:
            return f"{num / 1e8:.2f} 億"
        else:
            return f"{num:.2f}"

    try:
        await ctx.defer(ephemeral=False)

        user_balance = load_json("balance.json")
        guild_id = str(ctx.guild.id)
        user_id = str(ctx.user.id)

        if guild_id not in user_balance:
            user_balance[guild_id] = {}

        balance = user_balance[guild_id].get(user_id, 0)

        yuyuko_comments = [
            "嘻嘻，你的幽靈幣數量真有趣呢～",
            "這些幽靈幣，會帶來什麼樣的命運呢？",
            "靈魂與幽靈幣的交響曲，幽幽子很喜歡哦～",
            "你的幽靈幣閃閃發光，櫻花都忍不住飄落了～",
            "這樣的數量，會讓幽靈們羨慕吧？"
        ]

        formatted_balance = format_number(balance)

        embed = discord.Embed(
            title="🌸 幽幽子的幽靈幣窺探 🌸",
            description=(
                f"**{ctx.user.display_name}**，讓幽幽子為你揭示吧～\n\n"
                f"在這片靈魂之地，你的幽靈幣餘額為：\n"
                f"**{formatted_balance} 幽靈幣**"
            ),
            color=discord.Color.from_rgb(255, 182, 193)
        )
        embed.set_footer(text=random.choice(yuyuko_comments))

        await ctx.respond(embed=embed, ephemeral=False)

    except Exception as e:
        logging.error(f"Unexpected error in balance command: {e}")
        if isinstance(e, discord.errors.NotFound) and e.code == 10062:
            logging.warning("Interaction expired in balance command, cannot respond.")
        else:
            try:
                yuyuko_error_comments = [
                    "下次再試試吧～靈魂的波動有時會捉弄我們哦～"
                ]
                await ctx.respond(
                    embed=discord.Embed(
                        title="🌸 哎呀，靈魂出錯了！🌸",
                        description=f"幽幽子試圖窺探你的幽靈幣時，發生了一點小意外…\n錯誤：{e}",
                        color=discord.Color.red()
                    ).set_footer(text=random.choice(yuyuko_error_comments)),
                    ephemeral=True
                )
            except discord.errors.NotFound:
                logging.warning("Failed to respond due to expired interaction.")

@bot.slash_command(name="leaderboard", description="查看幽靈幣餘額和金庫貢獻排行榜～")
async def leaderboard(ctx: discord.ApplicationContext):
    guild_id = str(ctx.guild.id)

    def load_json(file):
        try:
            with open(file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def format_number(num):
        if num >= 1e20:
            return f"{num / 1e20:.2f} 兆京"
        elif num >= 1e16:
            return f"{num / 1e16:.2f} 京"
        elif num >= 1e12:
            return f"{num / 1e12:.2f} 兆"
        elif num >= 1e8:
            return f"{num / 1e8:.2f} 億"
        else:
            return f"{num:.2f}"

    if not ctx.guild:
        await ctx.respond("此命令只能在伺服器中使用。", ephemeral=True)
        return

    await ctx.defer()

    balance_data = load_json("balance.json")
    server_config = load_json("server_config.json")

    embed = discord.Embed(
        title="🏆 幽幽子的排行榜 🏆",
        color=discord.Color.from_rgb(255, 182, 193)
    )

    if guild_id not in balance_data or not balance_data[guild_id]:
        embed.add_field(
            name="🌸 幽靈幣餘額排行榜 🌸",
            value="目前沒有餘額排行榜數據哦～快去賺取幽靈幣吧！",
            inline=False
        )
    else:
        guild_balances = balance_data[guild_id]
        sorted_balances = sorted(guild_balances.items(), key=lambda x: x[1], reverse=True)

        balance_leaderboard = []
        for index, (user_id, balance) in enumerate(sorted_balances[:10], start=1):
            try:
                member = ctx.guild.get_member(int(user_id))
                if member:
                    username = member.display_name
                else:
                    user = await bot.fetch_user(int(user_id))
                    username = user.display_name if user else f"用戶ID: {user_id}"
            except Exception as fetch_error:
                username = f"用戶ID: {user_id}"
            balance_leaderboard.append(f"**#{index}** - {username}: {format_number(balance)} 幽靈幣")

        balance_message = "\n".join(balance_leaderboard) if balance_leaderboard else "排行榜數據為空。"
        embed.add_field(
            name="🌸 幽靈幣餘額排行榜 🌸",
            value=balance_message,
            inline=False
        )

    if guild_id not in server_config or "server_bank" not in server_config[guild_id]:
        embed.add_field(
            name="🌸 金庫貢獻排行榜 🌸",
            value="金庫還沒有任何貢獻哦～快去存錢或被徵稅吧！",
            inline=False
        )
    else:
        contributions = server_config[guild_id]["server_bank"]["contributions"]
        sorted_contributions = sorted(contributions.items(), key=lambda x: x[1], reverse=True)

        contribution_leaderboard = []
        for index, (user_id, amount) in enumerate(sorted_contributions[:10], start=1):
            try:
                member = ctx.guild.get_member(int(user_id))
                if member:
                    username = member.display_name
                else:
                    user = await bot.fetch_user(int(user_id))
                    username = user.display_name if user else f"用戶ID: {user_id}"
            except Exception as fetch_error:
                username = f"用戶ID: {user_id}"
            contribution_leaderboard.append(f"**#{index}** - {username}: {format_number(amount)} 幽靈幣")

        contribution_message = "\n".join(contribution_leaderboard) if contribution_leaderboard else "排行榜數據為空。"
        embed.add_field(
            name="🌸 金庫貢獻排行榜 🌸",
            value=contribution_message,
            inline=False
        )

    embed.set_footer(text="排行榜僅顯示前 10 名")
    await ctx.followup.send(embed=embed)
        
@bot.slash_command(name="shop", description="🌸 來逛逛幽幽子的夢幻商店吧～")
async def shop(ctx: discord.ApplicationContext):
    guild_id = str(ctx.guild.id)
    user_id = str(ctx.author.id)

    if not shop_data:
        await ctx.respond("商店數據載入失敗了呢～請使用 `/feedback` 回報喔！", ephemeral=True)
        return

    ITEMS_PER_PAGE = 25
    total_pages = math.ceil(len(shop_data) / ITEMS_PER_PAGE)
    current_page = 0

    class ShopView(View):
        def __init__(self, page):
            super().__init__(timeout=60)
            self.page = page
            self.add_item(self.create_select_menu())

            if page > 0:
                self.add_item(self.prev_button())
            if page < total_pages - 1:
                self.add_item(self.next_button())

        def create_select_menu(self):
            start = self.page * ITEMS_PER_PAGE
            end = start + ITEMS_PER_PAGE
            options = [
                discord.SelectOption(
                    label=item["name"],
                    description=f"價格: {item['price']} + 稅: {item['tax']}, MP: {item['MP']}",
                    value=item["name"]
                )
                for item in shop_data[start:end]
            ]

            select_menu = Select(
                placeholder="✨ 請選擇想要購買的商品～",
                options=options,
                min_values=1,
                max_values=1
            )
            select_menu.callback = self.select_callback
            return select_menu

        def prev_button(self):
            prev_button = Button(label="⬅️ 上一頁", style=discord.ButtonStyle.primary)
            prev_button.callback = self.prev_callback
            return prev_button

        def next_button(self):
            next_button = Button(label="➡️ 下一頁", style=discord.ButtonStyle.primary)
            next_button.callback = self.next_callback
            return next_button

        async def select_callback(self, interaction: discord.Interaction):
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message("這不是你的選擇喔～", ephemeral=True)
                return

            selected_item_name = interaction.data["values"][0]
            selected_item = next((item for item in shop_data if item["name"] == selected_item_name), None)

            if selected_item:
                total_price = selected_item["price"] + selected_item["tax"]

                embed = discord.Embed(
                    title="🌸 購買確認",
                    description=(f"您選擇了 **{selected_item_name}**～\n"
                                 f"價格：{selected_item['price']} 幽靈幣\n"
                                 f"稅金：{selected_item['tax']} 幽靈幣\n"
                                 f"心理壓力 (MP)：{selected_item['MP']}\n"
                                 f"總價格：**{total_price}** 幽靈幣"),
                    color=0xFFB6C1
                )

                confirm_view = View(timeout=30)
                confirm_button = Button(label="✅ 確認購買", style=discord.ButtonStyle.success)
                cancel_button = Button(label="❌ 取消", style=discord.ButtonStyle.danger)

                async def confirm_callback(interaction: discord.Interaction):
                    if interaction.user.id != ctx.author.id:
                        await interaction.response.send_message("這不是你的選擇喔～", ephemeral=True)
                        return

                    user_balance = load_json('balance.json')
                    user_balance.setdefault(guild_id, {})
                    user_balance[guild_id].setdefault(user_id, 0)
                    current_balance = user_balance[guild_id][user_id]

                    if current_balance >= total_price:
                        user_balance[guild_id][user_id] -= total_price
                        save_json('balance.json', user_balance)

                        embed = discord.Embed(
                            title="🌸 商品處理",
                            description=f"您購買了 **{selected_item_name}**！\n請選擇：存入背包還是直接食用？",
                            color=0xFFB6C1
                        )

                        choice_view = View(timeout=30)
                        backpack_button = Button(label="🎒 存入背包", style=discord.ButtonStyle.primary)
                        use_button = Button(label="🍽️ 直接食用", style=discord.ButtonStyle.secondary)

                        async def backpack_callback(interaction: discord.Interaction):
                            if interaction.user.id != ctx.author.id:
                                await interaction.response.send_message("這不是你的選擇喔～", ephemeral=True)
                                return

                            user_data = load_yaml('config_user.yml')
                            user_data.setdefault(guild_id, {})
                            user_data[guild_id].setdefault(user_id, {"MP": 200, "backpack": []})

                            user_data[guild_id][user_id]["backpack"].append({
                                "name": selected_item["name"],
                                "price": selected_item["price"],
                                "tax": selected_item["tax"],
                                "MP": selected_item["MP"]
                            })

                            save_yaml('config_user.yml', user_data)

                            await interaction.response.edit_message(
                                content=f"✨ **{selected_item_name}** 已存入背包！",
                                embed=None, view=None
                            )

                        async def use_callback(interaction: discord.Interaction):
                            if interaction.user.id != ctx.author.id:
                                await interaction.response.send_message("這不是你的選擇喔～", ephemeral=True)
                                return

                            user_data = load_yaml('config_user.yml')
                            user_data.setdefault(guild_id, {})
                            user_data[guild_id].setdefault(user_id, {"MP": 200, "backpack": []})

                            user_data[guild_id][user_id]["MP"] = max(
                                0, user_data[guild_id][user_id]["MP"] - selected_item["MP"]
                            )

                            save_yaml('config_user.yml', user_data)

                            await interaction.response.edit_message(
                                content=f"🍽️ 你食用了 **{selected_item_name}**，心理壓力（MP）下降了 {selected_item['MP']} 點！",
                                embed=None, view=None
                            )

                        backpack_button.callback = backpack_callback
                        use_button.callback = use_callback
                        choice_view.add_item(backpack_button)
                        choice_view.add_item(use_button)

                        await interaction.response.edit_message(embed=embed, view=choice_view)
                    else:
                        await interaction.response.edit_message(
                            content="幽靈幣不足呢～要不要再努力賺一點？💸", embed=None, view=None
                        )

                async def cancel_callback(interaction: discord.Interaction):
                    if interaction.user.id != ctx.author.id:
                        await interaction.response.send_message("這不是你的選擇喔～", ephemeral=True)
                        return
                    await interaction.response.edit_message(
                        content="已取消購買呢～♪", embed=None, view=None
                    )

                confirm_button.callback = confirm_callback
                cancel_button.callback = cancel_callback
                confirm_view.add_item(confirm_button)
                confirm_view.add_item(cancel_button)

                await interaction.response.edit_message(embed=embed, view=confirm_view)

        async def prev_callback(self, interaction: discord.Interaction):
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message("這不是你的選擇喔～", ephemeral=True)
                return
            self.page -= 1
            self.clear_items()
            self.add_item(self.create_select_menu())
            if self.page > 0:
                self.add_item(self.prev_button())
            if self.page < total_pages - 1:
                self.add_item(self.next_button())
            embed = discord.Embed(
                title=f"🌸 商店 - 第 {self.page+1}/{total_pages} 頁",
                description="選擇想購買的商品吧～✨",
                color=0xFFB6C1
            )
            await interaction.response.edit_message(embed=embed, view=self)

        async def next_callback(self, interaction: discord.Interaction):
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message("這不是你的選擇喔～", ephemeral=True)
                return
            self.page += 1
            self.clear_items()
            self.add_item(self.create_select_menu())
            if self.page > 0:
                self.add_item(self.prev_button())
            if self.page < total_pages - 1:
                self.add_item(self.next_button())
            embed = discord.Embed(
                title=f"🌸 商店 - 第 {self.page+1}/{total_pages} 頁",
                description="選擇想購買的商品吧～✨",
                color=0xFFB6C1
            )
            await interaction.response.edit_message(embed=embed, view=self)

        async def on_timeout(self):
            for item in self.children:
                item.disabled = True
            await self.message.edit(content="商店已超時，請重新開啟！", embed=None, view=self)

    embed = discord.Embed(
        title=f"🌸 商店 - 第 {current_page+1}/{total_pages} 頁",
        description="選擇想購買的商品吧～✨",
        color=0xFFB6C1
    )
    view = ShopView(current_page)
    await ctx.respond(embed=embed, view=view, ephemeral=False)

@bot.slash_command(name="backpack", description="幽幽子帶你看看背包裏的小寶貝哦～")
async def backpack(ctx: discord.ApplicationContext):
    guild_id = str(ctx.guild.id)
    user_id = str(ctx.author.id)

    user_data = load_yaml("config_user.yml")
    user_data.setdefault(guild_id, {})
    user_data[guild_id].setdefault(user_id, {"MP": 200, "backpack": []})

    backpack_items = user_data[guild_id][user_id]["backpack"]

    if not backpack_items:
        await ctx.respond("哎呀～你的背包空空的，像櫻花瓣一樣輕呢！🌸", ephemeral=True)
        return

    item_counts = {}
    for item in backpack_items:
        item_name = item["name"]
        item_counts[item_name] = item_counts.get(item_name, 0) + 1

    options = [
        discord.SelectOption(
            label=item_name,
            description=f"數量: {count}",
            value=item_name
        )
        for item_name, count in item_counts.items()
    ]

    select = Select(
        placeholder="選一件小東西吧～",
        options=options,
        min_values=1,
        max_values=1
    )

    async def select_callback(interaction: discord.Interaction):
        if interaction.user.id != ctx.author.id:
            await interaction.response.send_message("嘻嘻，這可不是你的小背包哦～", ephemeral=True)
            return

        selected_item_name = select.values[0]
        item_data = next((item for item in shop_data if item["name"] == selected_item_name), None)

        if not item_data:
            await interaction.response.send_message("哎呀～幽幽子找不到這個東西的秘密呢…", ephemeral=True)
            return

        mp_value = item_data["MP"]

        embed = discord.Embed(
            title=f"幽幽子的背包小角落 - {selected_item_name}",
            description=f"這個小東西能讓你輕鬆 {mp_value} 點壓力哦～\n你想怎麼處理它呢？",
            color=discord.Color.from_rgb(255, 105, 180)
        )

        use_button = Button(label="享用它～", style=discord.ButtonStyle.success)
        donate_button = Button(label="送給幽幽子", style=discord.ButtonStyle.secondary)

        async def use_callback(interaction: discord.Interaction):
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message("這可不是你的選擇啦～", ephemeral=True)
                return

            confirm_button = Button(label="確定要用～", style=discord.ButtonStyle.success)
            cancel_button = Button(label="再想想", style=discord.ButtonStyle.danger)

            async def confirm_use(interaction: discord.Interaction):
                if interaction.user.id != ctx.author.id:
                    await interaction.response.send_message("嘻嘻，別搶幽幽子的點心哦～", ephemeral=True)
                    return

                user_data[guild_id][user_id]["MP"] = max(
                    0, user_data[guild_id][user_id]["MP"] - mp_value
                )
                for i, item in enumerate(user_data[guild_id][user_id]["backpack"]):
                    if item["name"] == selected_item_name:
                        user_data[guild_id][user_id]["backpack"].pop(i)
                        break
                save_yaml("config_user.yml", user_data)

                await interaction.response.edit_message(
                    content=(f"你享用了 **{selected_item_name}**，壓力像櫻花一樣飄走了 {mp_value} 點！\n"
                             f"現在的 MP：{user_data[guild_id][user_id]['MP']} 點，真是輕鬆呢～🌸"),
                    embed=None,
                    view=None
                )

            async def cancel_use(interaction: discord.Interaction):
                await interaction.response.edit_message(
                    content="好吧～這次就先留著它吧～", embed=None, view=None
                )

            confirm_button.callback = confirm_use
            cancel_button.callback = cancel_use

            confirm_view = View()
            confirm_view.add_item(confirm_button)
            confirm_view.add_item(cancel_button)

            await interaction.response.edit_message(
                content=f"真的要用 **{selected_item_name}** 嗎？幽幽子幫你再確認一下哦～",
                embed=None,
                view=confirm_view
            )

        async def donate_callback(interaction: discord.Interaction):
            if interaction.user.id != ctx.author.id:
                await interaction.response.send_message("這可不是你的禮物哦～", ephemeral=True)
                return

            if selected_item_name in ["香烟", "台灣啤酒"]:
                await interaction.response.edit_message(
                    content=f"哎呀～幽幽子才不要這種 **{selected_item_name}** 呢，拿回去吧！",
                    embed=None,
                    view=None
                )
                return

            confirm_button = Button(label="確定送出～", style=discord.ButtonStyle.success)
            cancel_button = Button(label="再想想", style=discord.ButtonStyle.danger)

            async def confirm_donate(interaction: discord.Interaction):
                if interaction.user.id != ctx.author.id:
                    await interaction.response.send_message("嘻嘻，這可不是你能送的啦～", ephemeral=True)
                    return

                for i, item in enumerate(user_data[guild_id][user_id]["backpack"]):
                    if item["name"] == selected_item_name:
                        user_data[guild_id][user_id]["backpack"].pop(i)
                        break
                save_yaml("config_user.yml", user_data)

                await interaction.response.edit_message(
                    content=f"你把 **{selected_item_name}** 送給了幽幽子，她開心地說：「謝謝你哦～❤」",
                    embed=None,
                    view=None
                )

            async def cancel_donate(interaction: discord.Interaction):
                await interaction.response.edit_message(
                    content="好吧～這次就先留著吧，幽幽子也不介意哦～", embed=None, view=None
                )

            confirm_button.callback = confirm_donate
            cancel_button.callback = cancel_donate

            confirm_view = View()
            confirm_view.add_item(confirm_button)
            confirm_view.add_item(cancel_button)

            await interaction.response.edit_message(
                content=f"真的要把 **{selected_item_name}** 送給幽幽子嗎？她可是很期待呢～🌸",
                embed=None,
                view=confirm_view
            )

        use_button.callback = use_callback
        donate_button.callback = donate_callback

        view = View()
        view.add_item(use_button)
        view.add_item(donate_button)

        await interaction.response.edit_message(embed=embed, view=view)

    select.callback = select_callback

    embed = discord.Embed(
        title="幽幽子的背包小天地",
        description="來看看你收集了哪些可愛的小東西吧～🌸",
        color=discord.Color.from_rgb(255, 105, 180)
    )
    embed.set_footer(text="幽幽子會一直陪著你的哦～")

    view = View()
    view.add_item(select)

    await ctx.respond(embed=embed, view=view, ephemeral=False)

@bot.slash_command(name="choose_job", description="選擇你的工作！")
async def choose_job(ctx: discord.ApplicationContext):
    guild_id = str(ctx.guild.id)
    user_id = str(ctx.user.id)

    if guild_id in user_data and user_id in user_data[guild_id]:
        current_job = user_data[guild_id][user_id].get("job")
        if current_job:
            embed = discord.Embed(
                title="職業選擇",
                description=f"你已經有職業了！你現在的是 **{current_job}**。",
                color=discord.Color.blue()
            )
            await ctx.respond(embed=embed, ephemeral=True)
            return

    if not jobs_data or not isinstance(jobs_data, dict):
        embed = discord.Embed(
            title="錯誤",
            description="職業數據尚未正確配置，請使用 **`/feedback`** 指令回報錯誤！",
            color=discord.Color.red()
        )
        await ctx.respond(embed=embed, ephemeral=True)
        return

    class JobSelect(discord.ui.Select):
        def __init__(self):
            it_count = sum(
                1 for u_id, u_info in user_data.get(guild_id, {}).items()
                if u_info.get("job") == "IT程序員"
            )

            options = []
            for job, data in jobs_data.items():
                if isinstance(data, dict) and "min" in data and "max" in data:
                    if job == "IT程序員" and it_count >= 2:
                        options.append(discord.SelectOption(
                            label=f"   {job}   ",
                            description=f"{data['min']}-{data['max']}幽靈幣 (已滿員)",
                            value=f"{job}_disabled",
                            emoji="❌"
                        ))
                    else:
                        options.append(discord.SelectOption(
                            label=f"   {job}   ",
                            description=f"{data['min']}-{data['max']}幽靈幣",
                            value=job
                        ))

            super().__init__(
                placeholder="選擇你的工作...",
                options=options,
                min_values=1,
                max_values=1,
            )

        async def callback(self, interaction: discord.Interaction):
            if interaction.user.id != ctx.user.id:
                await interaction.response.send_message("這不是你的選擇！", ephemeral=True)
                return
            
            chosen_job = self.values[0]
            
            if "_disabled" in chosen_job:
                await interaction.response.send_message("該職業已滿員，請選擇其他職業！", ephemeral=True)
                return
            
            if guild_id not in user_data:
                user_data[guild_id] = {}
                
            if user_id not in user_data[guild_id]:
                user_data[guild_id][user_id] = {}

            user_info = user_data[guild_id][user_id]
            work_cooldown = user_info.get("work_cooldown", None)
            user_info["job"] = chosen_job
            
            if work_cooldown is not None:
                user_info["work_cooldown"] = work_cooldown
            else:
                user_info["work_cooldown"] = None
            
            save_yaml("config_user.yml", user_data)

            for child in self.view.children:
                child.disabled = True
            embed = discord.Embed(
                title="職業選擇成功",
                description=f"你選擇了 **{chosen_job}** 作為你的工作！🎉",
                color=discord.Color.green()
            )
            await interaction.response.edit_message(embed=embed, view=self.view)

    class JobView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=60)
            self.add_item(JobSelect())

        async def on_timeout(self):
            for child in self.children:
                child.disabled = True
            embed = discord.Embed(
                title="選擇超時",
                description="選擇已超時，請重新使用指令！",
                color=discord.Color.orange()
            )
            await self.message.edit(embed=embed, view=self)

    view = JobView()
    embed = discord.Embed(
        title="選擇你的職業",
        description="請從下方選擇你的工作：",
        color=discord.Color.blurple()
    )
    message = await ctx.respond(embed=embed, view=view)
    view.message = await message.original_message()

@bot.slash_command(name="reset_job", description="重置職業")
async def reset_job(ctx):
    guild_id = str(ctx.guild.id)
    user_id = str(ctx.author.id)

    group_data = user_data.get(guild_id, {})
    user_info = group_data.get(user_id, {})
    current_job = user_info.get("job", "無職業")

    embed = discord.Embed(
        title="職業重置確認",
        description=f"你當前的職業是：`{current_job}`\n\n確定要放棄現有職業嗎？",
        color=discord.Color.orange()
    )
    embed.set_footer(text="請選擇 Yes 或 No")

    class ConfirmReset(discord.ui.View):
        def __init__(self):
            super().__init__()

        @discord.ui.button(label="Yes", style=discord.ButtonStyle.green)
        async def confirm(self, button: discord.ui.Button, interaction: discord.Interaction):
            if interaction.user != ctx.author:
                await interaction.response.send_message("這不是你的選擇！", ephemeral=True)
                return

            if guild_id in user_data and user_id in user_data[guild_id]:
                user_data[guild_id][user_id]["job"] = None
                save_yaml("config_user.yml", user_data)

            success_embed = discord.Embed(
                title="成功",
                description="你的職業已被清除！",
                color=discord.Color.green()
            )
            await interaction.response.edit_message(embed=success_embed, view=None)

        @discord.ui.button(label="No", style=discord.ButtonStyle.red)
        async def cancel(self, button: discord.ui.Button, interaction: discord.Interaction):
            if interaction.user != ctx.author:
                await interaction.response.send_message("這不是你的選擇！", ephemeral=True)
                return

            cancel_embed = discord.Embed(
                title="操作取消",
                description="你的職業未被清除。",
                color=discord.Color.red()
            )
            await interaction.response.edit_message(embed=cancel_embed, view=None)

    await ctx.respond(embed=embed, view=ConfirmReset())

@bot.slash_command(name="work", description="執行你的工作並賺取幽靈幣！")
async def work(interaction: discord.Interaction):
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False)

        user_data = load_yaml('config_user.yml') or {}
        user_balance = load_json('balance.json') or {}

        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)

        user_balance.setdefault(guild_id, {})
        user_info = user_data.setdefault(guild_id, {}).setdefault(user_id, {})

        if not user_info.get("job"):
            await interaction.followup.send(
                "你尚未選擇職業，請先使用 `/choose_job` 選擇你的職業！", ephemeral=True
            )
            return

        job_name = user_info["job"]

        if isinstance(jobs_data, list):
            jobs_dict = {job["name"]: job for job in jobs_data if "name" in job}
        else:
            jobs_dict = jobs_data

        if job_name == "賭徒":
            embed = discord.Embed(
                title="工作系統",
                description="你選擇了刺激的道路，工作？ 哼~ 那對於我來說太枯燥了，賭博才是工作的樂趣！",
                color=discord.Color.from_rgb(255, 0, 0)
            )
            await interaction.followup.send(embed=embed, ephemeral=False)
            return

        job_rewards = jobs_dict.get(job_name)
        if not job_rewards:
            await interaction.followup.send(
                f"無效的職業: {job_name}，請重新選擇！", ephemeral=True
            )
            return

        user_info.setdefault("MP", 0)

        if user_info["MP"] >= 200:
            await interaction.followup.send(
                "你的心理壓力已達到最大值！請休息一下再繼續工作。", ephemeral=True
            )
            return

        last_cooldown = user_info.get("work_cooldown")
        now = datetime.now()
        if last_cooldown and datetime.fromisoformat(last_cooldown) > now:
            remaining = datetime.fromisoformat(last_cooldown) - now
            minutes, seconds = divmod(remaining.total_seconds(), 60)
            embed = discord.Embed(
                title="冷卻中",
                description=f"你正在冷卻中，還需等待 {int(minutes)} 分鐘 {int(seconds)} 秒！",
                color=discord.Color.red()
            )
            embed.set_footer(text=f"職業: {job_name}")
            await interaction.followup.send(embed=embed, ephemeral=False)
            return

        reward = random.randint(job_rewards["min"], job_rewards["max"])

        user_balance[guild_id].setdefault(user_id, 0)
        user_balance[guild_id][user_id] += reward

        user_info["work_cooldown"] = (now + timedelta(seconds=WORK_COOLDOWN_SECONDS)).isoformat()
        user_info["MP"] += 10

        save_json("balance.json", user_balance)
        save_yaml("config_user.yml", user_data)

        embed = discord.Embed(
            title="工作成功！",
            description=(
                f"{interaction.user.mention} 作為 **{job_name}** "
                f"賺取了 **{reward} 幽靈幣**！🎉\n"
                f"當前心理壓力（MP）：{user_info['MP']}/200"
            ),
            color=discord.Color.green()
        )
        embed.set_footer(text=f"職業: {job_name}")

        await interaction.followup.send(embed=embed)

    except Exception as e:
        print(f"[ERROR] work 指令錯誤: {e}")
        if not interaction.response.is_done():
            await interaction.followup.send("執行工作時發生錯誤，請稍後再試。")

def convert_decimal_to_float(data):
    """遞歸將 Decimal 類型轉換為 float，並限制為兩位小數"""
    if isinstance(data, Decimal):
        return float(data.quantize(Decimal("0.00"), rounding=ROUND_DOWN))
    elif isinstance(data, dict):
        return {k: convert_decimal_to_float(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [convert_decimal_to_float(i) for i in data]
    return data

def convert_float_to_decimal(data):
    """遞歸將 float 或 str 類型轉換為 Decimal"""
    if isinstance(data, float) or isinstance(data, str):
        try:
            return Decimal(data)
        except:
            return data
    elif isinstance(data, dict):
        return {k: convert_float_to_decimal(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [convert_float_to_decimal(i) for i in data]
    return data

@bot.slash_command(name="pay", description="转账给其他用户")
async def pay(interaction: discord.Interaction, member: discord.Member, amount: str):
    try:
        await interaction.response.defer()

        user_balance = load_json("balance.json")
        user_balance = convert_float_to_decimal(user_balance)

        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)
        recipient_id = str(member.id)

        if guild_id not in user_balance:
            user_balance[guild_id] = {}

        if user_id == recipient_id:
            await interaction.followup.send("❌ 您不能转账给自己。", ephemeral=True)
            return
        if recipient_id == str(bot.user.id):
            await interaction.followup.send("❌ 您不能转账给机器人。", ephemeral=True)
            return

        try:
            amount = Decimal(amount)
            if amount <= 0:
                raise ValueError
            amount = amount.quantize(Decimal("0.00"), rounding=ROUND_DOWN)
        except:
            await interaction.followup.send("❌ 转账金额格式无效，请输入有效的正数金额（例如：100 或 100.00）。", ephemeral=True)
            return

        current_balance = Decimal(user_balance[guild_id].get(user_id, 0))
        if current_balance < amount:
            await interaction.followup.send("❌ 您的余额不足。", ephemeral=True)
            return

        user_balance[guild_id][user_id] = current_balance - amount
        user_balance[guild_id][recipient_id] = Decimal(user_balance[guild_id].get(recipient_id, 0)) + amount

        data_to_save = convert_decimal_to_float(user_balance)
        save_json("balance.json", data_to_save)

        embed = discord.Embed(
            title="💸 转账成功！",
            description=(f"**{interaction.user.mention}** 给 **{member.mention}** 转账了 **{amount:.2f} 幽靈幣**。\n\n"
                         "🎉 感谢您的使用！"),
            color=discord.Color.green()
        )
        embed.set_footer(text="如有問題 请在 Github issues 提交疑问")

        await interaction.followup.send(embed=embed)
        logging.info(f"转账成功: {interaction.user.id} -> {member.id} 金额: {amount:.2f}")

    except Exception as e:
        logging.error(f"执行 pay 命令时发生错误: {e}")
        await interaction.followup.send("❌ 执行命令时发生错误，请稍后再试。", ephemeral=True)

@bot.slash_command(name="addmoney", description="给用户增加幽靈幣（特定用户专用）")
async def addmoney(interaction: discord.Interaction, member: discord.Member, amount: int):
    if interaction.user.id != AUTHOR_ID:
        await interaction.response.send_message("❌ 您没有权限执行此操作。", ephemeral=True)
        return

    user_balance = load_json("balance.json")
    guild_id = str(interaction.guild.id)
    recipient_id = str(member.id)

    if guild_id not in user_balance:
        user_balance[guild_id] = {}

    if recipient_id == str(bot.user.id):
        await interaction.response.send_message("❌ 不能给机器人增加幽靈幣。", ephemeral=True)
        return

    if amount > 100000000000:
        await interaction.response.send_message("❌ 单次添加金额不能超过 **100,000,000,000 幽靈幣**。", ephemeral=True)
        return

    user_balance[guild_id][recipient_id] = user_balance[guild_id].get(recipient_id, 0) + amount
    save_json("balance.json", user_balance)

    embed = discord.Embed(
        title="✨ 幽靈幣增加成功",
        description=f"**{member.name}** 已成功增加了 **{amount} 幽靈幣**。",
        color=discord.Color.green()
    )
    embed.set_footer(text="感谢使用幽靈幣系统")

    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="removemoney", description="移除用户幽靈幣（特定用户专用）")
async def removemoney(interaction: discord.Interaction, member: discord.Member, amount: int):
    if interaction.user.id != AUTHOR_ID:
        await interaction.response.send_message("❌ 您没有权限执行此操作。", ephemeral=True)
        return

    user_balance = load_json("balance.json")
    guild_id = str(interaction.guild.id)
    recipient_id = str(member.id)

    if guild_id not in user_balance:
        user_balance[guild_id] = {}

    if recipient_id == str(bot.user.id):
        await interaction.response.send_message("❌ 不能从机器人移除幽靈幣。", ephemeral=True)
        return

    current_balance = user_balance[guild_id].get(recipient_id, 0)
    user_balance[guild_id][recipient_id] = max(current_balance - amount, 0)
    save_yaml("balance.yml", user_balance)

    embed = discord.Embed(
        title="✨ 幽靈幣移除成功",
        description=f"**{member.name}** 已成功移除 **{amount} 幽靈幣**。",
        color=discord.Color.red()
    )
    embed.set_footer(text="感谢使用幽靈幣系统")

    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="shutdown", description="讓幽幽子安靜地沉眠")
async def shutdown(interaction: discord.Interaction):
    YUYUKO_QUOTES = [
        "人世無常，魂魄永存～",
        "櫻花散落之時，便是幽幽子用餐之刻哦～",
        "冥界的風，總是這麼舒服呢～",
    ]
    if interaction.user.id == AUTHOR_ID:
        try:
            embed = discord.Embed(
                title="幽幽子即將沉眠",
                description="幽幽子要睡囉，晚安哦～",
                color=discord.Color.red()
            )
            embed.set_footer(text=random.choice(YUYUKO_QUOTES))
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            await send_global_webhook_message("🔴 **幽幽子飄然離去，魂魄歸於冥界...**", discord.Color.red())
            await asyncio.sleep(3)
            await bot.close()
        except Exception as e:
            logging.error(f"Shutdown command failed: {e}")
            await interaction.followup.send(f"哎呀，幽幽子好像被什麼纏住了，無法沉眠…錯誤：{e}", ephemeral=True)
    else:
        await interaction.response.send_message("嘻嘻，只有特別的人才能讓幽幽子安靜下來，你還不行哦～", ephemeral=True)

@bot.slash_command(name="restart", description="喚醒幽幽子重新起舞")
async def restart(interaction: discord.Interaction):
    YUYUKO_QUOTES = [
        "人世無常，魂魄永存～",
        "櫻花散落之時，便是幽幽子用餐之刻哦～",
        "冥界的風，總是這麼舒服呢～",
    ]
    if interaction.user.id == AUTHOR_ID:
        try:
            embed = discord.Embed(
                title="幽幽子即將甦醒",
                description="幽幽子要重新翩翩起舞啦，稍等片刻哦～",
                color=discord.Color.orange()
            )
            embed.set_footer(text=random.choice(YUYUKO_QUOTES))
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            await send_global_webhook_message("🔄 **幽幽子輕輕轉身，即將再度現身...**", discord.Color.orange())
            await asyncio.sleep(3)
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception as e:
            logging.error(f"Restart command failed: {e}")
            await interaction.followup.send(f"哎呀，幽幽子好像絆倒了…重啟失敗，錯誤：{e}", ephemeral=True)
    else:
        await interaction.response.send_message("只有靈魂的主人才能喚醒幽幽子，你還不行呢～", ephemeral=True)
        
@bot.slash_command(name="ban", description="封禁用户")
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    if not interaction.user.guild_permissions.ban_members:
        embed = discord.Embed(
            title="权限不足",
            description="⚠️ 您没有权限封禁成员。",
            color=discord.Color.yellow()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if not interaction.guild.me.guild_permissions.ban_members:
        embed = discord.Embed(
            title="权限不足",
            description="⚠️ 我没有封禁成员的权限，请检查我的角色是否拥有 **封禁成员** 的权限。",
            color=discord.Color.yellow()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if interaction.guild.me.top_role <= member.top_role:
        embed = discord.Embed(
            title="无法封禁",
            description=(
                "⚠️ 我的角色权限不足，无法封禁此用户。\n"
                "请将我的身分組移动到服务器的 **最高层级**，"
                "并确保我的身分組拥有 **封禁成员** 的权限。"
            ),
            color=discord.Color.yellow()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    await member.ban(reason=reason)
    embed = discord.Embed(
        title="封禁成功",
        description=f"✅ 用户 **{member}** 已被封禁。\n原因：{reason or '未提供原因'}",
        color=discord.Color.red()
    )
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="kick", description="踢出用户")
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    if not interaction.user.guild_permissions.administrator:
        embed = discord.Embed(
            title="权限不足",
            description="⚠️ 您没有管理员权限，无法踢出成员。",
            color=discord.Color.yellow()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if not interaction.guild.me.guild_permissions.kick_members:
        embed = discord.Embed(
            title="权限不足",
            description="⚠️ 我没有踢出成员的权限，请检查我的角色是否拥有 **踢出成员** 的权限。",
            color=discord.Color.yellow()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if interaction.guild.me.top_role <= member.top_role:
        embed = discord.Embed(
            title="无法踢出",
            description=(
                "⚠️ 我的角色权限不足，无法踢出此用户。\n"
                "请将我的角色移动到服务器的 **最高层级**，"
                "并确保我的角色拥有 **踢出成员** 的权限。"
            ),
            color=discord.Color.yellow()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    await member.kick(reason=reason)
    embed = discord.Embed(
        title="踢出成功",
        description=f"✅ 用户 **{member}** 已被踢出。\n原因：{reason or '未提供原因'}",
        color=discord.Color.red()
    )
    await interaction.response.send_message(embed=embed)

class GiveawayView(View):
    def __init__(self, guild_id, prize, duration, timeout=None):
        super().__init__(timeout=timeout)
        self.guild_id = guild_id
        self.prize = prize
        self.participants = set()
        self.duration = duration

    async def on_timeout(self):
        await self.end_giveaway()

    async def end_giveaway(self):
        if self.guild_id not in active_giveaways:
            return

        giveaway = active_giveaways.pop(self.guild_id)
        channel = bot.get_channel(giveaway["channel_id"])
        if not channel:
            return

        if not self.participants:
            await channel.send("😢 抽獎活動結束，沒有有效的參與者。")
            return

        winner = random.choice(list(self.participants))
        embed = discord.Embed(
            title="🎉 抽獎活動結束 🎉",
            description=(
                f"**獎品**: {self.prize}\n"
                f"**獲勝者**: {winner.mention}\n\n"
                "感謝所有參與者！"
            ),
            color=discord.Color.green()
        )
        await channel.send(embed=embed)

    @discord.ui.button(label="參加抽獎", style=discord.ButtonStyle.green)
    async def participate(self, button: Button, interaction: discord.Interaction):
        if interaction.user not in self.participants:
            self.participants.add(interaction.user)
            await interaction.response.send_message("✅ 你已成功參加抽獎！", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ 你已經參加過了！", ephemeral=True)

    @discord.ui.button(label="結束抽獎", style=discord.ButtonStyle.red, row=1)
    async def end_giveaway_button(self, button: Button, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 只有管理員可以結束抽獎活動。", ephemeral=True)
            return

        await self.end_giveaway()
        await interaction.response.send_message("🔔 抽獎活動已結束！", ephemeral=True)
        self.stop()

@bot.slash_command(name="start_giveaway", description="開始抽獎活動")
async def start_giveaway(interaction: discord.Interaction, duration: int, prize: str):
    """
    啟動抽獎活動
    :param duration: 抽獎持續時間（秒）
    :param prize: 獎品名稱
    """
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ 你需要管理員權限才能使用此指令。", ephemeral=True)
        return

    if interaction.guild.id in active_giveaways:
        await interaction.response.send_message("⚠️ 已經有正在進行的抽獎活動。", ephemeral=True)
        return

    embed = discord.Embed(
        title="🎉 抽獎活動開始了！ 🎉",
        description=(
            f"**獎品**: {prize}\n"
            f"**活動持續時間**: {duration} 秒\n\n"
            "點擊下方的按鈕參與抽獎！"
        ),
        color=discord.Color.gold()
    )
    embed.set_footer(text="祝你好運！")

    view = GiveawayView(interaction.guild.id, prize, duration, timeout=duration)

    await interaction.response.send_message(embed=embed, view=view)
    message = await interaction.followup.send("🔔 抽獎活動已經開始！參與者請點擊按鈕參加！")

    active_giveaways[interaction.guild.id] = {
        "message_id": message.id,
        "channel_id": interaction.channel_id,
        "prize": prize,
        "view": view
    }

@bot.slash_command(name="clear", description="清除指定数量的消息")
async def clear(interaction: discord.Interaction, amount: int):
    await interaction.response.defer(ephemeral=True)

    if not interaction.user.guild_permissions.administrator:
        embed = discord.Embed(
            title="⛔ 無權限操作",
            description="你沒有管理員權限，無法執行此操作。",
            color=0xFF0000
        )
        await interaction.followup.send(embed=embed)
        return

    if amount <= 0:
        embed = discord.Embed(
            title="⚠️ 無效數字",
            description="請輸入一個大於 0 的數字。",
            color=0xFFA500
        )
        await interaction.followup.send(embed=embed)
        return

    if amount > 100:
        embed = discord.Embed(
            title="⚠️ 超出限制",
            description="無法一次性刪除超過 100 條消息。",
            color=0xFFA500
        )
        await interaction.followup.send(embed=embed)
        return

    cutoff_date = datetime.now(tz=timezone.utc) - timedelta(days=14)

    try:
        deleted = await interaction.channel.purge(limit=amount, after=cutoff_date)
        if deleted:
            embed = discord.Embed(
                title="✅ 清理成功",
                description=f"已刪除 {len(deleted)} 條消息。",
                color=0x00FF00
            )
        else:
            embed = discord.Embed(
                title="⚠️ 無消息刪除",
                description="沒有消息被刪除，可能所有消息都超過了 14 天限制。",
                color=0xFFFF00
            )
        await interaction.followup.send(embed=embed)

    except discord.Forbidden:
        embed = discord.Embed(
            title="⛔ 權限錯誤",
            description="機器人缺少刪除消息的權限，請聯繫管理員進行配置。",
            color=0xFF0000
        )
        await interaction.followup.send(embed=embed)

    except discord.HTTPException as e:
        embed = discord.Embed(
            title="❌ 清理失敗",
            description=f"發生 API 錯誤：{e.text if hasattr(e, 'text') else str(e)}",
            color=0xFF0000
        )
        await interaction.followup.send(embed=embed)

    except Exception as e:
        embed = discord.Embed(
            title="❌ 清理失敗",
            description=f"發生未知錯誤：{str(e)}",
            color=0xFF0000
        )
        await interaction.followup.send(embed=embed)

@bot.slash_command(name="time", description="获取最后活动时间")
async def time_command(interaction: discord.Interaction):
    global last_activity_time
    current_time = time.time()
    idle_seconds = current_time - last_activity_time
    idle_minutes = idle_seconds / 60
    idle_hours = idle_seconds / 3600
    idle_days = idle_seconds / 86400

    embed = discord.Embed()

    if idle_days >= 1:
        embed.title = "最後一次活動時間"
        embed.description = f"機器人上次活動時間是 **{idle_days:.2f} 天前**。"
        embed.color = discord.Color.dark_blue()
    elif idle_hours >= 1:
        embed.title = "最後一次活動時間"
        embed.description = f"機器人上次活動時間是 **{idle_hours:.2f} 小時前**。"
        embed.color = discord.Color.orange()
    else:
        embed.title = "最後一次活動時間"
        embed.description = f"機器人上次活動時間是 **{idle_minutes:.2f} 分鐘前**。"
        embed.color = discord.Color.green()

    embed.set_footer(text="製作:'死亡協會'")

    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="ping", description="幽幽子為你測試與靈界通訊的延遲～")
async def ping(interaction: discord.Interaction):
    openai.api_base = API_URL
    openai.api_key = os.getenv('CHATANYWHERE_API')
    await interaction.response.defer()

    embed = discord.Embed(
        title="🌸 幽幽子的靈界通訊測試 🌸",
        description="幽幽子正在與靈界通訊，測試延遲中…請稍候～",
        color=discord.Color.from_rgb(255, 182, 193)
    )
    yuyuko_comments = [
        "靈魂的波動正在傳遞，稍等一下哦～",
        "嘻嘻，靈界的回應有時會慢一點呢～",
        "櫻花飄落的速度，比這通訊還快吧？"
    ]
    embed.set_footer(text=random.choice(yuyuko_comments))

    message = await interaction.followup.send(embed=embed)

    iterations = 3
    total_time = 0
    delays = []

    for i in range(iterations):
        start_time = time.time()
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a simple ping tester."},
                    {"role": "user", "content": "Ping!"}
                ],
                max_tokens=10
            )
        except Exception as e:
            embed = discord.Embed(
                title="🌸 哎呀，靈界通訊失敗了！🌸",
                description=f"幽幽子試圖與靈界通訊時，發生了一點小意外…\n錯誤：{e}",
                color=discord.Color.red()
            )
            embed.set_footer(text="下次再試試吧～")
            await message.edit(embed=embed)
            return

        end_time = time.time()
        delay = (end_time - start_time) * 1000
        delays.append(delay)
        total_time += delay

        if delay <= 500:
            embed_color = discord.Color.teal()
        elif 500 < delay <= 1000:
            embed_color = discord.Color.gold()
        else:
            embed_color = discord.Color.red()

        yuyuko_comments_progress = [
            f"第 {i + 1} 次通訊完成，靈魂的回應真快呢～",
            f"靈界第 {i + 1} 次回應，櫻花都忍不住飄落了～",
            f"第 {i + 1} 次通訊，靈魂的波動真美妙～"
        ]
        embed = discord.Embed(
            title="🌸 幽幽子的靈界通訊測試 🌸",
            description=(
                f"正在與靈界通訊… 第 {i + 1}/{iterations} 次\n\n"
                f"**本次延遲**: `{delay:.2f} 毫秒`\n"
                f"**平均延遲**: `{total_time / (i + 1):.2f} 毫秒`"
            ),
            color=embed_color
        )
        embed.set_footer(text=yuyuko_comments_progress[i])
        await message.edit(embed=embed)
        await asyncio.sleep(1)

    avg_delay = total_time / iterations
    if avg_delay <= 500:
        embed_color = discord.Color.teal()
        yuyuko_comments_final = [
            "靈界的通訊真順暢，靈魂的舞步都輕快起來了～",
            "這樣的延遲，連幽靈都會讚嘆哦～",
            "嘻嘻，靈界與你的靈魂完美共鳴了～"
        ]
    elif 500 < avg_delay <= 1000:
        embed_color = discord.Color.gold()
        yuyuko_comments_final = [
            "通訊有點慢呢，靈魂的波動需要更多練習哦～",
            "這樣的延遲，櫻花都等得有點不耐煩了～",
            "靈界的回應有點遲，可能是幽靈在偷懶吧？"
        ]
    else:
        embed_color = discord.Color.red()
        yuyuko_comments_final = [
            "哎呀，靈界的通訊太慢了，靈魂都快睡著了～",
            "這樣的延遲，連櫻花都忍不住嘆息了～",
            "靈界的回應太慢了，幽幽子都等得不耐煩了～"
        ]

    result_embed = discord.Embed(
        title="🌸 幽幽子的靈界通訊結果 🌸",
        description=(
            f"**WebSocket 延遲**: `{bot.latency * 1000:.2f} 毫秒`\n"
            f"**靈界通訊平均延遲**: `{avg_delay:.2f} 毫秒`\n\n"
            f"詳細結果：\n"
            f"第 1 次: `{delays[0]:.2f} 毫秒`\n"
            f"第 2 次: `{delays[1]:.2f} 毫秒`\n"
            f"第 3 次: `{delays[2]:.2f} 毫秒`"
        ),
        color=embed_color
    )
    result_embed.set_footer(text=random.choice(yuyuko_comments_final))

    await message.edit(embed=result_embed)

@bot.slash_command(name="server_info", description="幽幽子為你窺探群組的靈魂資訊～")
async def server_info(interaction: Interaction):
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message(
            "哎呀～這個地方沒有靈魂聚集，無法窺探哦。請在群組中使用此指令～",
            ephemeral=True
        )
        return

    guild_name = guild.name
    guild_id = guild.id
    member_count = guild.member_count
    bot_count = sum(1 for member in guild.members if member.bot) if guild.members else "未知"
    role_count = len(guild.roles)
    created_at = f"<t:{int(guild.created_at.timestamp())}:F>"
    guild_icon_url = guild.icon.url if guild.icon else None

    embed = discord.Embed(
        title="🌸 幽幽子窺探的群組靈魂 🌸",
        description=(
            f"我是西行寺幽幽子，亡魂之主，現在為你揭示群組「{guild_name}」的靈魂～\n"
            "讓我們來看看這片土地的命運吧…"
        ),
        color=discord.Color.from_rgb(255, 182, 193)
    )

    embed.add_field(name="群組之名", value=guild_name, inline=False)
    embed.add_field(name="靈魂聚集之地", value=guild_id, inline=False)
    embed.add_field(name="靈魂數量", value=f"{member_count} (機械之魂: {bot_count})", inline=True)
    embed.add_field(name="身份之數", value=role_count, inline=True)
    embed.add_field(name="此地誕生之日", value=created_at, inline=False)

    if guild_icon_url:
        embed.set_thumbnail(url=guild_icon_url)

    yuyuko_quotes = [
        "這片土地的靈魂真熱鬧…有沒有好吃的供品呀？",
        "櫻花下的群組，靈魂們的命運真是迷人～",
        "生與死的交界處，這裡的氣息讓我感到舒適呢。"
    ]
    embed.set_footer(text=random.choice(yuyuko_quotes))

    view = View(timeout=180)
    async def button_callback(interaction: Interaction):
        try:
            if guild_icon_url:
                yuyuko_comments = [
                    "這就是群組的靈魂之影～很美吧？",
                    f"嘻嘻，我抓到了「{guild_name}」的圖像啦！",
                    "這片土地的標誌，生與死的交界處真是迷人呢～"
                ]
                await interaction.response.send_message(
                    f"{guild_icon_url}\n\n{random.choice(yuyuko_comments)}",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "哎呀～這個群組沒有靈魂之影可看哦。",
                    ephemeral=True
                )
        except Exception as e:
            print(f"按鈕互動錯誤: {e}")
            await interaction.response.send_message(
                "哎呀，發生了一點小意外…稍後再試試吧～",
                ephemeral=True
            )

    button = Button(
        label="點擊獲取群組圖貼",
        style=discord.ButtonStyle.primary,
        emoji="🖼️"
    )
    button.callback = button_callback
    view.add_item(button)

    await interaction.response.send_message(embed=embed, view=view)

@bot.slash_command(name="user_info", description="幽幽子為你窺探用戶的靈魂資訊～")
async def userinfo(ctx: discord.ApplicationContext, user: discord.Member = None):
    user = user or ctx.author

    guild_id = str(ctx.guild.id) if ctx.guild else "DM"
    user_id = str(user.id)

    guild_config = user_data.get(guild_id, {})
    user_config = guild_config.get(user_id, {})

    work_cooldown = user_config.get('work_cooldown', '未工作')
    job = user_config.get('job', '無職業')
    mp = user_config.get('MP', 0)

    embed = discord.Embed(
        title="🌸 幽幽子窺探的靈魂資訊 🌸",
        description=(
            f"我是西行寺幽幽子，亡魂之主，現在為你揭示 {user.mention} 的靈魂～\n"
            "讓我們來看看這位旅人的命運吧…"
        ),
        color=discord.Color.from_rgb(255, 182, 193)
    )
    embed.set_thumbnail(url=user.display_avatar.url)

    embed.add_field(name="名稱", value=f"{user.name}#{user.discriminator}", inline=True)
    embed.add_field(name="靈魂編號", value=user.id, inline=True)
    embed.add_field(
        name="靈魂誕生之日",
        value=user.created_at.replace(tzinfo=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        inline=True
    )

    if isinstance(user, discord.Member):
        embed.add_field(name="伺服器化名", value=user.nick or "無", inline=True)
        embed.add_field(
            name="加入此地之日",
            value=user.joined_at.replace(tzinfo=timezone.utc).strftime("%Y-%m-%d %H:%M:%S") if user.joined_at else "無法窺見",
            inline=True
        )
        embed.add_field(name="最高身份", value=user.top_role.mention if user.top_role else "無", inline=True)
        embed.add_field(name="是機械之魂？", value="是" if user.bot else "否", inline=True)
    else:
        embed.add_field(name="伺服器化名", value="此魂不在當前之地", inline=True)

    work_embed = discord.Embed(
        title="💼 幽幽子觀察到的命運軌跡",
        color=discord.Color.from_rgb(135, 206, 250)
    )
    work_embed.add_field(
        name="命運狀態",
        value=(
            f"💼 職業: {job}\n"
            f"⏳ 冷卻之時: {work_cooldown}\n"
            f"📊 靈魂壓力 (MP): {mp}/200"
        ),
        inline=False
    )

    yuyuko_quotes = [
        "靈魂的軌跡真是美麗啊…有沒有好吃的供品呢？",
        "生與死不過一線之隔，珍惜當下吧～",
        "這靈魂的顏色…嗯，適合配一朵櫻花！"
    ]
    embed.set_footer(text=random.choice(yuyuko_quotes))

    view = discord.ui.View(timeout=180)
    async def button_callback(interaction: discord.Interaction):
        yuyuko_comments = [
            f"這就是 {user.name} 的靈魂之影～很美吧？",
            f"嘻嘻，{user.name} 的頭像被我抓到啦！",
            f"這是 {user.name} 的模樣，生與死的交界處真是迷人呢～"
        ]
        await interaction.response.send_message(
            f"{user.display_avatar.url}\n\n{random.choice(yuyuko_comments)}",
            ephemeral=True
        )

    button = discord.ui.Button(
        label="獲取頭像",
        style=discord.ButtonStyle.primary,
        emoji="🖼️"
    )
    button.callback = button_callback
    view.add_item(button)

    await ctx.respond(embeds=[embed, work_embed], view=view)

@bot.slash_command(name="feedback", description="幽幽子聆聽你的靈魂之聲～提交反饋吧！")
async def feedback(ctx: discord.ApplicationContext, description: str = None):
    """Command to collect user feedback with category buttons."""
    view = View(timeout=None)

    async def handle_feedback(interaction: discord.Interaction, category: str):
        feedback_channel_id = 1308316531444158525
        feedback_channel = bot.get_channel(feedback_channel_id)

        if feedback_channel is None:
            await interaction.response.send_message(
                "哎呀～靈魂的回音無法傳達，反饋之地尚未設置好呢…請聯繫作者哦～",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🌸 幽幽子收到的靈魂之聲 🌸",
            description=(
                f"**分類:** {category}\n"
                f"**靈魂:** {interaction.user.mention}\n"
                f"**回音:** {description if description else '未提供描述'}"
            ),
            color=discord.Color.from_rgb(255, 182, 193)
        )
        embed.timestamp = discord.utils.utcnow()

        await feedback_channel.send(embed=embed)
        yuyuko_thanks = [
            "感謝你的靈魂之聲，我會好好聆聽的～",
            "嘻嘻，你的回音已傳到我的耳邊，謝謝你哦～",
            "靈魂的低語真美妙，感謝你的反饋！"
        ]
        await interaction.response.send_message(
            random.choice(yuyuko_thanks),
            ephemeral=True
        )

    async def command_error_callback(interaction: discord.Interaction):
        await handle_feedback(interaction, "指令錯誤或無回應")

    button1 = Button(label="指令錯誤或無回應", style=discord.ButtonStyle.primary)
    button1.callback = command_error_callback
    view.add_item(button1)

    async def message_issue_callback(interaction: discord.Interaction):
        await handle_feedback(interaction, "機器人訊息問題")

    button2 = Button(label="機器人訊息問題", style=discord.ButtonStyle.primary)
    button2.callback = message_issue_callback
    view.add_item(button2)

    async def minigame_error_callback(interaction: discord.Interaction):
        await handle_feedback(interaction, "迷你遊戲系統錯誤")

    button3 = Button(label="迷你遊戲系統錯誤", style=discord.ButtonStyle.primary)
    button3.callback = minigame_error_callback
    view.add_item(button3)

    async def other_issue_callback(interaction: discord.Interaction):
        await handle_feedback(interaction, "其他問題")

    button4 = Button(label="其他問題", style=discord.ButtonStyle.primary)
    button4.callback = other_issue_callback
    view.add_item(button4)

    if description:
        await ctx.respond(
            f"你的靈魂之聲我聽到了～「{description}」\n請選擇以下類別，讓我更好地理解你的心意吧：",
            view=view,
            ephemeral=True
        )
    else:
        await ctx.respond(
            "幽幽子在此聆聽你的心聲～請選擇以下類別，並補充具體描述哦：",
            view=view,
            ephemeral=True
        )

@bot.slash_command(name="timeout", description="禁言指定的使用者（以分鐘為單位）")
async def timeout(interaction: discord.Interaction, member: discord.Member, duration: int):
    if interaction.user.guild_permissions.moderate_members:
        await interaction.response.defer(ephemeral=True)

        bot_member = interaction.guild.me
        if not bot_member.guild_permissions.moderate_members:
            embed = discord.Embed(
                title="❌ 操作失敗",
                description="機器人缺少禁言權限，請確認角色權限設置。",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if member.top_role >= bot_member.top_role:
            embed = discord.Embed(
                title="❌ 操作失敗",
                description=f"無法禁言 {member.mention}，因為他們的角色高於或等於機器人。",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        try:
            mute_time = datetime.utcnow() + timedelta(minutes=duration)
            await member.timeout(mute_time, reason=f"Timeout by {interaction.user} for {duration} minutes")
            
            embed = discord.Embed(
                title="⛔ 成員禁言",
                description=f"{member.mention} 已被禁言 **{duration} 分鐘**。",
                color=discord.Color.dark_red()
            )
            embed.set_footer(text="請遵守伺服器規則")
            await interaction.followup.send(embed=embed, ephemeral=False)
        except discord.Forbidden:
            embed = discord.Embed(
                title="❌ 無法禁言",
                description=f"權限不足，無法禁言 {member.mention} 或回應訊息。",
                color=discord.Color.red()
            )
            try:
                await interaction.followup.send(embed=embed, ephemeral=False)
            except discord.Forbidden:
                print("無法回應權限不足的錯誤訊息，請檢查機器人權限。")
        except discord.HTTPException as e:
            embed = discord.Embed(
                title="❌ 禁言失敗",
                description=f"操作失敗：{e}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        embed = discord.Embed(
            title="⚠️ 權限不足",
            description="你沒有權限使用這個指令。",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.slash_command(name="untimeout", description="解除禁言狀態")
async def untimeout(interaction: discord.Interaction, member: discord.Member):
    if interaction.user.guild_permissions.moderate_members:
        try:
            await member.timeout(None)
            embed = discord.Embed(
                title="🔓 成員解除禁言",
                description=f"{member.mention} 的禁言狀態已被解除。",
                color=discord.Color.green()
            )
            embed.set_footer(text="希望成員能遵守規則")
            await interaction.response.send_message(embed=embed)
        except discord.Forbidden:
            embed = discord.Embed(
                title="❌ 無法解除禁言",
                description=f"權限不足，無法解除 {member.mention} 的禁言。",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=False)
        except discord.HTTPException as e:
            embed = discord.Embed(
                title="❌ 解除禁言失敗",
                description=f"操作失敗：{e}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        embed = discord.Embed(
            title="⚠️ 權限不足",
            description="你沒有權限使用這個指令。",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.slash_command(name="fish", description="進行一次釣魚")
async def fish(ctx: ApplicationContext):
    try:
        with open("config.json", "r", encoding="utf-8") as config_file:
            fish_data = json.load(config_file)["fish"]
    except FileNotFoundError:
        await ctx.respond("配置文件 `config.json` 未找到！", ephemeral=True)
        return
    except (KeyError, json.JSONDecodeError):
        await ctx.respond("配置文件 `config.json` 格式錯誤！", ephemeral=True)
        return

    user_id = str(ctx.user.id)
    guild_id = str(ctx.guild.id)
    current_rod = "魚竿"

    def generate_fish_data():
        selected_fish = random.choice(fish_data)
        fish_name = selected_fish["name"]
        fish_rarity = selected_fish["rarity"]
        fish_size = round(random.uniform(float(selected_fish["min_size"]), float(selected_fish["max_size"])), 2)
        return {"name": fish_name, "rarity": fish_rarity, "size": fish_size}

    latest_fish_data = generate_fish_data()

    rarity_colors = {
        "common": discord.Color.green(),
        "uncommon": discord.Color.blue(),
        "rare": discord.Color.purple(),
        "legendary": discord.Color.orange(),
        "deify": discord.Color.gold(),
        "unknown": discord.Color.dark_gray(),
    }

    def create_fishing_embed(fish_data):
        embed = discord.Embed(
            title="釣魚結果！",
            description=f"使用魚竿：{current_rod}",
            color=rarity_colors.get(fish_data["rarity"], discord.Color.light_gray())
        )
        embed.add_field(name="捕獲魚種", value=fish_data["name"], inline=False)
        embed.add_field(name="稀有度", value=fish_data["rarity"].capitalize(), inline=True)
        embed.add_field(name="重量", value=f"{fish_data['size']} 公斤", inline=True)
        embed.set_footer(text="釣魚協會祝您 天天釣到大魚\n祝你每次都空軍")
        return embed

    class FishingButtons(discord.ui.View):
        def __init__(self, author_id, fish_data):
            super().__init__(timeout=180)
            self.author_id = author_id
            self.latest_fish_data = fish_data

        async def interaction_check(self, interaction: Interaction):
            if interaction.user.id != self.author_id:
                await interaction.response.send_message("這不是你的按鈕哦！", ephemeral=True)
                return False
            return True

        async def on_timeout(self):
            try:
                await ctx.edit(
                    content="釣魚操作已超時，請重新開始！",
                    embed=None,
                    view=None
                )
            except discord.errors.NotFound:
                pass

        @discord.ui.button(label="重複釣魚", style=discord.ButtonStyle.green)
        async def repeat_fishing(self, button: discord.ui.Button, interaction: Interaction):
            try:
                button.disabled = True
                button.label = "釣魚中..."
                await interaction.response.edit_message(view=self)

                await asyncio.sleep(2)
                self.latest_fish_data = generate_fish_data()
                new_embed = create_fishing_embed(self.latest_fish_data)

                new_view = FishingButtons(self.author_id, self.latest_fish_data)
                await interaction.edit_original_response(embed=new_embed, view=new_view)
            except discord.errors.NotFound:
                await interaction.followup.send("交互已失效，請重新開始釣魚！", ephemeral=True)
            except discord.errors.HTTPException as e:
                await interaction.followup.send(f"釣魚失敗，請稍後重試！(錯誤: {e})", ephemeral=True)

        @discord.ui.button(label="保存漁獲", style=discord.ButtonStyle.blurple)
        async def save_fish(self, button: discord.ui.Button, interaction: Interaction):
            try:
                button.disabled = True
                button.label = "保存中..."
                await interaction.response.edit_message(view=self)

                async with file_lock:
                    try:
                        with open("fishiback.yml", "r", encoding="utf-8") as fishiback_file:
                            fishiback_data = yaml.safe_load(fishiback_file) or {}
                    except (FileNotFoundError, yaml.YAMLError):
                        fishiback_data = {}

                    fishiback_data.setdefault(user_id, {}).setdefault(guild_id, {"fishes": []})
                    fishiback_data[user_id][guild_id]["fishes"].append({
                        "name": self.latest_fish_data["name"],
                        "rarity": self.latest_fish_data["rarity"],
                        "size": self.latest_fish_data["size"],
                        "rod": current_rod
                    })

                    with open("fishiback.yml", "w", encoding="utf-8") as fishiback_file:
                        yaml.safe_dump(fishiback_data, fishiback_file, allow_unicode=True)

                button.label = "已保存漁獲"
                self.remove_item(button)
                await interaction.edit_original_response(view=self)
            except discord.errors.NotFound:
                await interaction.followup.send("交互已失效，無法保存漁獲！", ephemeral=True)
            except discord.errors.HTTPException as e:
                await interaction.followup.send(f"保存漁獲失敗，請稍後重試！(錯誤: {e})", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"保存漁獲時發生錯誤：{e}", ephemeral=True)

    embed = create_fishing_embed(latest_fish_data)
    await ctx.respond(embed=embed, view=FishingButtons(ctx.user.id, latest_fish_data))

def load_fish_data():
    if not os.path.exists('fishiback.yml'):
        with open('fishiback.yml', 'w', encoding='utf-8') as file:
            yaml.dump({}, file)

    with open('fishiback.yml', 'r', encoding='utf-8') as file:
        fishing_data = yaml.safe_load(file)

    if fishing_data is None:
        fishing_data = {}

    return fishing_data

def calculate_fish_price(fish):
    rarity_prices = {
        "common": (100, 10),
        "uncommon": (350, 15),
        "rare": (7400, 50),
        "legendary": (450000, 100),
        "deify": (3000000, 500),
        "unknown": (100000000, 1000)
    }
    try:
        base_price, weight_multiplier = rarity_prices.get(fish["rarity"], (0, 0))
        size = float(fish["size"])
        return int(base_price + size * weight_multiplier)
    except (KeyError, ValueError, TypeError):
        return 0

@bot.slash_command(name="fish_shop", description="釣魚商店")
@track_balance_json
async def fish_shop(ctx: discord.ApplicationContext):
    user_id = str(ctx.user.id)
    guild_id = str(ctx.guild.id)

    await ctx.defer()

    async with file_lock:
        try:
            with open("fishiback.yml", "r", encoding="utf-8") as fishiback_file:
                fishiback_data = yaml.safe_load(fishiback_file) or {}
        except FileNotFoundError:
            fishiback_data = {}

    async with file_lock:
        try:
            with open("balance.json", "r", encoding="utf-8") as balance_file:
                balance_data = json.load(balance_file) or {}
        except (FileNotFoundError, json.JSONDecodeError):
            balance_data = {}

    user_fishes = fishiback_data.get(user_id, {}).get(guild_id, {}).get("fishes", [])
    user_balance = balance_data.get(guild_id, {}).get(user_id, 0)

    class FishShopView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=180)
            self.original_user_id = ctx.user.id

        @discord.ui.button(label="前往出售漁獲", style=discord.ButtonStyle.primary)
        async def go_to_sell(self, button: discord.ui.Button, interaction: discord.Interaction):
            if interaction.user.id != self.original_user_id:
                await interaction.response.send_message("這不是你的商店，無法操作！", ephemeral=True)
                return

            if not user_fishes:
                embed = discord.Embed(
                    title="釣魚商店通知",
                    description="您目前沒有漁獲可以販售！",
                    color=discord.Color.red()
                )
                embed.set_footer(text="請繼續努力釣魚吧！")
                await interaction.response.edit_message(embed=embed, view=None)
                return

            sell_view = FishSellView(self.original_user_id)
            embed = sell_view.get_updated_embed()
            await interaction.response.edit_message(embed=embed, view=sell_view)

        async def on_timeout(self):
            try:
                await ctx.edit(content="商店已超時，請重新開啟。", embed=None, view=None)
            except discord.errors.NotFound:
                pass

    class FishSellView(discord.ui.View):
        def __init__(self, original_user_id, page=0):
            super().__init__(timeout=180)
            self.original_user_id = original_user_id
            self.page = page
            self.items_per_page = 25
            self.update_options()

        def update_options(self):
            self.clear_items()
            if not user_fishes:
                self.add_item(discord.ui.Button(label="目前沒有漁獲可販售", style=discord.ButtonStyle.grey, disabled=True))
                return

            total_pages = (len(user_fishes) + self.items_per_page - 1) // self.items_per_page
            start_idx = self.page * self.items_per_page
            end_idx = min((self.page + 1) * self.items_per_page, len(user_fishes))
            current_fishes = user_fishes[start_idx:end_idx]

            select_menu = discord.ui.Select(
                placeholder="選擇您要販售的漁獲",
                options=[
                    discord.SelectOption(
                        label=f"{fish['name']} ({fish['rarity'].capitalize()})",
                        description=f"重量: {fish['size']} 公斤 | 預計販售: {calculate_fish_price(fish)} 幽靈幣",
                        value=str(start_idx + index)
                    ) for index, fish in enumerate(current_fishes)
                ]
            )

            async def select_fish_callback(interaction: discord.Interaction):
                if interaction.user.id != self.original_user_id:
                    await interaction.response.send_message("這不是你的商店，無法操作！", ephemeral=True)
                    return

                selected_index = int(select_menu.values[0])
                selected_fish = user_fishes[selected_index]
                price = calculate_fish_price(selected_fish)

                rarity_colors = {
                    "common": discord.Color.green(),
                    "uncommon": discord.Color.blue(),
                    "rare": discord.Color.purple(),
                    "legendary": discord.Color.orange(),
                    "deify": discord.Color.gold(),
                    "unknown": discord.Color.light_grey()
                }

                embed = discord.Embed(
                    title=f"選擇的漁獲: {selected_fish['name']}",
                    color=rarity_colors.get(selected_fish["rarity"], discord.Color.default())
                )
                embed.add_field(name="名稱", value=selected_fish["name"], inline=False)
                embed.add_field(name="重量", value=f"{selected_fish['size']} 公斤", inline=False)
                embed.add_field(name="等級", value=selected_fish["rarity"].capitalize(), inline=False)
                embed.add_field(name="預計販售價格", value=f"{price} 幽靈幣", inline=False)
                embed.add_field(name="操作", value="請選擇是否售出此漁獲。", inline=False)

                sell_confirm_view = ConfirmSellView(selected_index, self.original_user_id)
                await interaction.response.edit_message(embed=embed, view=sell_confirm_view)

            select_menu.callback = select_fish_callback
            self.add_item(select_menu)

            if self.page > 0:
                prev_button = discord.ui.Button(label="上一頁", style=discord.ButtonStyle.grey)
                async def prev_callback(interaction: discord.Interaction):
                    if interaction.user.id != self.original_user_id:
                        await interaction.response.send_message("這不是你的商店，無法操作！", ephemeral=True)
                        return
                    new_view = FishSellView(self.original_user_id, self.page - 1)
                    embed = new_view.get_updated_embed()
                    await interaction.response.edit_message(embed=embed, view=new_view)
                prev_button.callback = prev_callback
                self.add_item(prev_button)

            if end_idx < len(user_fishes):
                next_button = discord.ui.Button(label="下一頁", style=discord.ButtonStyle.grey)
                async def next_callback(interaction: discord.Interaction):
                    if interaction.user.id != self.original_user_id:
                        await interaction.response.send_message("這不是你的商店，無法操作！", ephemeral=True)
                        return
                    new_view = FishSellView(self.original_user_id, self.page + 1)
                    embed = new_view.get_updated_embed()
                    await interaction.response.edit_message(embed=embed, view=new_view)
                next_button.callback = next_callback
                self.add_item(next_button)

        def get_updated_embed(self):
            embed = discord.Embed(
                title="選擇漁獲進行販售",
                description="點擊下方菜單選擇漁獲進行操作。",
                color=discord.Color.blue()
            )
            if not user_fishes:
                embed.description = "目前沒有漁獲可以販售！"
            else:
                total_pages = (len(user_fishes) + self.items_per_page - 1) // self.items_per_page
                embed.set_footer(text=f"共 {len(user_fishes)} 條漁獲 | 第 {self.page + 1}/{total_pages} 頁")
            return embed

        async def on_timeout(self):
            try:
                await ctx.edit(content="販售介面已超時，請重新開啟。", embed=None, view=None)
            except discord.errors.NotFound:
                pass

    class ConfirmSellView(discord.ui.View):
        def __init__(self, fish_index, original_user_id):
            super().__init__(timeout=180)
            self.fish_index = fish_index
            self.original_user_id = original_user_id

        @discord.ui.button(label="確認售出", style=discord.ButtonStyle.green)
        async def confirm_sell(self, button: discord.ui.Button, interaction: discord.Interaction):
            if interaction.user.id != self.original_user_id:
                await interaction.response.send_message("這不是你的商店，無法操作！", ephemeral=True)
                return

            nonlocal fishiback_data, balance_data, user_fishes
            fish = user_fishes[self.fish_index]
            price = calculate_fish_price(fish)

            if price == 0:
                await interaction.response.edit_message(
                    content="漁獲資料錯誤，無法售出！", embed=None, view=None
                )
                return

            balance_data.setdefault(guild_id, {}).setdefault(user_id, 0)
            balance_data[guild_id][user_id] += price
            user_fishes.pop(self.fish_index)

            if user_id not in fishiback_data:
                fishiback_data[user_id] = {}
            if guild_id not in fishiback_data[user_id]:
                fishiback_data[user_id][guild_id] = {}
            fishiback_data[user_id][guild_id]["fishes"] = user_fishes

            async with file_lock:
                with open("fishiback.yml", "w", encoding="utf-8") as fishiback_file:
                    yaml.safe_dump(fishiback_data, fishiback_file, allow_unicode=True)
            async with file_lock:
                with open("balance.json", "w", encoding="utf-8") as balance_file:
                    json.dump(balance_data, balance_file, ensure_ascii=False, indent=4)

            if not user_fishes:
                await interaction.response.edit_message(
                    content=f"成功售出 {fish['name']}，獲得幽靈幣 {price}！目前已無漁獲可販售。",
                    embed=None, view=None
                )
                return

            sell_view = FishSellView(self.original_user_id, 0)
            embed = sell_view.get_updated_embed()
            await interaction.response.edit_message(
                content=f"成功售出 {fish['name']}，獲得幽靈幣 {price}！",
                embed=embed, view=sell_view
            )

        @discord.ui.button(label="取消", style=discord.ButtonStyle.red)
        async def cancel_sell(self, button: discord.ui.Button, interaction: discord.Interaction):
            if interaction.user.id != self.original_user_id:
                await interaction.response.send_message("這不是你的商店，無法操作！", ephemeral=True)
                return

            sell_view = FishSellView(self.original_user_id, 0)
            embed = sell_view.get_updated_embed()
            await interaction.response.edit_message(
                content="已取消販售，請選擇其他漁獲。",
                embed=embed, view=sell_view
            )

        async def on_timeout(self):
            try:
                await ctx.edit(content="確認介面已超時，請重新開啟。", embed=None, view=None)
            except discord.errors.NotFound:
                pass

    welcome_embed = discord.Embed(
        title="歡迎來到漁獲商店",
        description="在這裡您可以販售釣得的漁獲，換取幽靈幣！",
        color=discord.Color.blue()
    )
    welcome_view = FishShopView()

    await ctx.edit(embed=welcome_embed, view=welcome_view)

@bot.slash_command(name="fish_back", description="查看你的漁獲")
async def fish_back(interaction: discord.Interaction):
    fishing_data = load_fish_data()

    user_id = str(interaction.user.id)
    guild_id = str(interaction.guild.id)

    if user_id in fishing_data:
        if guild_id in fishing_data[user_id]:
            user_fishes = fishing_data[user_id][guild_id].get('fishes', [])

            if user_fishes:
                fish_list = "\n".join(
                    [f"**{fish['name']}** - {fish['rarity']} ({fish['size']} 公斤)" for fish in user_fishes]
                )

                try:
                    await interaction.response.defer()
                    await asyncio.sleep(2)

                    embed = discord.Embed(
                        title="🎣 你的漁獲列表",
                        description=fish_list,
                        color=discord.Color.blue()
                    )
                    embed.set_footer(text="數據提供為釣魚協會")

                    await interaction.followup.send(embed=embed)
                except discord.errors.NotFound:
                    await interaction.channel.send(
                        f"{interaction.user.mention} ❌ 你的查詢超時，請重新使用 `/fish_back` 查看漁獲！"
                    )
            else:
                await interaction.response.send_message("❌ 你還沒有捕到任何魚！", ephemeral=True)
        else:
            await interaction.response.send_message("❌ 你還沒有捕到任何魚！", ephemeral=True)
    else:
        await interaction.response.send_message("❌ 你還沒有捕到任何魚！", ephemeral=True)

@bot.slash_command(name="draw_lots", description="查看御神籤功能的最新公告")
async def draw_lots_command(interaction: discord.Interaction):
    user_name = interaction.user.display_name

    embed = discord.Embed(
        title="📢 御神籤功能停用公告 📢",
        description=(
            f"很抱歉，**{user_name}**，\n"
            "在今日，我們 Discord Bot 幽幽子的作者，也就是 Miya253，停用在幽幽子上的御神籤功能。\n\n"
            "如果您有抽籤需求，請使用以下鏈接邀請 **博麗靈夢**：\n"
            "[點擊此訊息邀請 博麗靈夢](https://discord.com/oauth2/authorize?client_id=1352316233772437630&permissions=8&integration_type=0&scope=bot)\n\n"
            "以上，很抱歉未能為用戶們提供最好的抽籤體驗。"
        ),
        color=discord.Color.red()
    )
    embed.set_footer(text="感謝您的理解與支持！")

    await interaction.response.send_message(embed=embed, ephemeral=False)

@bot.slash_command(name="quiz", description="幽幽子邀你來場問答挑戰哦～")
async def quiz(ctx: ApplicationContext):
    quiz_data = load_yaml("quiz.yml", default={"questions": []})

    if not quiz_data["questions"]:
        return await ctx.respond("❌ 哎呀，題庫空空的，就像幽靈肚子一樣！")

    question_data = random.choice(quiz_data["questions"])
    question = question_data["question"]
    correct_answer = question_data["correct"]
    incorrect_answers = question_data["incorrect"]

    if len(incorrect_answers) != 3:
        return await ctx.respond("❌ 嗯？題目好像少了點什麼，幽幽子數數要三個錯的才對嘛！")

    options = [correct_answer] + incorrect_answers
    random.shuffle(options)

    embed = discord.Embed(
        title="🪭 幽幽子的問答時間～",
        description=f"「{question}」\n嘻嘻，這可不好猜呢～快選一個吧！",
        color=discord.Color.from_rgb(255, 182, 193)
    )
    embed.set_footer(text="幽靈的謎題只有30秒哦～")

    class QuizView(discord.ui.View):
        def __init__(self, interaction: Interaction):
            super().__init__(timeout=30)
            self.interaction = interaction
            self.answered = False
            for option in options:
                self.add_item(QuizButton(option))

        async def on_timeout(self):
            if self.answered:
                return
            embed.color = discord.Color.dark_grey()
            embed.description = f"{question}\n\n⏳ 「時間到了呢～」幽幽子飄走了，正確答案是 `{correct_answer}`！"
            for child in self.children:
                child.disabled = True
            await self.interaction.edit_original_response(embed=embed, view=self)

    class QuizButton(discord.ui.Button):
        def __init__(self, label):
            super().__init__(label=label, style=discord.ButtonStyle.secondary)
            self.is_correct = label == correct_answer

        async def callback(self, interaction: Interaction):
            if interaction.user != ctx.author:
                return await interaction.response.send_message("❌ 哎呀，這是給別人的謎題哦～", ephemeral=True)

            if self.view.answered:
                return await interaction.response.send_message("⏳ 這題已經解開啦，幽靈不會重複問哦！", ephemeral=True)

            self.view.answered = True
            self.view.stop()  # 停止超時計時器

            for child in self.view.children:
                child.disabled = True
                if isinstance(child, discord.ui.Button) and child.label == correct_answer:
                    child.style = discord.ButtonStyle.success
                elif isinstance(child, discord.ui.Button):
                    child.style = discord.ButtonStyle.danger

            if self.is_correct:
                embed.color = discord.Color.green()
                embed.description = f"{question}\n\n✅ 「嘻嘻，答對了呢～」幽幽子為你鼓掌！🎉"
            else:
                embed.color = discord.Color.red()
                embed.description = f"{question}\n\n❌ 「哎呀，錯啦～」正確答案是 `{correct_answer}`，下次再來哦！"

            await interaction.response.edit_message(embed=embed, view=self.view)

    await ctx.respond(embed=embed, view=QuizView(ctx.interaction))

@bot.slash_command(name="rpg-start", description="初始化你的rpg數據")
async def rpg_start(ctx: discord.ApplicationContext):
    embed = discord.Embed(
        title="RPG系統通知",
        description="正在開發中，預計完成時間：未知。\n如果你想要提前收到測試通知\n請點擊這個文字加入我們[測試群組](https://discord.gg/4GE3FpR8rH)",
        color=discord.Color.red()
    )
    embed.set_footer(text="很抱歉無法使用該指令")
    await ctx.respond(embed=embed)

@bot.slash_command(name="help", description="幽幽子為你介紹白玉樓的指令哦～")
async def help(ctx: discord.ApplicationContext):
    await ctx.defer(ephemeral=False)

    yuyuko_comments = [
        "嘻嘻，這些指令很有趣吧？快來試試看～",
        "靈魂的指引就在這裡，選擇你喜歡的吧～",
        "櫻花飄落時，指令的秘密也會顯現哦～",
        "這些指令，都是幽幽子精心準備的呢～",
        "來吧，讓我們一起探索這些指令的樂趣～",
        "白玉樓的風鈴響起，指令的旋律也隨之而來～",
        "靈魂的舞步，與這些指令共鳴吧～"
    ]

    embed_test = discord.Embed(
        title="⚠️ 幽幽子的測試員密語 ⚠️",
        description=(
            "這些是給測試員的特別指令，靈魂的試驗場哦～\n\n"
            "> `shutdown` - 讓白玉樓的燈火暫時 關閉機器人，讓幽幽子休息一下吧～\n"
            "> `restart` - 重啟機器人，靈魂需要一點新鮮空氣呢～\n"
            "> `addmoney` - 為用戶添加幽靈幣，靈魂的財富增加啦！\n"
            "> `removemoney` - 移除用戶的幽靈幣，哎呀，靈魂的財富減少了呢～\n"
            "> `tax` = 讓幽幽子的主人幫助國庫增長一些國稅"
        ),
        color=discord.Color.from_rgb(255, 182, 193)
    )
    embed_economy = discord.Embed(
        title="💸 幽幽子的幽靈幣經濟 💸",
        description=(
            "在白玉樓，幽靈幣可是很重要的哦～快來賺取你的財富吧！\n\n"
            "> `balance` - 讓幽幽子幫你窺探你的幽靈幣餘額～\n"
            "> `choose_job` - 選擇一份職業，靈魂也需要工作哦～\n"
            "> `work` - 努力工作，賺取更多的幽靈幣吧！\n"
            "> `pay` - 轉賬給其他靈魂，分享你的財富吧～\n"
            "> `reset_job` - 重置你的職業，換個新身份吧～\n"
            "> `leaderboard` - 查看經濟排行榜，看看誰是白玉樓最富有的靈魂！\n"
            "> `shop` - 在工作之餘也別忘了補充體力呀~\n"
            "> `backpack` - 可以看看靈魂的背包裏面有什麽好吃的~"
        ),
        color=discord.Color.from_rgb(255, 182, 193)
    )
    embed_admin = discord.Embed(
        title="🔒 幽幽子的管理權杖 🔒",
        description=(
            "這些是指令是給管理員的，靈魂的秩序由你來維護哦～\n\n"
            "> `ban` - 封鎖用戶，讓他們離開白玉樓吧！\n"
            "> `kick` - 踢出用戶，給他們一點小教訓～\n"
            "> `start_giveaway` - 開啟抽獎，靈魂們都期待著呢！\n"
            "> `mute` - 禁言某位成員，讓他們安靜一會兒～\n"
            "> `unmute` - 解除禁言，讓靈魂的聲音再次響起吧～"
        ),
        color=discord.Color.from_rgb(255, 182, 193)
    )
    embed_common = discord.Embed(
        title="🎉 幽幽子的日常樂趣 🎉",
        description=(
            "這些是給所有靈魂的日常指令，快來一起玩吧～\n\n"
            "> `time` - 查看待機時間，靈魂的悠閒時光有多少呢？\n"
            "> `ping` - 測試與靈界的通訊延遲，靈魂的波動有多快？\n"
            "> `server_info` - 獲取伺服器資訊，白玉樓的秘密都在這裡～\n"
            "> `user_info` - 窺探其他靈魂的資訊，嘻嘻～\n"
            "> `feedback` - 回報錯誤，幫幽幽子改進哦～\n"
            "> `quiz` - 挑戰問題，靈魂的智慧有多深呢？"
        ),
        color=discord.Color.from_rgb(255, 182, 193)
    )
    embed_fishing = discord.Embed(
        title="🎣 幽幽子的悠閒釣魚時光 🎣",
        description=(
            "在白玉樓的湖邊釣魚，享受悠閒時光吧～\n\n"
            "> `fish` - 開始釣魚，會釣到什麼魚呢？\n"
            "> `fish_back` - 打開釣魚背包，看看你的收穫吧～\n"
            "> `fish_shop` - 販售魚或購買魚具，準備好下次釣魚吧！\n"
            "> `fish_rod` - 切換漁具，用更好的魚竿釣大魚哦～"
        ),
        color=discord.Color.from_rgb(255, 182, 193)
    )
    embed_gambling = discord.Embed(
        title="🎰 幽幽子的賭博遊戲 🎰",
        description=(
            "用幽靈幣來挑戰運氣吧，靈魂的賭局開始啦～\n\n"
            "> `blackjack` - 與幽幽子玩一場21點遊戲，賭上你的幽靈幣吧！"
        ),
        color=discord.Color.from_rgb(255, 182, 193)
    )

    for embed in [embed_test, embed_economy, embed_admin, embed_common, embed_fishing, embed_gambling]:
        embed.set_footer(text=random.choice(yuyuko_comments))

    options = [
        discord.SelectOption(label="日常樂趣", description="查看普通指令", value="common", emoji="🎉"),
        discord.SelectOption(label="幽靈幣經濟", description="查看經濟系統指令", value="economy", emoji="💸"),
        discord.SelectOption(label="管理權杖", description="查看管理員指令", value="admin", emoji="🔒"),
        discord.SelectOption(label="悠閒釣魚", description="查看釣魚相關指令", value="fishing", emoji="🎣"),
        discord.SelectOption(label="測試員密語", description="查看測試員指令", value="test", emoji="⚠️"),
        discord.SelectOption(label="賭博遊戲", description="查看賭博指令", value="gambling", emoji="🎰"),
    ]

    yuyuko_timeout_comments = [
        "櫻花已凋謝，選單也休息了哦～請重新輸入 `/help` 吧！",
        "靈魂的舞步停下了，選單也過期啦～再來一次吧！",
        "嘻嘻，時間到了，選單已經飄走了～重新輸入 `/help` 哦！",
        "白玉樓的風鈴停了，選單也休息了呢～再試一次吧～",
        "靈魂的波動消失了，選單也過期啦～請重新輸入 `/help`！"
    ]

    async def select_callback(interaction: discord.Interaction):
        selected_value = select.values[0]
        embeds = {
            "common": embed_common,
            "economy": embed_economy,
            "admin": embed_admin,
            "fishing": embed_fishing,
            "test": embed_test,
            "gambling": embed_gambling
        }
        selected_embed = embeds.get(selected_value, embed_common)
        await interaction.response.edit_message(embed=selected_embed)

    select = Select(
        placeholder="選擇指令分類吧，靈魂的指引在等你～",
        options=options
    )
    select.callback = select_callback

    class TimeoutView(View):
        def __init__(self, timeout=60):
            super().__init__(timeout=timeout)
            self.message = None

        async def on_timeout(self):
            for child in self.children:
                if isinstance(child, Select):
                    child.disabled = True
            try:
                if self.message:
                    await self.message.edit(
                        content=random.choice(yuyuko_timeout_comments),
                        view=self
                    )
            except discord.NotFound:
                print("原始訊息未找到，可能已被刪除。")

    view = TimeoutView()
    view.add_item(select)

    message = await ctx.respond(
        content="🌸 歡迎來到白玉樓，我是西行寺幽幽子～請選擇指令分類吧！",
        embed=embed_common,
        view=view
    )
    view.message = await message.original_response()

try:
    bot.run(TOKEN, reconnect=True)
except discord.LoginFailure:
    print("無效的機器人令牌。請檢查 TOKEN。")
except Exception as e:
    print(f"機器人啟動時發生錯誤: {e}")
