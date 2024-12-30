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
from discord.ext import commands
from discord.ui import View, Button, Select
from discord import Interaction
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from urllib.parse import urlencode
from filelock import FileLock
from omikuji import draw_lots
from responses import food_responses, death_responses, life_death_responses, self_responses, friend_responses, maid_responses, mistress_responses, reimu_responses, get_random_response

# 加載變量環境
load_dotenv()

# 硬編碼的token和discord_user_id
TOKEN = os.getenv('DISCORD_TOKEN_MAIN_BOT')
AUTHOR_ID = int(os.getenv('AUTHOR_ID', 0))
LOG_FILE_PATH = "feedback_log.txt"
WORK_COOLDOWN_SECONDS = 3600

# 如果token和discord_user_id缺失是會顯示 “缺少必要的環境變量 DISCORD_TOKEN_MAIN_BOT 或 AUTHOR_ID”
if not TOKEN or not AUTHOR_ID:
    raise ValueError("缺少必要的環境變量 DISCORD_TOKEN_MAIN_BOT 或 AUTHOR_ID")

# 基礎的log記錄器
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(filename='main-error.log', encoding='utf-8', mode='w'),
        logging.StreamHandler()
    ]
)

# 初始化intents和bot
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

# 一次性加載全部的文件
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

def load_json(file_name, default={}):
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

user_balance = load_yaml('balance.yml')
dm_messages = load_json('dm_messages.json')
questions = load_yaml('trivia_questions.yml', {}).get('questions', [])
fish_data = load_yaml('fishi.yml')
shop_data = load_yaml('fishi_shop.yml')
user_rod = load_yaml('user_rod.yml', {})
config = load_json("config.json")
user_data = load_yaml("config_user.yml")

jobs_data = config.get("jobs", {})

if not os.path.exists('user_rod.yml'):
    save_yaml('user_rod.yml', {})

def get_random_question():
    return random.choice(questions) if questions else None

cooldowns = {}
active_giveaways = {}

# 偵測訊息事件裝飾器
@bot.event
async def on_message(message):
    global last_activity_time
    
    if message.author == bot.user:
        return
    
    if message.webhook_id:
        return
    
    content = message.content
    
    if '關於機器人幽幽子' in message.content.lower():
        await message.channel.send('幽幽子的創建時間是<t:1623245700:D>')
    
    if '關於製作者' in message.content.lower():
        await message.channel.send('製作者是個很好的人 雖然看上有有點怪怪的')
    
    if '幽幽子的生日' in message.content.lower():
        await message.channel.send('機器人幽幽子的生日在<t:1623245700:D>')
    
    if message.content.startswith('關閉幽幽子'):
        if message.author.id == AUTHOR_ID:
            await message.channel.send("正在關閉...")
            await asyncio.sleep(2)
            await bot.close()
            return
        else:
            await message.channel.send("你無權關閉我 >_< ")
            return

    elif message.content.startswith('重啓幽幽子'):
        if message.author.id == AUTHOR_ID:
            await message.channel.send("正在重啟幽幽子...")
            subprocess.Popen([sys.executable, os.path.abspath(__file__)])
            await bot.close()
            return
        else:
            await message.channel.send("你無權重啓我 >_< ")
            return

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
            await message.channel.send("早安 主人 今日的開發目標順利嗎")
        else:
            await message.reply("早上好 今天有什麽事情儘早完成喲", mention_author=False)
    
    if message.content == "午安":
        if message.author.id == AUTHOR_ID:
            await message.channel.send("下午好呀 今天似乎沒有什麽事情可以做呢")
        else:
            await message.reply("中午好啊 看起來汝似乎無所事事的呢", mention_author=False)
    
    if message.content == "晚安":
        current_time = datetime.now().strftime("%H:%M")
        
        if message.author.id == AUTHOR_ID:
            await message.channel.send(f"你趕快去睡覺 現在已經是 {current_time} 了 別再熬夜了！")
        else:
            await message.reply(f"現在的時間是 {current_time} 汝還不就寢嗎？", mention_author=False)
    
    await bot.process_commands(message)

# 機器人上綫事件
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")

    print("斜線指令已自動同步。")

    try:
        await bot.change_presence(
            status=discord.Status.dnd,
            activity=discord.Activity(type=discord.ActivityType.playing, name='Code')
        )
        print("已設置機器人的狀態。")
    except Exception as e:
        print(f"Failed to set presence: {e}")

    global last_activity_time
    last_activity_time = time.time()

@bot.slash_command(name="invite", description="生成机器人的邀请链接")
async def invite(ctx: discord.ApplicationContext):
    if not bot.user:
        await ctx.respond(
            "抱歉，无法生成邀请链接，机器人尚未正确启动。",
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
        title="邀请 幽幽子 到你的服务器",
        description=(
            "探索与幽幽子的专属互动，感受她的优雅与神秘。\n"
            f"✨ [点击这里邀请幽幽子]({invite_url}) ✨"
        ),
        color=discord.Color.purple()
    )
    if bot.user.avatar:
        embed.set_thumbnail(url=bot.user.display_avatar.url)
    embed.set_footer(text="感谢您的支持，让幽幽子加入您的服务器！")
    await ctx.respond(embed=embed)

@bot.slash_command(name="about-me", description="關於機器人")
async def about_me(ctx: discord.ApplicationContext):
    if not bot.user:
        await ctx.respond(
            "抱歉，無法提供關於機器人的資訊，目前機器人尚未正確啟動。",
            ephemeral=True
        )
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # 當前時間

    embed = discord.Embed(
        title="關於我",
        description=(
            "早上好，用戶！\n\n"
            "我是幽幽子機器人 \n"
            "你可以使用 `/` 來查看我的指令。\n"
            "同時，你也可以使用 `/help` 來獲取更詳細的幫助。\n\n"
            "不過，如果你想知道我是用什麼庫製作的話...... 不告訴你 "
        ),
        color=discord.Color.from_rgb(255, 182, 193)
    )

    if bot.user.avatar:
        embed.set_thumbnail(url=bot.user.display_avatar.url)

    embed.set_footer(text=f"{now}")
    await ctx.respond(embed=embed)

@bot.slash_command(name="rpg_start", description="初始化RPG數據")
async def rpg_start(ctx: discord.ApplicationContext):
    embed = discord.Embed(
        title="RPG 系統通知",
        description="RPG 系統正在製作中，預計完成時間：未知。",
        color=discord.Color.red()
    )
    embed.set_footer(text="感谢您的耐心等待！")
    await ctx.respond(embed=embed)

@bot.slash_command(name="balance", description="查询用户余额")
async def balance(ctx: discord.ApplicationContext):
    try:
        user_balance = load_yaml("balance.yml")
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

@bot.slash_command(name="balance_top", description="查看幽靈幣排行榜")
async def balance_top(interaction: discord.Interaction):
    try:
        if not interaction.guild:
            await interaction.response.send_message("此命令只能在伺服器中使用。", ephemeral=True)
            return

        await interaction.response.defer()

        try:
            with open('balance.yml', 'r', encoding='utf-8') as file:
                balance_data = yaml.safe_load(file) or {}
        except FileNotFoundError:
            await interaction.followup.send("找不到 balance.yml 文件。", ephemeral=True)
            logging.error("找不到 balance.yml 文件。")
            return
        except yaml.YAMLError as yaml_error:
            await interaction.followup.send("讀取 balance.yml 時發生錯誤。", ephemeral=True)
            logging.error(f"讀取 balance.yml 時發生錯誤: {yaml_error}")
            return

        guild_id = str(interaction.guild.id)
        if guild_id not in balance_data or not balance_data[guild_id]:
            await interaction.followup.send("目前沒有排行榜數據。", ephemeral=True)
            return

        guild_balances = balance_data[guild_id]
        sorted_balances = sorted(guild_balances.items(), key=lambda x: x[1], reverse=True)

        leaderboard = []
        for index, (user_id, balance) in enumerate(sorted_balances[:10], start=1):
            try:
                member = interaction.guild.get_member(int(user_id))
                if member:
                    username = member.display_name
                else:
                    user = await bot.fetch_user(int(user_id))
                    username = user.name if user else f"未知用戶（ID: {user_id}）"
            except Exception as fetch_error:
                logging.error(f"無法獲取用戶 {user_id} 的名稱: {fetch_error}")
                username = f"未知用戶（ID: {user_id}）"
            leaderboard.append(f"**#{index}** - {username}: {balance} 幽靈幣")

        leaderboard_message = "\n".join(leaderboard)

        embed = discord.Embed(
            title="🏆 幽靈幣排行榜 🏆",
            description=leaderboard_message or "排行榜數據為空。",
            color=discord.Color.from_rgb(255, 182, 193)
        )
        embed.set_footer(text="排行榜僅顯示前 10 名")

        await interaction.followup.send(embed=embed)

    except Exception as e:
        await interaction.followup.send("執行命令時發生未預期的錯誤，請稍後再試。", ephemeral=True)
        logging.error(f"執行命令時發生錯誤: {e}")

@bot.slash_command(name="choose_job", description="選擇你的工作並保存至配置！")
async def choose_job(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    user_id = str(interaction.user.id)

    if guild_id in user_data and user_id in user_data[guild_id]:
        current_job = user_data[guild_id][user_id]["job"]
        embed = discord.Embed(
            title="職業選擇",
            description=f"你已經有職業了！你現在的是 **{current_job}**。",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if not jobs_data:
        embed = discord.Embed(
            title="錯誤",
            description="職業數據尚未配置，請使用**`/feedback`**指令回報錯誤！",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    options = [
        discord.SelectOption(label=job, description=f"獲取 {data['min']}-{data['max']} 幽靈幣", value=job)
        for job, data in jobs_data.items()
    ]

    class JobSelect(discord.ui.Select):
        def __init__(self):
            super().__init__(
                placeholder="選擇你的工作...",
                options=options,
                min_values=1,
                max_values=1,
            )

        async def callback(self, interaction: discord.Interaction):
            chosen_job = self.values[0]

            if guild_id not in user_data:
                user_data[guild_id] = {}
            user_data[guild_id][user_id] = {"job": chosen_job, "cooldown": None}
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
    message = await interaction.response.send_message(embed=embed, view=view)
    view.message = await message

@bot.slash_command(name="work", description="執行你的工作並賺取幽靈幣！")
async def work(interaction: discord.Interaction):
    try:
        if not interaction.guild:
            await interaction.response.send_message("此命令只能在伺服器中使用。", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)

        if guild_id not in user_data or user_id not in user_data[guild_id]:
            await interaction.response.send_message(
                "你尚未選擇職業，請先使用 `/choose_job` 選擇你的職業！", ephemeral=True
            )
            return

        user_info = user_data[guild_id][user_id]
        job_name = user_info.get("job")
        last_cooldown = user_info.get("cooldown")

        if job_name not in jobs_data:
            await interaction.response.send_message(
                f"無效的職業: {job_name}，請重新選擇！", ephemeral=True
            )
            return

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
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        job_rewards = jobs_data[job_name]
        reward = random.randint(job_rewards["min"], job_rewards["max"])

        if guild_id not in user_balance:
            user_balance[guild_id] = {}
        user_balance[guild_id][user_id] = user_balance[guild_id].get(user_id, 0) + reward
        save_yaml("balance.yml", user_balance)

        new_cooldown = now + timedelta(seconds=WORK_COOLDOWN_SECONDS)
        user_data[guild_id][user_id]["cooldown"] = new_cooldown.isoformat()
        save_yaml("config_user.yml", user_data)

        embed = discord.Embed(
            title="工作成功！",
            description=f"{interaction.user.mention} 作為 **{job_name}** 賺取了 **{reward} 幽靈幣**！🎉",
            color=discord.Color.green()
        )
        embed.set_footer(text=f"職業: {job_name}")

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        logging.error(f"執行 work 指令時出錯: {e}")
        embed = discord.Embed(
            title="錯誤",
            description="執行命令時發生錯誤，請稍後再試。",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.slash_command(name="pay", description="转账给其他用户")
async def pay(interaction: discord.Interaction, member: discord.Member, amount: int):
    try:
        if not interaction.guild:
            await interaction.response.send_message("❌ 此命令只能在伺服器中使用。", ephemeral=True)
            return

        user_balance = load_yaml("balance.yml")
        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)
        recipient_id = str(member.id)

        if guild_id not in user_balance:
            user_balance[guild_id] = {}

        if user_id == recipient_id:
            await interaction.response.send_message("❌ 您不能转账给自己。", ephemeral=True)
            return
        if recipient_id == str(bot.user.id):
            await interaction.response.send_message("❌ 您不能转账给机器人。", ephemeral=True)
            return
        if amount <= 0:
            await interaction.response.send_message("❌ 转账金额必须大于 0。", ephemeral=True)
            return
        if user_balance[guild_id].get(user_id, 0) < amount:
            await interaction.response.send_message("❌ 您的余额不足。", ephemeral=True)
            return

        user_balance[guild_id][user_id] -= amount
        user_balance[guild_id][recipient_id] = user_balance[guild_id].get(recipient_id, 0) + amount

        save_yaml("balance.yml", user_balance)

        embed = discord.Embed(
            title="💸 转账成功！",
            description=(
                f"**{interaction.user.mention}** 给 **{member.mention}** 转账了 **{amount} 幽靈幣**。\n\n"
                "🎉 感谢您的使用！"
            ),
            color=discord.Color.green()
        )
        embed.set_footer(text="如有疑问，请联系管理员")

        await interaction.response.send_message(embed=embed, ephemeral=False)
        logging.info(f"转账成功: {interaction.user.id} -> {member.id} 金额: {amount}")

    except Exception as e:
        logging.error(f"执行 pay 命令时发生错误: {e}")
        await interaction.response.send_message("❌ 执行命令时发生错误，请稍后再试。", ephemeral=True)

@bot.slash_command(name="addmoney", description="给用户增加幽靈幣（特定用户专用）")
async def addmoney(interaction: discord.Interaction, member: discord.Member, amount: int):
    if interaction.user.id != AUTHOR_ID:
        await interaction.response.send_message("❌ 您没有权限执行此操作。", ephemeral=True)
        return

    user_balance = load_yaml("balance.yml")
    guild_id = str(interaction.guild.id)
    recipient_id = str(member.id)

    if guild_id not in user_balance:
        user_balance[guild_id] = {}

    if recipient_id == str(bot.user.id):
        await interaction.response.send_message("❌ 不能给机器人增加幽靈幣。", ephemeral=True)
        return

    if amount > 100000:
        await interaction.response.send_message("❌ 单次添加金额不能超过 **100,000 幽靈幣**。", ephemeral=True)
        return

    user_balance[guild_id][recipient_id] = user_balance[guild_id].get(recipient_id, 0) + amount
    save_yaml("balance.yml", user_balance)

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

    user_balance = load_yaml("balance.yml")
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
    await interaction.response.defer(thinking=True)

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
        deleted = await interaction.channel.purge(
            limit=amount,
            check=lambda m: m.created_at >= cutoff_date
        )

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
            description=f"發生錯誤：{e}",
            color=0xFF0000
        )
        await interaction.followup.send(embed=embed)
    except Exception as e:
        embed = discord.Embed(
            title="❌ 清理失敗",
            description="發生未知錯誤，請稍後再試。",
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

@bot.slash_command(name="ping", description="測試訊息讀取和返回延遲")
async def ping(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📊 延遲測試中...",
        description="正在測試 Discord API 每秒讀取訊息和返回延遲...",
        color=discord.Color.blurple()
    )

    await interaction.response.defer()
    message = await interaction.followup.send(embed=embed)

    iterations = 10
    total_time = 0

    for i in range(iterations):
        start_time = time.time()
        await message.edit(embed=discord.Embed(
            title="📊 延遲測試中...",
            description=f"正在測試中... 第 {i + 1}/{iterations} 次",
            color=discord.Color.blurple()
        ))
        end_time = time.time()
        total_time += (end_time - start_time) * 1000

    avg_delay = total_time / iterations

    if avg_delay <= 100:
        embed_color = discord.Color.teal()
    elif 100 < avg_delay <= 200:
        embed_color = discord.Color.gold()
    else:
        embed_color = discord.Color.red()

    result_embed = discord.Embed(
        title="📊 延遲測試結果",
        description=(
            f"**WebSocket 延遲**: `{bot.latency * 1000:.2f} 毫秒`\n"
            f"**Discord API 訊息編輯平均延遲**: `{avg_delay:.2f} 毫秒`"
        ),
        color=embed_color
    )
    result_embed.set_footer(text="測試完成，數據僅供參考。")

    await message.edit(embed=result_embed)

class ServerInfoView(View):
    def __init__(self, guild_icon_url):
        super().__init__(timeout=180)
        self.guild_icon_url = guild_icon_url

    
    @discord.ui.button(label="點擊獲取群組圖貼", style=discord.ButtonStyle.primary)
    async def send_guild_icon(self, button: Button, interaction: Interaction):
        try:
            print(f"按鈕觸發成功, Guild Icon URL: {self.guild_icon_url}")
            if self.guild_icon_url:
                await interaction.response.send_message(self.guild_icon_url, ephemeral=True)
            else:
                await interaction.response.send_message("這個群組沒有圖像。", ephemeral=True)
        except Exception as e:
            print(f"按鈕互動錯誤: {e}")
            await interaction.followup.send("發生錯誤，請稍後再試。", ephemeral=True)

@bot.slash_command(name="server_info", description="獲取群組資訊")
async def server_info(interaction: Interaction):
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("這個指令只能在群組中使用。", ephemeral=True)
        return

    guild_name = guild.name
    guild_id = guild.id
    member_count = guild.member_count
    bot_count = sum(1 for member in guild.members if member.bot) if guild.members else "未知"
    role_count = len(guild.roles)
    created_at = f"<t:{int(guild.created_at.timestamp())}:F>"
    guild_icon_url = guild.icon.url if guild.icon else None

    embed_color = guild.me.color if guild.me.color else discord.Color.blue()

    embed = discord.Embed(title="群組資訊", color=embed_color)
    embed.add_field(name="群組名字", value=guild_name, inline=False)
    embed.add_field(name="群組ID", value=guild_id, inline=False)
    embed.add_field(name="成員數量", value=f"{member_count} (機器人: {bot_count})", inline=True)
    embed.add_field(name="身分組數量", value=role_count, inline=True)
    embed.add_field(name="群組創建時間", value=created_at, inline=False)
    if guild_icon_url:
        embed.set_thumbnail(url=guild_icon_url)

    view = ServerInfoView(guild_icon_url)
    await interaction.response.send_message(embed=embed, view=view)

@bot.slash_command(name="user_info", description="获取用户的基本信息")
async def userinfo(ctx: discord.ApplicationContext, user: discord.Member = None):
    user = user or ctx.author

    embed = discord.Embed(title="用户信息", color=discord.Color.from_rgb(255, 182, 193))
    embed.set_thumbnail(url=user.display_avatar.url)

    embed.add_field(name="名称", value=f"{user.name}#{user.discriminator}", inline=True)
    embed.add_field(name="ID", value=user.id, inline=True)
    embed.add_field(name="服务器昵称", value=user.nick or "无", inline=True)
    embed.add_field(
        name="账号创建日期", 
        value=user.created_at.replace(tzinfo=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        inline=True
    )
    embed.add_field(
        name="加入服务器日期",
        value=user.joined_at.replace(tzinfo=timezone.utc).strftime("%Y-%m-%d %H:%M:%S") if user.joined_at else "无法获取",
        inline=True
    )
    embed.add_field(name="最高角色", value=user.top_role.mention if user.top_role else "无", inline=True)
    embed.add_field(name="Bot?", value="是" if getattr(user, "bot", False) else "否", inline=True)

    await ctx.respond(embed=embed)

class FeedbackButtons(View):
    def __init__(self, description: str = None):
        super().__init__(timeout=None)
        self.description = description if description else "未提供描述"

    @discord.ui.button(label="指令錯誤或無回應", style=discord.ButtonStyle.primary)
    async def command_error(self, button: Button, interaction: discord.Interaction):
        await self.handle_feedback(interaction, "指令錯誤或無回應")

    @discord.ui.button(label="機器人訊息問題", style=discord.ButtonStyle.primary)
    async def message_issue(self, button: Button, interaction: discord.Interaction):
        await self.handle_feedback(interaction, "機器人訊息問題")

    @discord.ui.button(label="迷你遊戲系統錯誤", style=discord.ButtonStyle.primary)
    async def minigame_error(self, button: Button, interaction: discord.Interaction):
        await self.handle_feedback(interaction, "迷你遊戲系統錯誤")

    @discord.ui.button(label="其他問題", style=discord.ButtonStyle.primary)
    async def other_issue(self, button: Button, interaction: discord.Interaction):
        await self.handle_feedback(interaction, "其他問題")

    async def handle_feedback(self, interaction: discord.Interaction, category: str):
        feedback_channel_id = 1308316531444158525  # 替換為你的反饋頻道ID
        feedback_channel = bot.get_channel(feedback_channel_id)

        if feedback_channel is None:
            await interaction.response.send_message(
                "反饋頻道尚未正確設置，請聯繫作者。", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="收到新的反饋",
            description=(
                f"**分類:** {category}\n"
                f"**用戶:** {interaction.user.mention}\n"
                f"**描述:** {self.description}"
            ),
            color=discord.Color.from_rgb(255, 182, 193)
        )
        embed.timestamp = discord.utils.utcnow()

        await feedback_channel.send(embed=embed)
        await interaction.response.send_message("感謝您的反饋！", ephemeral=True)

@bot.slash_command(name="feedback", description="提交您的反饋或建議！")
async def feedback(ctx: discord.ApplicationContext, description: str = None):
    """Command to collect user feedback with category buttons."""
    if description:
        await ctx.respond(
            f"您提供的反饋描述：{description}\n請使用以下按鈕選擇您的反饋類別：",
            view=FeedbackButtons(description=description),
            ephemeral=True
        )
    else:
        await ctx.respond(
            "請使用以下按鈕選擇您的反饋類別，並補充具體描述：",
            view=FeedbackButtons(),
            ephemeral=True
        )

@bot.slash_command(name="trivia", description="動漫 Trivia 問題挑戰")
async def trivia(interaction: discord.Interaction):
    question_data = get_random_question()

    question = question_data['question']
    choices = question_data['choices']
    answer = question_data['answer']

    view = discord.ui.View()
    for choice in choices:
        button = discord.ui.Button(label=choice)

        async def button_callback(interaction: discord.Interaction, choice=choice):
            if choice == answer:
                await interaction.response.send_message(f"正確！答案是：{answer}", ephemeral=True)
            else:
                await interaction.response.send_message(f"錯誤！正確答案是：{answer}", ephemeral=True)

            await interaction.message.edit(content=f"問題：{question}\n\n正確答案是：{answer}", view=None)

        button.callback = button_callback
        view.add_item(button)

    await interaction.response.send_message(f"問題：{question}", view=view)

@bot.slash_command(name="timeout", description="禁言指定的使用者（以分鐘為單位）")
async def timeout(interaction: discord.Interaction, member: discord.Member, duration: int):
    if interaction.user.guild_permissions.moderate_members:
        # 延迟响应，避免超时
        await interaction.response.defer(ephemeral=True)

        # 检查机器人权限
        bot_member = interaction.guild.me
        if not bot_member.guild_permissions.moderate_members:
            embed = discord.Embed(
                title="❌ 操作失敗",
                description="機器人缺少禁言權限，請確認角色權限設置。",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # 检查目标用户权限
        if member.top_role >= bot_member.top_role:
            embed = discord.Embed(
                title="❌ 操作失敗",
                description=f"無法禁言 {member.mention}，因為他們的角色高於或等於機器人。",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        try:
            # 計算禁言結束時間
            mute_time = datetime.utcnow() + timedelta(minutes=duration)
            await member.timeout(mute_time, reason=f"Timeout by {interaction.user} for {duration} minutes")
            
            # 成功禁言的回應
            embed = discord.Embed(
                title="⛔ 成員禁言",
                description=f"{member.mention} 已被禁言 **{duration} 分鐘**。",
                color=discord.Color.dark_red()
            )
            embed.set_footer(text="請遵守伺服器規則")
            await interaction.followup.send(embed=embed)
        except discord.Forbidden:
            embed = discord.Embed(
                title="❌ 無法禁言",
                description=f"權限不足，無法禁言 {member.mention} 或回應訊息。",
                color=discord.Color.red()
            )
            try:
                await interaction.followup.send(embed=embed, ephemeral=True)
            except discord.Forbidden:
                print("無法回應權限不足的錯誤訊息，請檢查機器人權限。")
        except discord.HTTPException as e:
            # 其他 API 錯誤
            embed = discord.Embed(
                title="❌ 禁言失敗",
                description=f"操作失敗：{e}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        # 使用者權限不足
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
            await member.timeout(None)  # 解除禁言
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
            await interaction.response.send_message(embed=embed, ephemeral=True)
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

@bot.slash_command(name="system_status", description="检查机器人的系统资源使用情况")
async def system_status(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ 你没有权限使用此命令。此命令仅限管理员使用。", ephemeral=True)
        return

    await interaction.response.defer()

    cpu_percent = psutil.cpu_percent(interval=1)
    memory_info = psutil.virtual_memory()
    total_memory = memory_info.total / (1024 ** 3)
    used_memory = memory_info.used / (1024 ** 3)
    free_memory = memory_info.available / (1024 ** 3)

    status_message = (
        f"**🖥️ 系统资源使用情况：**\n"
        f"```css\n"
        f"CPU 使用率  : {cpu_percent}%\n"
        f"总内存      : {total_memory:.2f} GB\n"
        f"已用内存    : {used_memory:.2f} GB\n"
        f"可用内存    : {free_memory:.2f} GB\n"
        f"```\n"
    )

    await interaction.followup.send(status_message)

class ShopView(discord.ui.View):
    def __init__(self, user_id, fish_list, guild_id):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.fish_list = fish_list
        self.guild_id = guild_id

        self.add_item(discord.ui.Button(
            label="出售漁獲",
            style=discord.ButtonStyle.secondary,
            custom_id="sell_fish"
        ))
        self.children[-1].callback = self.show_sell_fish

        self.add_item(discord.ui.Button(
            label="購買漁具",
            style=discord.ButtonStyle.primary,
            custom_id="buy_gear"
        ))
        self.children[-1].callback = self.show_gear_shop

    async def show_sell_fish(self, interaction: discord.Interaction):
        if not self.fish_list:
            embed = discord.Embed(
                title="🎣 沒有漁獲可以出售",
                description="看來你今天還沒釣到任何魚哦！快去垂釣吧，祝你大豐收！",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title="🎣 出售漁獲",
            description="請從你的漁獲中選擇你想出售的魚，換取幽靈幣！",
            color=discord.Color.gold()
        )
        embed.set_footer(text="每條魚都有它的價值，快來看看吧！")

        await interaction.response.edit_message(
            content=None,
            embed=embed,
            view=SellFishView(self.user_id, self.fish_list, self.guild_id)
        )

    async def show_gear_shop(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🛠️ 漁具購買商店",
            description=(
                "歡迎光臨！在這裡你可以選擇各種優質漁具，讓你的釣魚體驗更加精彩！\n\n"
                "🎉 **特別優惠**: 購買新款魚竿可獲得附加屬性加成！"
            ),
            color=discord.Color.green()
        )
        embed.set_footer(text="選擇適合你的漁具，快樂釣魚吧！")

        await interaction.response.edit_message(
            content=None,
            embed=embed,
            view=GearShopView(self.user_id, self.guild_id)
        )

class SellFishView(discord.ui.View):
    BASE_PRICES = {
        'common': 50,
        'uncommon': 120,
        'rare': 140,
        'legendary': 1000,
        'deify': 4200,
        'unknown': 2000
    }

    def __init__(self, user_id, fish_list, guild_id):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.fish_list = fish_list[:25]
        self.guild_id = guild_id

        self.update_fish_menu()

    def update_fish_menu(self):
        """動態生成選擇菜單並添加到視圖"""
        if not self.fish_list:
            self.add_item(discord.ui.Button(
                label="無魚可售",
                style=discord.ButtonStyle.gray,
                disabled=True
            ))
            return

        options = [
            discord.SelectOption(
                label=f"{fish['name']} - 大小: {fish['size']:.2f} 公斤",
                description=f"估價: {self.calculate_fish_value(fish)} 幽靈幣",
                value=str(index)
            )
            for index, fish in enumerate(self.fish_list)
        ]

        select = discord.ui.Select(
            placeholder="選擇你想出售的魚",
            options=options,
            custom_id="fish_select"
        )
        select.callback = self.select_fish_to_sell
        self.add_item(select)

    def calculate_fish_value(self, fish):
        """計算魚的價值"""
        base_value = self.BASE_PRICES.get(fish['rarity'], 50)
        return int(base_value * fish['size'])

    async def select_fish_to_sell(self, interaction: discord.Interaction):
        selected_fish_index = int(interaction.data['values'][0])
        selected_fish = self.fish_list[selected_fish_index]

        embed = discord.Embed(
            title="確認出售魚",
            description=f"你選擇了出售以下漁獲：\n\n"
                        f"**名稱**: {selected_fish['name']}\n"
                        f"**大小**: {selected_fish['size']:.2f} 公斤\n"
                        f"**估價**: {self.calculate_fish_value(selected_fish)} 幽靈幣",
            color=discord.Color.blue()
        )
        embed.set_footer(text="確認交易或取消操作")
    
        await interaction.response.edit_message(
            content="> 🎣 **請確認是否出售：**",
            embed=embed,
            view=ConfirmSellView(self.user_id, selected_fish, self.fish_list, self.guild_id)
        )

class ConfirmSellView(discord.ui.View):
    def __init__(self, user_id, selected_fish, fish_list, guild_id):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.selected_fish = selected_fish
        self.fish_list = fish_list
        self.guild_id = guild_id

    def calculate_fish_value(self, fish):
        """計算魚的價值"""
        base_value = SellFishView.BASE_PRICES.get(fish['rarity'], 50)
        return int(base_value * fish['size'])

    @discord.ui.button(label="確認出售", style=discord.ButtonStyle.success)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        fish_value = self.calculate_fish_value(self.selected_fish)

        try:
            with open('fishiback.yml', 'r', encoding='utf-8') as file:
                fish_back = yaml.safe_load(file) or {}
        except FileNotFoundError:
            fish_back = {}

        user_data = fish_back.get(self.user_id, {'coins': 0, 'caught_fish': []})
        user_data['coins'] = user_data.get('coins', 0) + fish_value
        user_data['caught_fish'] = [
            fish for fish in self.fish_list if fish != self.selected_fish
        ]
        fish_back[self.user_id] = user_data

        with open('fishiback.yml', 'w', encoding='utf-8') as file:
            yaml.dump(fish_back, file)

        updated_fish_list = user_data['caught_fish']

        embed = discord.Embed(
            title="成功出售！",
            description=f"你成功出售了 **{self.selected_fish['name']}**！\n\n"
                        f"**大小**: {self.selected_fish['size']:.2f} 公斤\n"
                        f"**獲得金額**: {fish_value} 幽靈幣\n\n"
                        f"你的新餘額已更新！",
            color=discord.Color.green()
        )
        embed.set_footer(text="感謝您的交易！")

        await interaction.response.edit_message(
            content=f"> 🎣 **成功出售 {self.selected_fish['name']}，獲得 {fish_value} 幽靈幣！**",
            embed=embed,
            view=SellFishView(self.user_id, updated_fish_list, self.guild_id)
        )

    @discord.ui.button(label="取消", style=discord.ButtonStyle.danger)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="> 🎣 **請選擇並出售你的漁獲：**",
            view=SellFishView(self.user_id, self.fish_list, self.guild_id)
        )

class GearShopView(discord.ui.View):
    RODS = [
        {"name": "普通釣竿", "price": 10},
        {"name": "高級釣竿", "price": 5000},
        {"name": "傳說釣竿", "price": 20000},
        {"name": "神話釣竿", "price": 50000}
    ]

    def __init__(self, user_id, guild_id):
        super().__init__(timeout=None)
        self.user_id = str(user_id)
        self.guild_id = str(guild_id)

        buy_rod_button = discord.ui.Button(
            label="購買釣竿",
            style=discord.ButtonStyle.primary,
            custom_id="buy_rod"
        )
        buy_rod_button.callback = self.buy_rod_menu
        self.add_item(buy_rod_button)

    async def buy_rod_menu(self, interaction: discord.Interaction):
        try:
            with open('user_rod.yml', 'r', encoding='utf-8') as file:
                user_rod = yaml.safe_load(file) or {}
        except FileNotFoundError:
            user_rod = {}

        if self.guild_id not in user_rod:
            user_rod[self.guild_id] = {}

        if self.user_id not in user_rod[self.guild_id]:
            user_rod[self.guild_id][self.user_id] = {'rods': [], 'current_rod': None}

        user_rod_data = user_rod[self.guild_id][self.user_id]
        if not isinstance(user_rod_data, dict):
            user_rod[self.guild_id][self.user_id] = {'rods': [], 'current_rod': None}
            user_rod_data = user_rod[self.guild_id][self.user_id]

        rods_owned = [rod['name'] for rod in user_rod_data['rods']]
        options = [
            discord.SelectOption(
                label=rod['name'],
                description=f"價格: {rod['price']} 幽靈幣",
                value=rod['name']
            )
            for rod in self.RODS if rod['name'] not in rods_owned
        ]

        if not options:
            await interaction.response.send_message("🎣 你已購買了所有可用的釣竿！", ephemeral=True)
            return

        select = discord.ui.Select(
            placeholder="選擇你想購買的釣竿",
            options=options,
            custom_id="rod_select"
        )
        select.callback = lambda inter: self.buy_rod(inter, user_rod, user_rod_data)

        view = discord.ui.View()
        view.add_item(select)

        await interaction.response.send_message("請選擇你想購買的釣竿：", view=view, ephemeral=False)

    async def buy_rod(self, interaction: discord.Interaction, user_rod, user_rod_data):
        rod_name = interaction.data['values'][0]
        selected_rod = next(rod for rod in self.RODS if rod['name'] == rod_name)

        try:
            with open('balance.yml', 'r', encoding='utf-8') as file:
                balance = yaml.safe_load(file) or {}
        except FileNotFoundError:
            balance = {}

        guild_balance_data = balance.get(self.guild_id, {})
        user_balance = guild_balance_data.get(self.user_id, 0)

        if user_balance < selected_rod['price']:
            await interaction.response.send_message("⚠️ 你的幽靈幣不足，無法購買該釣竿！", ephemeral=True)
            return

        guild_balance_data[self.user_id] = user_balance - selected_rod['price']
        balance[self.guild_id] = guild_balance_data
        with open('balance.yml', 'w', encoding='utf-8') as file:
            yaml.dump(balance, file)

        user_rod_data['rods'].append({'name': rod_name})
        user_rod_data['current_rod'] = rod_name
        user_rod[self.guild_id][self.user_id] = user_rod_data

        with open('user_rod.yml', 'w', encoding='utf-8') as file:
            yaml.dump(user_rod, file)

        await interaction.response.send_message(
            f"✅ 成功購買 **{rod_name}**！\n你的餘額剩餘：{guild_balance_data[self.user_id]} 幽靈幣。",
            ephemeral=True
        )

@bot.slash_command(name="fish_shop", description="查看釣魚商店並購買釣竿")
async def fish_shop(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    guild_id = str(interaction.guild.id)

    try:
        with open('fishiback.yml', 'r', encoding='utf-8') as file:
            fish_back = yaml.safe_load(file) or {}
    except FileNotFoundError:
        fish_back = {}

    if user_id not in fish_back:
        fish_back[user_id] = {'caught_fish': []}
        with open('fishiback.yml', 'w', encoding='utf-8') as file:
            yaml.dump(fish_back, file)

    user_fish_list = fish_back[user_id]['caught_fish']

    embed = discord.Embed(
        title="🎣 歡迎來到釣魚商店",
        description=(
            "我們以誠信和誠實經營為核心價值，致力於為每位垂釣者提供高品質的服務。\n\n"
            "請選擇以下操作："
        ),
        color=discord.Color.gold()
    )
    embed.set_footer(text="商店物品供給為 釣魚協會")

    await interaction.response.send_message(
        embed=embed,
        view=ShopView(user_id, user_fish_list, guild_id)
    )

def get_cooldown(user_rod):
    """根據魚竿計算冷卻時間"""
    cooldown_base = 5
    cooldown_reduction = {
        "普通釣竿": 1.0,
        "高級釣竿": 0.8,
        "傳說釣竿": 0.6,
        "神話釣竿": 0.4
    }
    multiplier = cooldown_reduction.get(user_rod, 1.0)
    return cooldown_base * multiplier

def catch_fish(user_rod):
    """根據魚竿隨機捕獲一條魚"""
    rarity_weights = {
        "common": 50,
        "uncommon": 35,
        "rare": 25,
        "legendary": 15,
        "deify": 10,
        "unknown": 10
    }

    rod_multiplier = {
        "普通釣竿": 1.0,
        "高級釣竿": 2.1,
        "傳說釣竿": 3.5,
        "神話釣竿": 4.0
    }
    multiplier = rod_multiplier.get(user_rod, 1.0)

    possible_fish = fish_data['fish']
    weights = [
        rarity_weights.get(fish['rarity'], 1) * multiplier
        for fish in possible_fish
    ]

    selected_fish = random.choices(possible_fish, weights=weights, k=1)[0]

    min_size = float(selected_fish['min_size'])
    max_size = float(selected_fish['max_size'])
    selected_fish['size'] = round(random.uniform(min_size, max_size), 2)

    return selected_fish

class FishView(discord.ui.View):
    def __init__(self, fish, user_id, rod):
        super().__init__(timeout=30)
        self.fish = fish
        self.user_id = user_id
        self.rod = rod
        self.message = None

    async def on_timeout(self):
        """當釣魚互動超時時處理"""
        for child in self.children:
            child.disabled = True
        if self.message:
            timeout_embed = discord.Embed(
                title="⏳ 時間已過！",
                description="你錯過了此次的釣魚機會！",
                color=discord.Color.dark_gray()
            )
            await self.message.edit(embed=timeout_embed, view=None)

    @discord.ui.button(label="保存漁獲", style=discord.ButtonStyle.primary)
    async def save_fish(self, interaction: discord.Interaction, button: discord.ui.Button):
        """保存捕獲的魚到用戶的存檔"""
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("🚫 這不是你的操作，請使用 `/fish` 開始釣魚。", ephemeral=True)
            return

        if not os.path.exists('fishiback.yml'):
            with open('fishiback.yml', 'w', encoding='utf-8') as file:
                yaml.dump({}, file)

        with open('fishiback.yml', 'r', encoding='utf-8') as file:
            fish_back = yaml.safe_load(file) or {}

        if self.user_id not in fish_back:
            fish_back[self.user_id] = {'balance': 0, 'caught_fish': []}

        fish_back[self.user_id]['caught_fish'].append(self.fish)

        with open('fishiback.yml', 'w', encoding='utf-8') as file:
            yaml.dump(fish_back, file)

        await interaction.response.edit_message(
            content=f"✅ 你保存了 {self.fish['name']} ({self.fish['size']} 公斤) 到你的漁獲列表中！",
            view=None
        )

    @discord.ui.button(label="再釣一次", style=discord.ButtonStyle.secondary)
    async def fish_again(self, interaction: discord.Interaction, button: discord.ui.Button):
        """讓用戶再釣一次魚"""
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("🚫 這不是你的操作，請使用 `/fish` 開始釣魚。", ephemeral=True)
            return

        cooldown_time = get_cooldown(self.rod)
        if self.user_id in cooldowns and time.time() - cooldowns[self.user_id] < cooldown_time:
            remaining_time = cooldown_time - (time.time() - cooldowns[self.user_id])
            await interaction.response.send_message(f"⏳ 冷卻中：{remaining_time:.1f} 秒", ephemeral=True)
            return

        cooldowns[self.user_id] = time.time()
        new_fish = catch_fish(self.rod)

        embed = generate_fish_embed(new_fish)
        self.message = await interaction.response.edit_message(embed=embed, view=FishView(new_fish, self.user_id, self.rod))

def generate_fish_embed(fish):
    """根據魚生成嵌入消息"""
    rarity_colors = {
        "common": 0x00FF00,
        "uncommon": 0x0000FF,
        "rare": 0xFF00FF,
        "legendary": 0xFFD700,
        "deify": 0xFF4500,
        "unknown": 0x4B0082
    }
    color = rarity_colors.get(fish['rarity'], 0xFFFFFF)

    embed = discord.Embed(
        title=f"🎣 你捕到了一條 {fish['rarity'].capitalize()} 的 {fish['name']}！",
        description=f"大小：**{fish['size']} 公斤**",
        color=color
    )
    return embed

@bot.slash_command(name="fish", description="進行一次釣魚")
async def fish(interaction: discord.Interaction):
    user_id = str(interaction.user.id)

    if not os.path.exists('user_rod.yml'):
        with open('user_rod.yml', 'w', encoding='utf-8') as file:
            yaml.dump({}, file)

    with open('user_rod.yml', 'r', encoding='utf-8') as file:
        user_rods = yaml.safe_load(file) or {}

    user_data = user_rods.get(user_id, {"current_rod": "普通釣竿"})
    current_rod = user_data.get("current_rod", "普通釣竿")

    cooldown_time = get_cooldown(current_rod)
    if user_id in cooldowns and time.time() - cooldowns[user_id] < cooldown_time:
        remaining_time = cooldown_time - (time.time() - cooldowns[user_id])
        await interaction.response.send_message(f"⏳ 冷卻中：{remaining_time:.1f} 秒", ephemeral=True)
        return

    cooldowns[user_id] = time.time()

    fish_caught = catch_fish(current_rod)
    embed = generate_fish_embed(fish_caught)

    message = await interaction.response.send_message(embed=embed, view=FishView(fish_caught, user_id, current_rod))

class RodView(discord.ui.View):
    def __init__(self, user_id, guild_id, available_rods, current_rod):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.guild_id = guild_id
        self.available_rods = available_rods
        self.current_rod = current_rod
        self.message = None

        select = discord.ui.Select(
            placeholder=f"🎣 目前釣竿: {current_rod}",
            options=[
                discord.SelectOption(
                    label=rod["name"],
                    value=f"{rod['name']}_{i}",
                    emoji=rod.get("emoji", "🎣")
                )
                for i, rod in enumerate(available_rods)
            ],
            custom_id="rod_select"
        )
        select.callback = self.switch_rod
        self.add_item(select)

    async def switch_rod(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("🚫 這不是你的設定菜單，請使用 `/fish_rod` 查看你的釣竿。", ephemeral=True)
            return

        if interaction.response.is_done():
            return

        selected_value = interaction.data['values'][0]
        selected_rod = selected_value.rsplit("_", 1)[0]

        RodView.update_user_rod_with_lock(self.guild_id, str(self.user_id), selected_rod)

        with open('user_rod.yml', 'r', encoding='utf-8') as file:
            user_rods = yaml.safe_load(file) or {}
        guild_data = user_rods.get(str(self.guild_id), {})
        user_data = guild_data.get(str(self.user_id), {})
        available_rods = user_data.get("rods", [{"name": "普通釣竿"}])
        current_rod = user_data.get("current_rod", "普通釣竿")

        embed = discord.Embed(
            title="釣竿切換",
            description=f"✅ 你已切換到: **{selected_rod}**",
            color=discord.Color.green()
        )
        await interaction.response.edit_message(
            embed=embed,
            view=RodView(self.user_id, self.guild_id, available_rods, current_rod)
        )

    @staticmethod
    def update_user_rod_with_lock(guild_id, user_id, new_rod):
        """使用文件鎖安全更新用戶的釣竿設定"""
        lock = FileLock("user_rod.yml.lock")
        with lock:
            try:
                with open('user_rod.yml', 'r', encoding='utf-8') as file:
                    user_rods = yaml.safe_load(file)
            except FileNotFoundError:
                user_rods = {}

            if guild_id not in user_rods:
                user_rods[guild_id] = {}
            if user_id not in user_rods[guild_id]:
                user_rods[guild_id][user_id] = {"rods": [{"name": "普通釣竿"}], "current_rod": "普通釣竿"}

            user_rods[guild_id][user_id]["current_rod"] = new_rod

            with open('user_rod.yml', 'w', encoding='utf-8') as file:
                yaml.dump(user_rods, file)

    async def on_timeout(self):
        """清除超时交互组件"""
        for child in self.children:
            child.disabled = True
        if self.message:
            await self.message.edit(view=self)

@bot.slash_command(name="fish_rod", description="查看並切換你的釣魚竿")
async def fish_rod(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    guild_id = str(interaction.guild_id)

    if not os.path.exists('user_rod.yml'):
        with open('user_rod.yml', 'w', encoding='utf-8') as file:
            yaml.dump({}, file)

    lock = FileLock("user_rod.yml.lock")
    with lock:
        with open('user_rod.yml', 'r', encoding='utf-8') as file:
            try:
                user_rods = yaml.safe_load(file) or {}
            except yaml.YAMLError:
                user_rods = {}

        if guild_id not in user_rods:
            user_rods[guild_id] = {}
        guild_data = user_rods[guild_id]
        if user_id not in guild_data:
            guild_data[user_id] = {
                "current_rod": "普通釣竿",
                "rods": [{"name": "普通釣竿"}]
            }
        else:
            user_data = guild_data[user_id]
            if isinstance(user_data.get("rods"), list):
                if all(isinstance(rod, str) for rod in user_data["rods"]):
                    user_data["rods"] = [{"name": rod} for rod in user_data["rods"]]
            else:
                user_data["rods"] = [{"name": "普通釣竿"}]

            if user_data.get("current_rod") not in [rod["name"] for rod in user_data["rods"]]:
                user_data["current_rod"] = "普通釣竿"

        with open('user_rod.yml', 'w', encoding='utf-8') as file:
            yaml.dump(user_rods, file)

    user_data = user_rods[guild_id][user_id]
    available_rods = user_data["rods"]
    current_rod = user_data["current_rod"]

    embed = discord.Embed(
        title="釣竿管理",
        description=(f"🎣 你現在使用的釣竿是: **{current_rod}**\n⬇️ 從下方選單選擇以切換釣竿！"),
        color=discord.Color.blue()
    )

    view = RodView(user_id, guild_id, available_rods, current_rod)

    await interaction.response.send_message(embed=embed, view=view)

    view.message = await interaction.followup.fetch_message(interaction.id)

@bot.slash_command(name="fish_back", description="查看你的漁獲")
async def fish_back(interaction: discord.Interaction):
    if not os.path.exists('fishiback.yml'):
        with open('fishiback.yml', 'w', encoding='utf-8') as file:
            yaml.dump({}, file)

    with open('fishiback.yml', 'r', encoding='utf-8') as file:
        fishing_data = yaml.safe_load(file)

    if fishing_data is None:
        fishing_data = {}

    user_id = str(interaction.user.id)

    if user_id in fishing_data and fishing_data[user_id].get('caught_fish'):
        caught_fish = fishing_data[user_id]['caught_fish']
        fish_list = "\n".join(
            [f"**{fish['name']}** - {fish['rarity']} ({fish['size']} 公斤)" for fish in caught_fish]
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
        try:
            await interaction.response.send_message("❌ 你還沒有捕到任何魚！", ephemeral=True)
        except discord.errors.NotFound:
            await interaction.channel.send(
                f"{interaction.user.mention} ❌ 查詢失敗，請重新嘗試 `/fish_back`！"
            )

def is_on_cooldown(user_id, cooldown_file, cooldown_hours):
    try:
        with open(cooldown_file, "r") as f:
            cooldowns = json.load(f)
    except FileNotFoundError:
        cooldowns = {}
    
    if str(user_id) in cooldowns:
        last_used = datetime.fromisoformat(cooldowns[str(user_id)])
        now = datetime.now()
        cooldown_period = timedelta(hours=cooldown_hours)
        if now < last_used + cooldown_period:
            remaining = last_used + cooldown_period - now
            remaining_time = f"{remaining.seconds // 3600}小時 {remaining.seconds % 3600 // 60}分鐘"
            return True, remaining_time
    
    return False, None

def update_cooldown(user_id, cooldown_file):
    try:
        with open(cooldown_file, "r") as f:
            cooldowns = json.load(f)
    except FileNotFoundError:
        cooldowns = {}
    
    cooldowns[str(user_id)] = datetime.now().isoformat()
    with open(cooldown_file, "w") as f:
        json.dump(cooldowns, f)

@bot.slash_command(name="draw_lots", description="抽取御神抽籤")
async def draw_lots_command(interaction: discord.Interaction):
    cooldown_file = "cooldowns.json"
    cooldown_hours = 5
    user_id = interaction.user.id
    
    on_cooldown, remaining_time = is_on_cooldown(user_id, cooldown_file, cooldown_hours)
    
    if on_cooldown:
        await interaction.response.send_message(f"你還在冷卻中，剩餘時間：{remaining_time}", ephemeral=True)
    else:
        await interaction.response.defer()
        result_text, color = draw_lots()
        
        embed = discord.Embed(
            title="🎋 抽籤結果 🎋",
            description=result_text,
            color=color
        )
        
        await interaction.followup.send(embed=embed)
        update_cooldown(user_id, cooldown_file)

# 斜綫help指令
@bot.slash_command(name="help", description="显示所有可用指令")
async def help(ctx: discord.ApplicationContext):
    embed_test = discord.Embed(
        title="⚠️ 測試員指令",
        description="> `shutdown` - 關閉機器人\n> `restart` - 重啓機器人",
        color=discord.Color.orange()
    )
    embed_economy = discord.Embed(
        title="💸 經濟系統",
        description="> `balance` - 用戶餘額\n> `work` - 工作\n> `pay` - 轉賬",
        color=discord.Color.from_rgb(255, 182, 193)
    )
    embed_admin = discord.Embed(
        title="🔒 管理員指令",
        description=(
            "> `ban` - 封鎖用戶\n> `kick` - 踢出用戶\n"
            "> `addmoney` - 添加金錢\n> `removemoney` - 移除金錢\n"
            "> `start_giveaway` - 開啓抽獎\n> `mute` - 禁言某位成員\n"
            "> `unmute` - 解除某位成員禁言"
        ),
        color=discord.Color.from_rgb(0, 51, 102)
    )
    embed_common = discord.Embed(
        title="🎉 普通指令",
        description=(
            "> `time` - 未活動的待機時間顯示\n> `ping` - 顯示機器人的回復延遲\n"
            "> `server_info` - 獲取伺服器資訊\n> `user_info` - 獲取用戶資訊\n"
            "> `feedback` - 回報錯誤\n> `trivia` - 問題挑戰(動漫)"
        ),
        color=discord.Color.green()
    )
    embed_fishing = discord.Embed(
        title="🎣 釣魚指令",
        description=(
            "> `fish` - 開啓悠閑釣魚時光\n> `fish_back` - 打開釣魚背包\n"
            "> `fish_shop` - 販售與購買魚具\n> `fish_rod` - 切換漁具"
        ),
        color=discord.Color.blue()
    )

    for embed in [embed_test, embed_economy, embed_admin, embed_common, embed_fishing]:
        embed.set_footer(text="更多指令即將推出，敬請期待...")

    options = [
        discord.SelectOption(label="普通指令", description="查看普通指令", value="common", emoji="🎉"),
        discord.SelectOption(label="經濟系統", description="查看經濟系統指令", value="economy", emoji="💸"),
        discord.SelectOption(label="管理員指令", description="查看管理員指令", value="admin", emoji="🔒"),
        discord.SelectOption(label="釣魚指令", description="查看釣魚相關指令", value="fishing", emoji="🎣"),
        discord.SelectOption(label="測試員指令", description="查看測試員指令", value="test", emoji="⚠️"),
    ]

    async def select_callback(interaction: discord.Interaction):
        selected_value = select.values[0]
        embeds = {
            "common": embed_common,
            "economy": embed_economy,
            "admin": embed_admin,
            "fishing": embed_fishing,
            "test": embed_test
        }
        selected_embed = embeds.get(selected_value, embed_common)
        await interaction.response.edit_message(embed=selected_embed)

    select = Select(
        placeholder="選擇指令分類...",
        options=options
    )
    select.callback = select_callback

    # 超時處理 View
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
                        content="此選單已過期，請重新輸入 `/help` 以獲取指令幫助。",
                        view=self
                    )
            except discord.NotFound:
                print("原始訊息未找到，可能已被刪除。")

    view = TimeoutView()
    view.add_item(select)

    message = await ctx.respond(
        content="以下是目前可用指令的分類：",
        embed=embed_common,
        view=view
    )
    view.message = await message.original_response()

# 這裏是discord硬編碼部分的token如果沒有正確讀取到token的話會在終端機顯示
# 終端機的部分會直接顯示 “機器人啟動時發生錯誤: {e}” “{e}”代表著什麽地方的錯誤
# 如果token沒有正確讀取到的話會在終端機顯示 “無效的機器人令牌。請檢查 TOKEN。”
try:
    bot.run(TOKEN, reconnect=True)
except discord.LoginFailure:
    print("無效的機器人令牌。請檢查 TOKEN。")
except Exception as e:
    print(f"機器人啟動時發生錯誤: {e}")
