import discord
from discord.ext import commands
import os
import sys
import random
import json
from datetime import datetime, timedelta, timezone
import asyncio
from discord.ui import Select, Button, View, Modal, input_text
import subprocess
import time
from dotenv import load_dotenv
import logging
from urllib.parse import urlparse
from pydantic_core import InitErrorDetails
import yaml
from discord import SelectOption
from discord import ui
import subprocess
import psutil
from home_work import parse_requirement
import calculator
import math
from calendar_module import add_event, remove_event, get_user_events, check_events, CalendarEvent
from omikuji import draw_lots
import re
from decimal import Decimal, ROUND_DOWN
from discord import Interaction
import shutil

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN_TEST_BOT")
AUTHOR_ID = int(os.getenv('AUTHOR_ID', 0))
WORK_COOLDOWN_SECONDS = 230

if not TOKEN or not AUTHOR_ID:
    raise ValueError("You lots the discord bot token and aothor_id pls chack you'r .env file")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(filename='main-error.log', encoding='utf-8', mode='w'),
        logging.StreamHandler()
    ]
)

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

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

user_balance = load_yaml('test-balance.yml')
config = load_json("config.json")
user_data = load_yaml("config_user.yml")
quiz_data = load_yaml('quiz.yml')
rpg_data = load_json("rpg_config.json")
raw_jobs = config.get("jobs", [])
jobs_data = {job: details for item in raw_jobs for job, details in item.items()}
fish_data = config.get("fish", {})
shop_data = config.get("shop_item", {})
rpg_data = load_json("rpg_config.json")

if not jobs_data:
    print("警告: 職業數據 (jobs) 為空！請檢查 config.json 文件。")
if not fish_data:
    print("警告: 魚類數據 (fish) 為空！請檢查 config.json 文件。")
if not shop_data:
    print("警告: 商店數據 (shop_item) 為空！請檢查 config.json 文件。")

dm_messages = load_json('dm_messages.json')
questions = load_yaml('trivia_questions.yml', {}).get('questions', [])
user_rod = load_yaml('user_rod.yml', {})

if not os.path.exists('user_rod.yml'):
    save_yaml('user_rod.yml', {})

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")

    print("Slash commands are automatically synchronized.")

    try:
        await bot.change_presence(
            status=discord.Status.dnd,
            activity=discord.Activity(type=discord.ActivityType.streaming, name='Monster Hunter', url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        )
        print("The bot's status has been set.")
    except Exception as e:
        print(f"Failed to set presence: {e}")

@bot.event
async def on_message(message):
    global last_activity_time
    last_activity_time = time.time()
    if message.author == bot.user:
        return

    content_lower = message.content.lower()
    if '關於芙蘭' in content_lower:
        await message.channel.send('芙蘭的創建時間是<t:1722340500:D>')

    elif '芙蘭閑置多久了' in content_lower:
        idle_minutes = (time.time() - last_activity_time) / 60
        await message.channel.send(f'芙蘭目前閑置時間為 {idle_minutes:.2f} 分鐘。')

    elif '關於製作者' in content_lower:
        await message.channel.send('製作者是個很好的人 雖然看上去有點怪怪的')

    elif '芙蘭的生日' in content_lower:
        await message.channel.send('機器人芙蘭的生日在<t:1722340500:D>')

    elif message.content.startswith('芙蘭去睡覺吧'):
        if message.author.id == AUTHOR_ID:
            await message.channel.send("好! 我去睡了 晚安 大哥哥")
            await asyncio.sleep(5)
            await bot.close()
        else:
            await message.channel.send("你無權關閉我 >_<")

    elif message.content.startswith('重啓芙蘭'):
        if message.author.id == AUTHOR_ID:
            await message.channel.send("正在重啟芙蘭...")
            subprocess.Popen([sys.executable, os.path.abspath(__file__)])
            await bot.close()
        else:
            await message.channel.send("你無權重啓我 >_<")
    
    if '早安芙蘭' in content_lower:
        await message.channel.send('您好 我是芙蘭醬喲')
        await asyncio.sleep(3)
        await message.channel.send("欸大哥哥 你在説什麽？ 來配我玩吧~")
            
    await bot.process_commands(message)

@bot.slash_command(name="restart", description="重启机器人")
async def restart(interaction: discord.Interaction):
    if interaction.user.id == AUTHOR_ID:
        try:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send("重启中...")
            os.execv(sys.executable, ['python'] + sys.argv)
        except Exception as e:
            print(f"Restart command failed: {e}")
    else:
        await interaction.response.send_message("你没有权限执行此操作。", ephemeral=True)

@bot.slash_command(name="shutdown", description="关闭机器人")
async def shutdown(interaction: discord.Interaction):
    if interaction.user.id == AUTHOR_ID:
        try:
            await interaction.response.defer(ephemeral=True)

            await interaction.followup.send("关闭中...")

            await bot.close()
        except Exception as e:
            logging.error(f"Shutdown command failed: {e}")
            await interaction.followup.send(f"关闭失败，错误信息：{e}", ephemeral=True)
    else:
        await interaction.response.send_message("你没有权限执行此操作。", ephemeral=True)

@bot.slash_command(name="rpg-start", description="開啓你的RPG冒險之旅")
async def rpg_start(interaction: discord.Interaction):
    
    guild_id = str(interaction.guild.id)
    user_id = str(interaction.user.id)

    balance_data = load_yaml("test-balance.yml")
    user_balance = balance_data.get(guild_id, {}).get(user_id, 0)
    rpg_data = load_json("rpg_config.json")

    if guild_id in rpg_data and user_id in rpg_data[guild_id]:
        await interaction.response.send_message(
            "⚠️ 你已經初始化一次了，無法再次使用該指令。",
            ephemeral=True
        )
        return

    if guild_id not in rpg_data:
        rpg_data[guild_id] = {}

    rpg_data[guild_id][user_id] = {
        "等級": 1,
        "經驗值": 0,
        "升級需求": 100,
        "職業": "無業游民",
        "魔力": "100/100",
        "防禦": "0/20",
        "體力": "20/20"
    }
    save_json("rpg_config.json", rpg_data)
    
    avatar_url = interaction.user.display_avatar.url
    embed_color = discord.Color.gold()
    embed = discord.Embed(title=f"⚔️ RPG 冒險開始！", color=embed_color)
    embed.set_thumbnail(url=avatar_url)
    embed.add_field(name="等級", value="1", inline=True)
    embed.add_field(name="經驗值", value="0%", inline=True)
    embed.add_field(name="職業", value="無業游民", inline=True)
    embed.add_field(name="魔力", value="100/100", inline=True)
    embed.add_field(name="金錢", value=f"{user_balance} 幽靈幣", inline=True)
    embed.add_field(name="防禦", value="0/20", inline=True)
    embed.add_field(name="體力", value="20/20", inline=True)

    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="rpg-info", description="查看你的RPG冒險數據")
async def rpg_info(interaction: discord.Interaction):
    
    guild_id = str(interaction.guild.id)
    user_id = str(interaction.user.id)

    balance_data = load_yaml("test-balance.yml")
    user_balance = balance_data.get(guild_id, {}).get(user_id, 0)
    rpg_data = load_json("rpg_config.json")
    
    if guild_id not in rpg_data or user_id not in rpg_data[guild_id]:
        await interaction.response.send_message(
            "⚠️ 你尚未開始冒險，請先使用 `/rpg-start`！",
            ephemeral=True
        )
        return
    
    user_rpg_data = rpg_data[guild_id][user_id]
    
    level = user_rpg_data.get("等級", 1)
    exp = user_rpg_data.get("經驗值", 0)
    exp_needed = user_rpg_data.get("升級需求", 100)

    avatar_url = interaction.user.display_avatar.url
    embed = discord.Embed(title=f"📜 你的RPG數據", color=discord.Color.blue())
    embed.set_thumbnail(url=avatar_url)
    
    embed.add_field(name="🏅 等級", value=str(level), inline=True)
    embed.add_field(name="📈 經驗值", value=f"{exp} / {exp_needed}%", inline=True)
    embed.add_field(name="👤 職業", value=user_rpg_data.get("職業", "無業游民"), inline=True)
    embed.add_field(name="🔮 魔力", value=user_rpg_data.get("魔力", "未知"), inline=True)
    embed.add_field(name="🛡️ 防禦", value=user_rpg_data.get("防禦", "未知"), inline=True)
    embed.add_field(name="❤️ 體力", value=user_rpg_data.get("體力", "未知"), inline=True)
    embed.add_field(name="💰 金錢", value=f"{user_balance} 幽靈幣", inline=True)

    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="rpg-shop", description="打開 RPG 商店")
async def rpg_shop(ctx: discord.ApplicationContext):
    if ctx.user.id != AUTHOR_ID:
        await ctx.respond("⚠️ 你無法使用該指令 目前還在測試中.", ephemeral=True)
        return
    await ctx.defer()

    try:
        with open("rpg_shop_config.json", "r", encoding="utf-8") as f:
            shop_data = json.load(f)
    except FileNotFoundError:
        await ctx.respond("找不到商店配置文件！", ephemeral=True)
        return

    if not shop_data:
        await ctx.respond("目前沒有商店！", ephemeral=True)
        return

    class ShopSelect(discord.ui.Select):
        def __init__(self):
            options = [discord.SelectOption(label=shop, value=shop) for shop in shop_data.keys()]
            super().__init__(placeholder="選擇你要前往的商店", options=options)

        async def callback(self, interaction: discord.Interaction):
            await show_shop(interaction, self.values[0])

    async def show_shop(interaction: discord.Interaction, shop_name):
        shop_items = shop_data.get(shop_name, {}).get("商品", [])
        if not shop_items:
            await interaction.response.send_message(f"{shop_name} 目前沒有商品！", ephemeral=True)
            return

        class ItemSelect(discord.ui.Select):
            def __init__(self):
                options = [discord.SelectOption(label=item["name"], value=item["name"]) for item in shop_items]
                super().__init__(placeholder="選擇你要購買的商品", options=options)

            async def callback(self, interaction: discord.Interaction):
                await show_item_details(interaction, shop_name, self.values[0])

        view = discord.ui.View()
        view.add_item(ItemSelect())
        await interaction.response.send_message(f"**{shop_name}**\n請選擇你要購買的商品：", view=view, ephemeral=True)

    async def show_item_details(interaction: discord.Interaction, shop_name, item_name):
        shop_items = shop_data.get(shop_name, {}).get("商品", [])
        item = next((i for i in shop_items if i["name"] == item_name), None)

        if not item:
            await interaction.response.send_message("找不到該商品！", ephemeral=True)
            return

        item_price = item.get("price", 0)
        item_attributes = "\n".join([f"**{key}:** {value}" for key, value in item.items() if key not in ["name", "price"]])

        embed = discord.Embed(
            title=f"商品資訊 - {item_name}",
            description=f"**價格:** {item_price} 金幣\n{item_attributes}",
            color=discord.Color.gold(),
        )

        class BuyButton(discord.ui.Button):
            def __init__(self):
                super().__init__(label="購買", style=discord.ButtonStyle.green)

            async def callback(self, interaction: discord.Interaction):
                await purchase_item(interaction, item_name, item_price, item)

        view = discord.ui.View()
        view.add_item(BuyButton())

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def purchase_item(interaction: discord.Interaction, item_name, item_price, item):
        try:
            with open("test-balance.yml", "r", encoding="utf-8") as f:
                balance_data = yaml.safe_load(f) or {}
        except FileNotFoundError:
            await interaction.response.send_message("找不到餘額文件！", ephemeral=True)
            return

        user_id = str(interaction.user.id)
        guild_id = str(interaction.guild_id)
        user_balance = balance_data.get(user_id, 0)

        if user_balance < item_price:
            await interaction.response.send_message(f"你的金幣不足，無法購買 {item_name}！", ephemeral=True)
            return

        balance_data[user_id] -= item_price
        with open("test-balance.yml", "w", encoding="utf-8") as f:
            yaml.safe_dump(balance_data, f)

        try:
            with open("rpg_player_backpack.json", "r", encoding="utf-8") as f:
                backpack_data = json.load(f)
        except FileNotFoundError:
            backpack_data = {}

        if guild_id not in backpack_data:
            backpack_data[guild_id] = {}

        if user_id not in backpack_data[guild_id]:
            backpack_data[guild_id][user_id] = []

        existing_item = next((i for i in backpack_data[guild_id][user_id] if i["name"] == item_name), None)
        if existing_item:
            existing_item["quantity"] = existing_item.get("quantity", 1) + 1
        else:
            item_copy = item.copy()
            item_copy["quantity"] = 1  # 加入數量
            backpack_data[guild_id][user_id].append(item_copy)

        with open("rpg_player_backpack.json", "w", encoding="utf-8") as f:
            json.dump(backpack_data, f, ensure_ascii=False, indent=4)

        await interaction.response.send_message(f"成功購買 {item_name}！你的餘額剩餘 {balance_data[user_id]} 金幣。", ephemeral=True)

    view = discord.ui.View()
    view.add_item(ShopSelect())
    await ctx.respond("**商店大街**\n請選擇你要前往的商店：", view=view, ephemeral=True)

@bot.slash_command(name="rpg-backpack", description="查看你的 RPG 背包")
async def rpg_backpack(ctx: discord.ApplicationContext):
    if ctx.user.id != AUTHOR_ID:
        await ctx.respond("⚠️ 你無法使用該指令，目前還在測試中.", ephemeral=True)
        return
    server_id = str(ctx.guild.id)
    user_id = str(ctx.user.id)

    try:
        with open("rpg_player_backpack.json", "r", encoding="utf-8") as f:
            backpack_data = json.load(f)
    except FileNotFoundError:
        backpack_data = {}

    server_backpack = backpack_data.get(server_id, {})
    user_backpack = server_backpack.get(user_id, [])

    if not user_backpack:
        await ctx.respond("你的背包是空的！", ephemeral=True)
        return

    backpack_items = "\n".join([f"**{item['name']}** x{item['quantity']}" for item in user_backpack])
    
    embed = discord.Embed(title=f"{ctx.user.display_name} 的背包", description=backpack_items, color=discord.Color.blue())
    await ctx.respond(embed=embed, ephemeral=True)

@bot.slash_command(name="rpg-mission", description="前往冒險者協會，選擇一個任務")
async def rpg_mission(interaction: discord.Interaction):
    mission_data = load_json("rpg-mission-config.json")
    if not mission_data:
        await interaction.response.send_message("⚠️ 目前沒有可選的任務！", ephemeral=True)
        return

    class MissionSelectView(View):
        def __init__(self, user_id):
            super().__init__(timeout=60)
            self.user_id = user_id

            for mission_id, mission in mission_data.items():
                button = Button(label=mission["mission name"], style=discord.ButtonStyle.primary)
                button.callback = self.create_callback(mission_id, mission)
                self.add_item(button)

        def create_callback(self, mission_id, mission):
            async def callback(interaction: discord.Interaction):
                if interaction.user.id != self.user_id:
                    await interaction.response.send_message("⚠️ 這不是你的選單！", ephemeral=True)
                    return
                
                guild_id = str(interaction.guild.id)
                user_id = str(interaction.user.id)
                rpg_data = load_json("rpg_config.json")

                if guild_id not in rpg_data:
                    rpg_data[guild_id] = {}
                if user_id not in rpg_data[guild_id]:
                    await interaction.response.send_message("⚠️ 你還沒有開始 RPG！請先使用 `/rpg-start`。", ephemeral=True)
                    return

                rpg_data[guild_id][user_id]["當前任務"] = {
                    "id": mission_id,
                    "name": mission["mission name"],
                    "description": mission["mission description"],
                    "rewards": {
                        "exp": int(mission["reward 1"].replace("經驗值", "")),
                        "gold": int(mission["reward 2"].replace("幽靈幣", ""))
                    },
                    "progress": mission["progress"]  # 存入初始進度
                }
                save_json("rpg_config.json", rpg_data)

                embed = discord.Embed(title="📜 任務已接取！", color=discord.Color.blue())
                embed.add_field(name="任務內容", value=mission["mission name"], inline=False)
                embed.add_field(name="描述", value=mission["mission description"], inline=False)
                embed.add_field(name="進度", value=mission["progress"], inline=True)
                embed.add_field(name="獎勵", value=f"💰 {mission['reward 2']}\n🎖️ {mission['reward 1']}", inline=True)

                await interaction.response.edit_message(embed=embed, view=None)
            
            return callback

    embed = discord.Embed(title="🏛️ 冒險者協會", description="請選擇你要接取的任務：", color=discord.Color.gold())
    view = MissionSelectView(interaction.user.id)

    await interaction.response.send_message(embed=embed, view=view)

@bot.slash_command(name="rpg-complete", description="完成當前 RPG 任務")
async def rpg_complete(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    user_id = str(interaction.user.id)

    rpg_data = load_json("rpg_config.json")
    balance_data = load_json("test-balance.yml")

    if guild_id not in rpg_data or user_id not in rpg_data[guild_id]:
        await interaction.response.send_message("⚠️ 你還沒有開始 RPG！請先使用 `/rpg-start`。", ephemeral=True)
        return

    user_data = rpg_data[guild_id][user_id]
    mission = user_data.get("當前任務")

    if not mission:
        await interaction.response.send_message("⚠️ 你沒有進行中的任務，請先使用 `/rpg-mission`！", ephemeral=True)
        return

    current_progress, max_progress = map(int, mission["progress"].split("/"))

    if current_progress < max_progress:
        await interaction.response.send_message(
            f"⚠️ 你的任務尚未完成！({current_progress}/{max_progress})",
            ephemeral=True
        )
        return

    exp_reward = mission["rewards"]["exp"]
    gold_reward = mission["rewards"]["gold"]

    user_data["經驗值"] += exp_reward
    balance_data.setdefault(guild_id, {}).setdefault(user_id, 0)
    balance_data[guild_id][user_id] += gold_reward

    leveled_up = False
    while user_data["經驗值"] >= user_data["升級需求"]:
        user_data["經驗值"] -= user_data["升級需求"]
        user_data["等級"] += 1
        user_data["升級需求"] = int(user_data["升級需求"] * 1.1)
        leveled_up = True

    user_data["當前任務"] = None

    save_json("rpg_config.json", rpg_data)
    save_json("test-balance.yml", balance_data)

    embed = discord.Embed(title="🎉 任務完成！", color=discord.Color.green())
    embed.add_field(name="獲得獎勵", value=f"💰 {gold_reward} 幽靈幣\n🎖️ {exp_reward} 經驗", inline=True)
    embed.add_field(name="當前等級", value=str(user_data["等級"]), inline=True)
    embed.add_field(name="經驗值", value=f"{user_data['經驗值']} / {user_data['升級需求']}", inline=True)

    if leveled_up:
        embed.description = "🎊 恭喜你升級了！"

    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="rpg-adventure", description="展開一次冒險，探索未知的世界！")
async def rpg_adventure(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    user_id = str(interaction.user.id)

    rpg_data = load_json("rpg_config.json")
    events_data = load_json("rpg_events.json")  # 存放隨機事件的 JSON
    balance_data = load_json("test-balance.yml")
    backpack_data = load_json("rpg_player_backpack.json")  # 玩家背包數據

    # 確保玩家數據存在
    if guild_id not in rpg_data or user_id not in rpg_data[guild_id]:
        await interaction.response.send_message(
            f"🤖 **{bot.user.name}**: 您好，我找不到您的初始化數據。\n"
            f"請使用 `/rpg-start` 來初始化您的數據，這樣您才能開始您的第一次冒險！",
            ephemeral=True
        )
        return

    user_data = rpg_data[guild_id][user_id]

    # 確保玩家有足夠體力
    if user_data.get("體力", 0) <= 0:
        await interaction.response.send_message("⚠️ 你已經沒有體力了，請稍後再來！", ephemeral=True)
        return

    # 扣除一次體力
    user_data["體力"] -= 1

    # 隨機選擇一個事件
    event = random.choice(events_data["地表冒險"])

    # 建立回應的嵌入訊息
    embed = discord.Embed(title="🌍 你的冒險結果", description=event["event description"], color=discord.Color.green())
    embed.add_field(name="事件", value=event["event name"], inline=False)

    # 檢查是否為戰鬥事件
    if event["event battle"]:
        monster = event["monster"]
        embed.add_field(name="🆚 遭遇怪物", value=f"**{monster['monster name']}**", inline=False)
        embed.add_field(name="❤️ HP", value=str(monster["monster hp"]), inline=True)
        embed.add_field(name="⚔️ 攻擊", value=str(monster["monster attack"]), inline=True)
        embed.add_field(name="🛡️ 防禦", value=str(monster["monster defence"]), inline=True)

        # 簡單模擬戰鬥結果（未來可以改進）
        player_attack = user_data["攻擊力"]
        monster_hp = int(monster["monster hp"])
        while monster_hp > 0:
            monster_hp -= max(1, player_attack - int(monster["monster defence"]))

        # 獲勝後獎勵
        exp_reward = int(event["reward 1"].replace("經驗值", "").strip())
        gold_reward = int(event["reward 2"].replace("幽靈幣", "").strip())

        user_data["經驗值"] += exp_reward
        balance_data.setdefault(guild_id, {}).setdefault(user_id, 0)
        balance_data[guild_id][user_id] += gold_reward

        embed.add_field(name="🏆 獎勵", value=f"🎖️ {exp_reward} 經驗\n💰 {gold_reward} 幽靈幣", inline=False)
    else:
        # 非戰鬥事件（如寶箱）
        gold_reward = int(event["reward 1"].replace("幽靈幣", "").strip())
        item_reward = event["item"]

        balance_data.setdefault(guild_id, {}).setdefault(user_id, 0)
        balance_data[guild_id][user_id] += gold_reward

        # 更新玩家背包數據
        if guild_id not in backpack_data:
            backpack_data[guild_id] = {}
        if user_id not in backpack_data[guild_id]:
            backpack_data[guild_id][user_id] = {}

        item_name = item_reward["item name"]
        item_amount = int(item_reward["item amount"])

        # 如果物品已經存在，則增加數量
        if item_name in backpack_data[guild_id][user_id]:
            backpack_data[guild_id][user_id][item_name] += item_amount
        else:
            backpack_data[guild_id][user_id][item_name] = item_amount

        embed.add_field(name="📦 你發現了寶箱！", value=f"💰 {gold_reward} 幽靈幣\n🎁 {item_name} x{item_amount}", inline=False)

    # 儲存更新後的數據
    save_json("rpg_config.json", rpg_data)
    save_json("test-balance.yml", balance_data)
    save_json("rpg_player_backpack.json", backpack_data)

    # 發送冒險結果
    await interaction.response.send_message(embed=embed)


@bot.slash_command(name="balance", description="查询用户余额")
async def balance(ctx: discord.ApplicationContext):
    try:
        user_balance = load_yaml("test-balance.yml")
        guild_id = str(ctx.guild.id)
        user_id = str(ctx.user.id)

        if guild_id not in user_balance:
            user_balance[guild_id] = {}

        balance = user_balance[guild_id].get(user_id, 0)

        embed = discord.Embed(
            title="💰 幽靈幣餘額查詢",
            description=(
                f"**{ctx.user.display_name}** 在此群组的幽靈幣餘額为：\n\n"
                f"**{balance} 幽靈幣**"
            ),
            color=discord.Color.from_rgb(219, 112, 147)
        )
        embed.set_footer(text="感谢使用幽靈幣系統！")

        await ctx.respond(embed=embed)

    except Exception as e:
        logging.error(f"Unexpected error in balance command: {e}")
        await ctx.respond(f"發生錯誤：{e}", ephemeral=True)

try:
    bot.run(TOKEN, reconnect=True)
except discord.LoginFailure:
    print("無效的機器人令牌。請檢查 TOKEN。")
except Exception as e:
    print(f"機器人啟動時發生錯誤: {e}")
