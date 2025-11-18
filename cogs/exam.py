# exam.py (UI 優化版 / 冷卻時間顯示為「具體時間點」)

import discord
from discord import app_commands
from discord.ext import commands
import psycopg2
import os
import random
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("EXTERNAL_DATABASE_URL")

# -----------------------------------------------
# ✨ [功能更新] 修改 init_db
# -----------------------------------------------
def init_db():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    # 1. 建立基礎 Tables (若不存在)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id SERIAL PRIMARY KEY,
            question TEXT NOT NULL,
            option1 TEXT NOT NULL,
            option2 TEXT NOT NULL,
            option3 TEXT NOT NULL,
            option4 TEXT NOT NULL,
            answer INTEGER NOT NULL
        );
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS exam_settings (
            id INT PRIMARY KEY,
            question_amount INT NOT NULL DEFAULT 5,
            failure_cooldown_minutes INT NOT NULL DEFAULT 0,
            exam_room_id BIGINT,
            add_exam_room_id BIGINT,
            manage_exam_role_id BIGINT,
            graduater_role_id BIGINT
        );
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_cooldowns (
            user_id BIGINT PRIMARY KEY,
            cooldown_until TIMESTAMP
        );
    """)

    # 2. 確保設定表有預設值
    cur.execute("""
        INSERT INTO exam_settings (id, question_amount, failure_cooldown_minutes)
        VALUES (1, 5, 0)
        ON CONFLICT (id) DO NOTHING;
    """)

    # 3. 資料庫遷移
    new_columns = [
        ("exam_room_id", "BIGINT"),
        ("add_exam_room_id", "BIGINT"),
        ("manage_exam_role_id", "BIGINT"),
        ("graduater_role_id", "BIGINT"),
        ("failure_cooldown_minutes", "INT NOT NULL DEFAULT 0")
    ]
    
    for col_name, col_type in new_columns:
        try:
            cur.execute(f"ALTER TABLE exam_settings ADD COLUMN IF NOT EXISTS {col_name} {col_type};")
        except Exception:
            conn.rollback()
        else:
            conn.commit()

    conn.commit()
    cur.close()
    conn.close()

init_db()


class Exam(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ---------------------------------------------------------
    # 🛠️ 輔助方法：讀取設定
    # ---------------------------------------------------------
    def get_settings(self):
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("""
            SELECT question_amount, failure_cooldown_minutes, 
                   exam_room_id, add_exam_room_id, 
                   manage_exam_role_id, graduater_role_id 
            FROM exam_settings WHERE id = 1;
        """)
        row = cur.fetchone()
        cur.close()
        conn.close()
        
        if row:
            return {
                "question_amount": row[0],
                "failure_cooldown_minutes": row[1],
                "exam_room_id": row[2],
                "add_exam_room_id": row[3],
                "manage_exam_role_id": row[4],
                "graduater_role_id": row[5]
            }
        return None

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        send_method = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
        try:
            if isinstance(error, app_commands.MissingPermissions):
                await send_method(f"❌ 你需要管理員權限才能使用此指令！", ephemeral=True)
            elif "RangeError" in str(type(error)):
                 await send_method(f"❌ 數值超出允許範圍！", ephemeral=True)
            else:
                pass
        except Exception as e:
            print(f"錯誤處理器發生錯誤: {e}")

    # ---------------------------------------------------------
    # ⚙️ 管理員設定指令
    # ---------------------------------------------------------

    @app_commands.command(name="set_exam_room", description="設定考試專用頻道")
    @app_commands.default_permissions(administrator=True)
    async def set_exam_room(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await interaction.response.defer(ephemeral=True)
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("UPDATE exam_settings SET exam_room_id = %s WHERE id = 1;", (channel.id,))
        conn.commit()
        cur.close()
        conn.close()
        await interaction.followup.send(f"✅ 已將 **考試頻道** 設定為：{channel.mention}")

    @app_commands.command(name="set_manage_room", description="設定新增/管理題目的頻道")
    @app_commands.default_permissions(administrator=True)
    async def set_manage_room(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await interaction.response.defer(ephemeral=True)
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("UPDATE exam_settings SET add_exam_room_id = %s WHERE id = 1;", (channel.id,))
        conn.commit()
        cur.close()
        conn.close()
        await interaction.followup.send(f"✅ 已將 **管理題目頻道** 設定為：{channel.mention}")

    @app_commands.command(name="set_manage_role", description="設定考官(管理題目)的身分組")
    @app_commands.default_permissions(administrator=True)
    async def set_manage_role(self, interaction: discord.Interaction, role: discord.Role):
        await interaction.response.defer(ephemeral=True)
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("UPDATE exam_settings SET manage_exam_role_id = %s WHERE id = 1;", (role.id,))
        conn.commit()
        cur.close()
        conn.close()
        await interaction.followup.send(f"✅ 已將 **考官身分組** 設定為：{role.mention}")

    @app_commands.command(name="set_graduate_role", description="設定考試通過後給予的身分組")
    @app_commands.default_permissions(administrator=True)
    async def set_graduate_role(self, interaction: discord.Interaction, role: discord.Role):
        await interaction.response.defer(ephemeral=True)
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("UPDATE exam_settings SET graduater_role_id = %s WHERE id = 1;", (role.id,))
        conn.commit()
        cur.close()
        conn.close()
        await interaction.followup.send(f"✅ 已將 **畢業身分組** 設定為：{role.mention}")

    @app_commands.command(name="set_exam_amount", description="設定考試題目數量")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(amount="題目數量 (1-999)")
    async def set_exam_amount(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 999]):
        await interaction.response.defer(ephemeral=True)
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("UPDATE exam_settings SET question_amount = %s WHERE id = 1;", (amount,))
        conn.commit()
        cur.close()
        conn.close()
        await interaction.followup.send(f"✅ 考試題目數量已設為 **{amount}** 題。")

    @app_commands.command(name="set_exam_cooldown", description="設定考試失敗後的冷卻時間 (分鐘)")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(minutes="冷卻分鐘數 (0 代表無冷卻)")
    async def set_exam_cooldown(self, interaction: discord.Interaction, minutes: app_commands.Range[int, 0, 1440]):
        await interaction.response.defer(ephemeral=True)
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("UPDATE exam_settings SET failure_cooldown_minutes = %s WHERE id = 1;", (minutes,))
        conn.commit()
        cur.close()
        conn.close()
        await interaction.followup.send(f"✅ 考試失敗冷卻時間已設為 **{minutes}** 分鐘。(設為 0 可立即解除所有冷卻)")

    # ---------------------------------------------------------
    # 📋 題目管理指令
    # ---------------------------------------------------------

    async def check_manager_access(self, interaction: discord.Interaction, settings):
        if not settings:
            await interaction.followup.send("❌ 系統尚未初始化設定，請聯絡管理員！")
            return False

        if not settings['add_exam_room_id']:
            await interaction.followup.send("❌ 管理員尚未設定「管理題目頻道」！請使用 `/set_manage_room` 設定。")
            return False
        if interaction.channel.id != settings['add_exam_room_id']:
            await interaction.followup.send(f"⚠️ 請在指定的管理頻道 <#{settings['add_exam_room_id']}> 使用此指令！")
            return False

        if not settings['manage_exam_role_id']:
            await interaction.followup.send("❌ 管理員尚未設定「考官身分組」！請使用 `/set_manage_role` 設定。")
            return False
        
        has_role = interaction.user.get_role(settings['manage_exam_role_id']) is not None
        is_admin = interaction.user.guild_permissions.administrator
        
        if not has_role and not is_admin:
            await interaction.followup.send(f"❌ 你需要 <@&{settings['manage_exam_role_id']}> 身分組才能操作！")
            return False
            
        return True

    @app_commands.command(name="add_question", description="新增一個考題")
    @app_commands.default_permissions(administrator=True)
    async def add_question(self, interaction: discord.Interaction, question: str, option1: str, option2: str, option3: str, option4: str, answer: int):
        await interaction.response.defer(ephemeral=True)
        
        settings = self.get_settings()
        if not await self.check_manager_access(interaction, settings):
            return

        if answer not in [1, 2, 3, 4]:
            await interaction.followup.send("❌ 答案只能是 1~4！")
            return
        
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("INSERT INTO questions (question, option1, option2, option3, option4, answer) VALUES (%s, %s, %s, %s, %s, %s)", 
                    (question, option1, option2, option3, option4, answer))
        conn.commit()
        cur.close()
        conn.close()
        await interaction.followup.send(f"✅ 成功新增題目：{question}")

    @app_commands.command(name="delete_question", description="刪除考題")
    @app_commands.default_permissions(administrator=True)
    async def delete_question(self, interaction: discord.Interaction, question_id: int):
        await interaction.response.defer(ephemeral=True)
        
        settings = self.get_settings()
        if not await self.check_manager_access(interaction, settings):
            return
        
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("DELETE FROM questions WHERE id = %s RETURNING *", (question_id,))
        deleted = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        
        if deleted:
            await interaction.followup.send(f"🗑️ 已刪除題目 ID {question_id}")
        else:
            await interaction.followup.send(f"❌ 找不到題目 ID {question_id}")

    @app_commands.command(name="list_questions", description="查詢所有題目")
    @app_commands.default_permissions(administrator=True)
    async def list_questions(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        settings = self.get_settings()
        if not await self.check_manager_access(interaction, settings):
            return
            
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("SELECT id, question FROM questions ORDER BY id")
        questions = cur.fetchall()
        cur.close()
        conn.close()
        
        if not questions:
            await interaction.followup.send("目前題庫是空的！")
            return
            
        embed = discord.Embed(title="📖 題庫列表", color=discord.Color.blue())
        description_text = ""
        for q in questions:
            line = f"**ID: {q[0]}** - {q[1]}\n"
            if len(description_text) + len(line) > 4096:
                description_text += "\n... (題目過多，僅顯示部分)"
                break
            description_text += line
        embed.description = description_text
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="reset_questions", description="【危險】清空題庫")
    @app_commands.default_permissions(administrator=True)
    async def reset_questions(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        settings = self.get_settings()
        if not await self.check_manager_access(interaction, settings):
            return
            
        try:
            conn = psycopg2.connect(DATABASE_URL)
            cur = conn.cursor()
            cur.execute("TRUNCATE TABLE questions RESTART IDENTITY;")
            conn.commit()
            cur.close()
            conn.close()
            await interaction.followup.send("💥 題庫已重置。")
        except Exception as e:
            await interaction.followup.send(f"❌ 錯誤：{e}")

    # ---------------------------------------------------------
    # 📝 考試核心指令
    # ---------------------------------------------------------

    @app_commands.command(name="exam", description="開始考試")
    async def exam_start(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        settings = self.get_settings()
        
        if not settings:
            await interaction.followup.send("❌ 系統錯誤：無法讀取設定。", ephemeral=True)
            return
        if not settings['exam_room_id']:
            await interaction.followup.send("❌ 管理員尚未設定「考試頻道」！請使用 `/set_exam_room` 設定。", ephemeral=True)
            return
        if not settings['graduater_role_id']:
            await interaction.followup.send("❌ 管理員尚未設定「畢業身分組」！請使用 `/set_graduate_role` 設定。", ephemeral=True)
            return

        if interaction.channel.id != settings['exam_room_id']:
            await interaction.followup.send(f"⚠️ 請到指定的考試房間 <#{settings['exam_room_id']}> 使用此指令！")
            return

        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        # 1. 檢查是否在冷卻中
        if settings['failure_cooldown_minutes'] > 0:
            cur.execute("SELECT cooldown_until FROM user_cooldowns WHERE user_id = %s", (interaction.user.id,))
            cooldown_row = cur.fetchone()
            
            if cooldown_row:
                cooldown_until = cooldown_row[0]
                remaining_seconds = (cooldown_until - datetime.now()).total_seconds()
                
                if remaining_seconds > 3:
                    mins, secs = divmod(int(remaining_seconds), 60)
                    time_str = f"{mins} 分 {secs} 秒" if mins > 0 else f"{secs} 秒"
                    await interaction.followup.send(f"⏳ 考試正在冷卻中。\n請等待 **{time_str}** 後再試。", ephemeral=True)
                    cur.close()
                    conn.close()
                    return

        # 2. ✨ 寫入新的冷卻時間 (只要開始考試，就設定冷卻)
        if settings['failure_cooldown_minutes'] > 0:
            new_cooldown_until = datetime.now() + timedelta(minutes=settings['failure_cooldown_minutes'])
            cur.execute("""
                INSERT INTO user_cooldowns (user_id, cooldown_until) 
                VALUES (%s, %s) 
                ON CONFLICT (user_id) DO UPDATE SET cooldown_until = EXCLUDED.cooldown_until;
            """, (interaction.user.id, new_cooldown_until))
            conn.commit() # 立即存檔

        # 3. 撈題目
        amount_to_fetch = settings['question_amount']
        cur.execute("SELECT * FROM questions ORDER BY RANDOM() LIMIT %s", (amount_to_fetch,))
        questions = cur.fetchall()
        cur.close()
        conn.close()

        if not questions:
            await interaction.followup.send("目前題庫是空的！")
            return
        if len(questions) < amount_to_fetch:
            await interaction.followup.send(f"⚠️ 題目不足 (僅 {len(questions)} 題)！")
            return

        # 建立 View
        view = QuizView(
            self.bot, 
            interaction.user, 
            questions, 
            settings['graduater_role_id'], 
            settings['failure_cooldown_minutes'],
            settings['add_exam_room_id']
        ) 
        
        await interaction.followup.send(
            f"📘 考試開始！共有 {len(questions)} 題。",
            embed=view.current_embed, 
            view=view
        )


# 👇 互動題目選單
class QuizView(discord.ui.View):
    def __init__(self, bot: commands.Bot, user: discord.User, questions, graduater_role_id: int, cooldown_minutes: int, manage_channel_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.user = user
        self.questions = questions
        self.graduater_role_id = graduater_role_id
        self.cooldown_minutes = cooldown_minutes
        self.manage_channel_id = manage_channel_id
        self.index = 0
        self.correct_count = 0
        self.show_next()

    def show_next(self):
        self.clear_items()
        if self.index < len(self.questions):
            q = self.questions[self.index]
            
            options_to_shuffle = [
                (q[2], "1"), (q[3], "2"), (q[4], "3"), (q[5], "4")
            ]
            random.shuffle(options_to_shuffle)
            
            embed = discord.Embed(title=f"第 {self.index + 1} / {len(self.questions)} 題", description=f"**{q[1]}**", color=discord.Color.green())
            
            select_options = []
            for i, (text, original_value) in enumerate(options_to_shuffle):
                embed.add_field(name=f"選項 {i+1}", value=text, inline=False)
                select_options.append(discord.SelectOption(label=f"選項 {i+1}", value=original_value))

            select = discord.ui.Select(
                placeholder="請選擇一個選項...",
                options=select_options
            )
            
            select.callback = self.make_callback(int(q[6]), q[1])
            self.add_item(select)
            self.current_embed = embed
            
        else:
            button = discord.ui.Button(label="領取證書", style=discord.ButtonStyle.success)
            button.callback = self.finish_exam
            self.add_item(button)
            self.current_embed = discord.Embed(title="🎉 考試結束", description="恭喜你全部答對！請點擊下方按鈕領取身分組。", color=discord.Color.gold())

    def make_callback(self, correct_answer, question_text: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user.id:
                await interaction.response.send_message("這不是你的考試喔 😅", ephemeral=True)
                return
            
            selected = int(interaction.data["values"][0])
            
            if selected == correct_answer:
                self.correct_count += 1
                self.index += 1
                if self.index < len(self.questions):
                    self.show_next()
                    await interaction.response.edit_message(content=None, embed=self.current_embed, view=self)
                else:
                    self.show_next()
                    await interaction.response.edit_message(content=None, embed=self.current_embed, view=self)
            else:
                await interaction.response.edit_message(content=f"❌ 答錯了！考試結束 😢", embed=None, view=None)
                
                if self.cooldown_minutes > 0:
                    try:
                        conn = psycopg2.connect(DATABASE_URL)
                        cur = conn.cursor()
                        cooldown_until = datetime.now() + timedelta(minutes=self.cooldown_minutes)
                        cur.execute("""
                            INSERT INTO user_cooldowns (user_id, cooldown_until) 
                            VALUES (%s, %s) 
                            ON CONFLICT (user_id) DO UPDATE SET cooldown_until = EXCLUDED.cooldown_until;
                        """, (interaction.user.id, cooldown_until))
                        conn.commit()
                        cur.close()
                        conn.close()
                    except Exception as e:
                        print(f"冷卻設定失敗: {e}")

                if self.manage_channel_id:
                    try:
                        announce_channel = self.bot.get_channel(self.manage_channel_id)
                        if not announce_channel:
                             announce_channel = await self.bot.fetch_channel(self.manage_channel_id)

                        if announce_channel:
                            retry_msg = ""
                            if self.cooldown_minutes > 0:
                                future_ts = int((datetime.now() + timedelta(minutes=self.cooldown_minutes)).timestamp())
                                # ✨ [格式優化] 這裡的通知也改成具體時間點
                                retry_msg = f"\n⏳ 需等待至 <t:{future_ts}:t> 才能重考。"

                            await announce_channel.send(
                                f"😥 **考試失敗通知**\n"
                                f"成員：{interaction.user.mention}\n"
                                f"錯誤題目：**{question_text}**"
                                f"{retry_msg}"
                            )
                    except Exception as e:
                        print(f"無法傳送失敗訊息: {e}")
                
        return callback

    async def finish_exam(self, interaction: discord.Interaction):
        if not self.graduater_role_id:
            await interaction.response.edit_message(content="❌ 系統錯誤：未設定畢業身分組 ID。", embed=None, view=None)
            return

        role = interaction.guild.get_role(self.graduater_role_id)
        if role:
            try:
                await interaction.user.add_roles(role)
                await interaction.response.edit_message(content=f"🏅 恭喜！已獲得身分組：{role.name}", embed=None, view=None)
            except discord.Forbidden:
                await interaction.response.edit_message(content="✅ 通過！但我權限不足給予身分組，請通知管理員。", embed=None, view=None)
        else:
            await interaction.response.edit_message(content=f"✅ 通過！但找不到 ID `{self.graduater_role_id}` 的身分組。", embed=None, view=None)

async def setup(bot):
    await bot.add_cog(Exam(bot))