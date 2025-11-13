import discord
from discord import app_commands
from discord.ext import commands
import psycopg2
import os
import random
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("EXTERNAL_DATABASE_URL")
EXAM_ROOM_ID = int(os.getenv("EXAM_ROOM_ID"))
ADD_EXAM_ROOM_ID = int(os.getenv("ADD_EXAM_ROOM_ID"))
MANAGE_EXAM_ROLE_ID = int(os.getenv("MANAGE_EXAM_ROLE_ID"))
GRADUATER_ID = int(os.getenv("GRADUATER_ID"))

# -----------------------------------------------
# ✨ [功能更新] 修改 init_db
# -----------------------------------------------
def init_db():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    # 建立 questions 資料表 (不變)
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
    
    # ✨ 新增：建立 exam_settings 資料表
    cur.execute("""
        CREATE TABLE IF NOT EXISTS exam_settings (
            id INT PRIMARY KEY,
            question_amount INT NOT NULL DEFAULT 5
        );
    """)
    
    # ✨ 新增：確保 settings 表中有預設值 (id=1, 數量=5)
    # ON CONFLICT DO NOTHING = 如果 id=1 的資料已存在，就什麼都不做
    cur.execute("""
        INSERT INTO exam_settings (id, question_amount)
        VALUES (1, 5)
        ON CONFLICT (id) DO NOTHING;
    """)
    
    conn.commit()
    cur.close()
    conn.close()

init_db()


class Exam(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """ 處理這個 Cog 中所有指令的錯誤 """
        if isinstance(error, app_commands.MissingRole):
            await interaction.response.send_message(f"❌ 你需要擁有管理員的身分組才能使用此指令！", ephemeral=True)
        elif isinstance(error, app_commands.RangeError):
            await interaction.response.send_message(f"❌ 數量必須介於 {error.minimum} 到 {error.maximum} 之間！", ephemeral=True)
        elif isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message("❌ 你不符合使用此指令的條件（例如頻道錯誤）！", ephemeral=True)
        else:
            print(f"指令 {interaction.command.name} 發生未處理的錯誤: {error}")
            if not interaction.response.is_done():
                await interaction.response.send_message("🤖 發生了一個未知的錯誤，請聯繫管理員。", ephemeral=True)
    # -----------------------------------------------

    # 🧩 新增題目指令
    @app_commands.command(name="add_question", description="新增一個考題（只能在指定房間使用）")
    @app_commands.checks.has_role(MANAGE_EXAM_ROLE_ID)
    async def add_question(self, interaction: discord.Interaction,
                           question: str,
                           option1: str,
                           option2: str,
                           option3: str,
                           option4: str,
                           answer: int):
        # ... (邏輯不變) ...
        if interaction.channel.id != ADD_EXAM_ROOM_ID:
            await interaction.response.send_message("⚠️ 這個指令只能在指定的新增題目頻道使用！", ephemeral=True)
            return
        if answer not in [1, 2, 3, 4]:
            await interaction.response.send_message("❌ 答案只能是 1~4！", ephemeral=True)
            return
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO questions (question, option1, option2, option3, option4, answer)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (question, option1, option2, option3, option4, answer))
        conn.commit()
        cur.close()
        conn.close()
        await interaction.response.send_message(f"✅ 成功新增題目：{question}", ephemeral=True)

    # ❌ 刪除題目
    @app_commands.command(name="delete_question", description="刪除考題（用 ID）")
    @app_commands.checks.has_role(MANAGE_EXAM_ROLE_ID)
    async def delete_question(self, interaction: discord.Interaction, question_id: int):
        # ... (邏輯不變) ...
        if interaction.channel.id != ADD_EXAM_ROOM_ID:
            await interaction.response.send_message("⚠️ 這個指令只能在指定的新增題目頻道使用！", ephemeral=True)
            return
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("DELETE FROM questions WHERE id = %s RETURNING *", (question_id,))
        deleted = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        if deleted:
            await interaction.response.send_message(f"🗑️ 已刪除題目 ID {question_id}", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ 找不到題目 ID {question_id}", ephemeral=True)

    # 📖 查詢所有題目
    @app_commands.command(name="list_questions", description="查詢目前題庫中的所有題目（僅限指定房間）")
    @app_commands.checks.has_role(MANAGE_EXAM_ROLE_ID)
    async def list_questions(self, interaction: discord.Interaction):
        # ... (邏輯不變) ...
        if interaction.channel.id != ADD_EXAM_ROOM_ID:
            await interaction.response.send_message("⚠️ 這個指令只能在指定的新增題目頻道使用！", ephemeral=True)
            return
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("SELECT id, question FROM questions ORDER BY id")
        questions = cur.fetchall()
        cur.close()
        conn.close()
        if not questions:
            await interaction.response.send_message("目前題庫是空的！", ephemeral=True)
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
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # 💥 重置題庫
    @app_commands.command(name="reset_questions", description="【危險】刪除所有題目並將 ID 重設回 1")
    @app_commands.checks.has_role(MANAGE_EXAM_ROLE_ID)
    async def reset_questions(self, interaction: discord.Interaction):
        # ... (邏輯不變) ...
        if interaction.channel.id != ADD_EXAM_ROOM_ID:
            await interaction.response.send_message("⚠️ 這個指令只能在指定的新增題目頻道使用！", ephemeral=True)
            return
        try:
            conn = psycopg2.connect(DATABASE_URL)
            cur = conn.cursor()
            cur.execute("TRUNCATE TABLE questions RESTART IDENTITY;")
            conn.commit()
            cur.close()
            conn.close()
            await interaction.response.send_message("題庫已清空，ID 計數器已重設回 1。", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 重置題庫時發生錯誤：{e}", ephemeral=True)

    # -----------------------------------------------
    # ✨ [新指令] 管理員設定考試題目
    # -----------------------------------------------
    @app_commands.command(name="set_exam_amount", description="設定考試的預設題目數量(1~100)")
    @app_commands.checks.has_role(MANAGE_EXAM_ROLE_ID)
    @app_commands.describe(amount="要設定的題目數量(1~100)")
    async def set_exam_amount(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
        
        # 也在 ADD_EXAM_ROOM 才能設定
        if interaction.channel.id != ADD_EXAM_ROOM_ID:
            await interaction.response.send_message("⚠️ 這個指令只能在指定的新增題目頻道使用！", ephemeral=True)
            return

        try:
            conn = psycopg2.connect(DATABASE_URL)
            cur = conn.cursor()
            
            # 更新 (或插入) id=1 的那筆設定
            cur.execute("""
                INSERT INTO exam_settings (id, question_amount)
                VALUES (1, %s)
                ON CONFLICT (id) DO UPDATE SET question_amount = EXCLUDED.question_amount;
            """, (amount,))
            
            conn.commit()
            cur.close()
            conn.close()
            
            await interaction.response.send_message(f"✅ 成功將考試題目數量設為 **{amount}** 題。", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 設定時發生錯誤：{e}", ephemeral=True)

    # -----------------------------------------------
    # ✨ [功能更新] 開始考試
    # -----------------------------------------------
    @app_commands.command(name="exam", description="開始考試")
    async def exam_start(self, interaction: discord.Interaction):
        
        if interaction.channel.id != EXAM_ROOM_ID:
            await interaction.response.send_message("⚠️ 請到指定的考試房間使用此指令！", ephemeral=True)
            return

        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        # ✨ 新增：讀取管理員設定的題目數量
        cur.execute("SELECT question_amount FROM exam_settings WHERE id = 1;")
        setting_row = cur.fetchone()
        
        # 如果找不到設定（理論上不會），預設為 5
        amount_to_fetch = 5
        if setting_row:
            amount_to_fetch = setting_row[0]

        # ✨ 修改：使用讀取到的 amount_to_fetch 來抽題
        cur.execute("SELECT * FROM questions ORDER BY RANDOM() LIMIT %s", (amount_to_fetch,))
        
        questions = cur.fetchall()
        cur.close()
        conn.close()

        if not questions:
            await interaction.response.send_message("目前題庫是空的，請先新增題目！", ephemeral=True)
            return
        
        # 檢查抽到的題目是否少于設定的數量 (例如題庫只有3題，但設定要5題)
        if len(questions) < amount_to_fetch:
            await interaction.response.send_message(f"⚠️ 題庫題目不足！(僅找到 {len(questions)} 題)", ephemeral=True)
            return

        # ✨ [Bug 修復] 傳入 GRADUATER_ID
        view = QuizView(interaction.user, questions, GRADUATER_ID) 
        
        await interaction.response.send_message(
            f"📘 考試開始！共有 {len(questions)} 題，答錯即結束！",
            view=view,
            ephemeral=True
        )


# 👇 互動題目選單
class QuizView(discord.ui.View):
    # ✨ [Bug 修復] 修正 __init__
    def __init__(self, user: discord.User, questions, graduater_role_id: int):
        super().__init__(timeout=None)
        self.user = user
        self.questions = questions
        self.graduater_role_id = graduater_role_id # <-- 儲存 ID
        self.index = 0
        self.correct_count = 0
        self.show_next()

    def show_next(self):
        # ... (邏輯不變) ...
        self.clear_items()
        if self.index < len(self.questions):
            q = self.questions[self.index]
            select = discord.ui.Select(
                placeholder=f"第 {self.index + 1} 題：{q[1]}",
                options=[
                    discord.SelectOption(label=q[2], value="1"),
                    discord.SelectOption(label=q[3], value="2"),
                    discord.SelectOption(label=q[4], value="3"),
                    discord.SelectOption(label=q[5], value="4"),
                ]
            )
            select.callback = self.make_callback(int(q[6]))
            self.add_item(select)
        else:
            button = discord.ui.Button(label="完成考試", style=discord.ButtonStyle.success)
            button.callback = self.finish_exam
            self.add_item(button)

    def make_callback(self, correct_answer):
        # ... (邏輯不變) ...
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
                    await interaction.response.edit_message(
                        content=f"✅ 答對了！進入下一題（第 {self.index + 1} 題）",
                        view=self
                    )
                else:
                    self.show_next()
                    await interaction.response.edit_message(
                        content=f"🎉 全部答對！恭喜通過考試！請點擊下方完成按鈕！",
                        view=self
                    )
            else:
                await interaction.response.edit_message(
                    content=f"❌ 答錯了！考試結束 😢",
                    view=None
                )
        return callback

    # -----------------------------------------------
    # ✨ [Bug 修復] 修正 finish_exam
    # -----------------------------------------------
    async def finish_exam(self, interaction: discord.Interaction):
        # 新的：直接用 ID 取得身分組
        role = interaction.guild.get_role(self.graduater_role_id)
        
        if role:
            await interaction.user.add_roles(role)
            await interaction.response.edit_message(
                content=f"🏅 恭喜通過考試，已獲得身分組：{role.name}",
                view=None
            )
        else:
            await interaction.response.edit_message(
                content=f"✅ 通過考試！但找不到身分組，請通知管理員。",
                view=None
            )
    # -----------------------------------------------


async def setup(bot):
    await bot.add_cog(Exam(bot))