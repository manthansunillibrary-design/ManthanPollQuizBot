#!/usr/bin/env python3
"""
ManthanPollQuizBot - Render + Telegram Ready
- Sequential Quiz Flow with shared link
- Google Sheet: "ManthanPollQuiz"
- Service account JSON via env var GOOGLE_CREDENTIALS
- Bot Token via BOT_TOKEN env var
"""

import os
import json
import logging
import uuid
import asyncio
from datetime import datetime
import gspread
from telegram import Poll, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    PollAnswerHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ---------------- CONFIG ----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_CREDENTIALS")  # Render env var
SHEET_NAME = "ManthanPollQuiz"
COACHING_NAME = "🏫 Manthan Competition Classes"
DEFAULT_TIMER = 20  # seconds

# ---------------- Check Secrets ----------------
if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN env var missing!")
if not SERVICE_ACCOUNT_JSON:
    raise RuntimeError("❌ GOOGLE_CREDENTIALS env var missing!")

# ---------------- Logging ----------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------------- Google Sheets ----------------
try:
    credentials_dict = json.loads(SERVICE_ACCOUNT_JSON)
    if "private_key" in credentials_dict:
        credentials_dict["private_key"] = credentials_dict["private_key"].replace('\\n', '\n')
    gc = gspread.service_account_from_dict(credentials_dict)
    sh = gc.open(SHEET_NAME)
    ws = sh.sheet1
    logger.info("✅ gspread connected successfully!")
except Exception as e:
    raise RuntimeError(f"❌ Failed to connect gspread: {e}")

# ---------------- Default Headers ----------------
DEFAULT_HEADERS = [
    "ID","Question","Option1","Option2","Option3","Option4",
    "CorrectOption","QuizID","PollID","ChatID","MessageID",
    "ResultsMessageID","Link","CreatedAt","TimerSec"
]

def ensure_headers_and_map():
    current = ws.row_values(1)
    if not current:
        ws.insert_row(DEFAULT_HEADERS, 1)
        current = DEFAULT_HEADERS.copy()
    for h in DEFAULT_HEADERS:
        if h not in current:
            ws.update_cell(1, len(current)+1, h)
            current.append(h)
    return {name: idx+1 for idx, name in enumerate(current)}

COL = ensure_headers_and_map()

# ---------------- ID Assignment ----------------
def assign_ids_if_missing():
    """
    Batch-update version:
    - Generate missing IDs and CreatedAt
    - Fill default TimerSec where empty
    Uses a single batch request to reduce write-rate quota errors.
    """
    records = ws.get_all_records()
    if not records:
        return

    updates = []  # collect (row, col, value) tuples for batch update

    for idx, rec in enumerate(records, start=2):
        # ID
        current_id = rec.get("ID", "")
        if not str(current_id).strip():
            new_id = "Q" + uuid.uuid4().hex[:8]
            updates.append({
                "range": gspread.utils.rowcol_to_a1(idx, COL["ID"]),
                "values": [[new_id]]
            })
            updates.append({
                "range": gspread.utils.rowcol_to_a1(idx, COL["CreatedAt"]),
                "values": [[datetime.utcnow().isoformat()]]
            })

        # TimerSec
        timer_val = rec.get("TimerSec", "")
        if timer_val is None or str(timer_val).strip() == "":
            updates.append({
                "range": gspread.utils.rowcol_to_a1(idx, COL["TimerSec"]),
                "values": [[str(DEFAULT_TIMER)]]
            })

    # If updates collected, do a single batch_update (via values_batch_update)
    if updates:
        body = {"valueInputOption": "USER_ENTERED", "data": updates}
        ws.spreadsheet.values_batch_update(body)

# ---------------- Poll Management ----------------
emoji_counts = {}
poll_data = {}

def get_row_record(rownum: int):
    recs = ws.get_all_records()
    if 2 <= rownum <= len(recs)+1:
        return recs[rownum-2]
    return {}

async def send_poll_for_row(context: ContextTypes.DEFAULT_TYPE, rownum:int, chat_id:int):
    rec = get_row_record(rownum)
    question = str(rec.get("Question","")).strip()
    if not question: return False

    question_text = f"{COACHING_NAME}\n\n{question}"

    options=[]
    for i in range(1,5):
        v = str(rec.get(f"Option{i}","")).strip()
        if v: options.append(v)
    if not options: return False

    correct_opt = str(rec.get("CorrectOption","")).strip()
    is_quiz=False
    correct_option_id=None
    if correct_opt:
        try:
            ci=int(correct_opt)
            if 1<=ci<=len(options):
                correct_option_id=ci-1
                is_quiz=True
        except:
            if correct_opt in options:
                correct_option_id=options.index(correct_opt)
                is_quiz=True

    if is_quiz:
        msg = await context.bot.send_poll(
            chat_id=chat_id,
            question=question_text,
            options=options,
            type=Poll.QUIZ,
            is_anonymous=False,
            correct_option_id=correct_option_id
        )
    else:
        msg = await context.bot.send_poll(
            chat_id=chat_id,
            question=question_text,
            options=options,
            type=Poll.REGULAR,
            is_anonymous=False
        )

    poll_id = msg.poll.id
    ws.update_cell(rownum, COL["PollID"], poll_id)
    ws.update_cell(rownum, COL["ChatID"], str(chat_id))
    ws.update_cell(rownum, COL["MessageID"], str(msg.message_id))

    me = await context.bot.get_me()
    qid = ws.cell(rownum, COL["ID"]).value
    link = f"https://t.me/{me.username}?start={qid}"
    ws.update_cell(rownum, COL["Link"], link)

    emoji_counts[poll_id] = {"like":0,"love":0,"haha":0,"angry":0}
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(f"👍 0", callback_data=f"{poll_id}_like"),
        InlineKeyboardButton(f"❤️ 0", callback_data=f"{poll_id}_love"),
        InlineKeyboardButton(f"😂 0", callback_data=f"{poll_id}_haha"),
        InlineKeyboardButton(f"😡 0", callback_data=f"{poll_id}_angry")
    ]])
    resmsg = await context.bot.send_message(chat_id=chat_id,text="React to this poll:",reply_markup=keyboard)
    ws.update_cell(rownum,COL["ResultsMessageID"],str(resmsg.message_id))

    poll_data[poll_id] = {
        "row": rownum,
        "options": options,
        "votes": [0]*len(options),
        "user_votes":{},
        "chat_id":int(chat_id),
        "message_id": msg.message_id,
        "results_msg_id": resmsg.message_id
    }

    logger.info(f"Sent poll row={rownum} poll_id={poll_id} chat={chat_id}")
    return True

# ---------------- Sequential Quiz ----------------
async def start_sequential_quiz(context: ContextTypes.DEFAULT_TYPE, chat_id:int, quiz_id:str):
    records = ws.get_all_records()
    for idx, rec in enumerate(records, start=2):
        if rec.get("QuizID","") == quiz_id and not str(rec.get("PollID","")).strip():
            timer_sec = rec.get("TimerSec")
            try:
                timer_sec = int(timer_sec)
            except:
                timer_sec = DEFAULT_TIMER
            await send_poll_for_row(context, idx, chat_id)
            await asyncio.sleep(timer_sec)

# ---------------- Command Handlers ----------------
async def start(update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"नमस्ते {user.first_name}! मैं Manthan Poll/Quiz Bot हूँ.\nUse /quiz to get a new quiz link."
    )

async def quiz_cmd(update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    records = ws.get_all_records()
    first_quiz_id = None
    for rec in records:
        if not str(rec.get("PollID","")).strip():
            first_quiz_id = rec.get("QuizID","")
            break
    if not first_quiz_id:
        await update.message.reply_text("कोई नया question नहीं मिला (सब already posted).")
        return
    me = await context.bot.get_me()
    shared_link = f"https://t.me/{me.username}?start={first_quiz_id}"
    await update.message.reply_text(f"Quiz ready! Share this link with students:\n{shared_link}")
    # Start sequential quiz asynchronously
    asyncio.create_task(start_sequential_quiz(context, chat_id, first_quiz_id))

async def syncids(update, context: ContextTypes.DEFAULT_TYPE):
    assign_ids_if_missing()
    await update.message.reply_text("Missing IDs generated and CreatedAt updated.")

async def poll_answer_handler(update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.poll_answer
    poll_id = answer.poll_id
    user_id = answer.user.id
    new_set = set(answer.option_ids)
    if poll_id not in poll_data: return
    entry = poll_data[poll_id]
    prev = entry["user_votes"].get(user_id,set())
    to_add = new_set - prev
    to_remove = prev - new_set
    for i in to_add:
        if 0<=i<len(entry["votes"]): entry["votes"][i]+=1
    for i in to_remove:
        if 0<=i<len(entry["votes"]): entry["votes"][i]-=1
    entry["user_votes"][user_id]=new_set
    lines=["Current Votes:"]
    for idx,opt in enumerate(entry["options"]):
        lines.append(f"{idx+1}. {opt} — {entry['votes'][idx]} votes")
    result_text="\n".join(lines)
    try:
        await context.bot.edit_message_text(chat_id=entry["chat_id"],message_id=entry["results_msg_id"],text=result_text)
    except: pass

async def emoji_callback(update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    try:
        poll_id, emoji_type = data.split("_")
    except: return
    if poll_id not in emoji_counts: return
    emoji_counts[poll_id][emoji_type]+=1
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(f"👍 {emoji_counts[poll_id]['like']}", callback_data=f"{poll_id}_like"),
        InlineKeyboardButton(f"❤️ {emoji_counts[poll_id]['love']}", callback_data=f"{poll_id}_love"),
        InlineKeyboardButton(f"😂 {emoji_counts[poll_id]['haha']}", callback_data=f"{poll_id}_haha"),
        InlineKeyboardButton(f"😡 {emoji_counts[poll_id]['angry']}", callback_data=f"{poll_id}_angry")
    ]])
    await query.edit_message_reply_markup(reply_markup=kb)
    await query.answer("Your reaction recorded ✅")

# ---------------- Main ----------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("quiz", quiz_cmd))
    app.add_handler(CommandHandler("syncids", syncids))
    app.add_handler(PollAnswerHandler(poll_answer_handler))
    app.add_handler(CallbackQueryHandler(emoji_callback))

    assign_ids_if_missing()
    logger.info("🚀 Bot starting... Press Ctrl+C to stop.")
    app.run_polling()

if __name__=="__main__":
    main()
