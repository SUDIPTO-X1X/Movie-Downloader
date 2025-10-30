import os,re
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.request import HTTPXRequest
import aiohttp
from aiohttp import ClientTimeout
from bs4 import BeautifulSoup

#_____________________[ Config/Value ]_________________#
BOT_TOKEN = "999:CDL:ING-PONG"

"""  DAte : 8/11/25
this is temp link if u want add permanent link of web just add redirect def then u can run without update
If u need more fasility in this script DM ME 
"""
BASE_URL = "https://filmyfly.navy"
ITEMS_PER_PAGE = 15

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
#_____________________[ Session/Close ]_________#
session: aiohttp.ClientSession | None = None
TIMEOUT = ClientTimeout(total=15)

async def get_session():
    global session
    if session is None or session.closed:
        session = aiohttp.ClientSession(timeout=TIMEOUT)
    return session

async def on_shutdown(app):
    global session
    if session and not session.closed:
        await session.close()
        logger.info("HTTP session closed")

#_____________________[ Scraping Def ]_____________#
async def search_movie(query: str):
    search_url = f"{BASE_URL}/site-1.html?to-search={query.replace(' ', '+')}"
    try:
        session = await get_session()
        async with session.get(search_url) as resp:
            html = await resp.text()
    except asyncio.TimeoutError:
        logger.warning(f"Timeout while fetching {search_url}")
        return []
    except Exception as e:
        logger.error(f"Error fetching {search_url}: {e}")
        return []

    soup = BeautifulSoup(html, "html.parser")
    movie_links = []
    for div in soup.find_all("div", class_="A2"):
        a_tag = div.find("a", href=True)
        title_tag = div.find("b")
        if a_tag and title_tag:
            link = a_tag["href"]
            title = title_tag.get_text(strip=True)
            movie_links.append((title, BASE_URL + link))
    return movie_links

async def scrp_dwnlod_pge(page_url: str):
    try:
        session = await get_session()
        async with session.get(page_url) as resp:
            html = await resp.text()

        soup = BeautifulSoup(html, "html.parser")
        dl_btn = soup.find("div", class_="dlbtn")
        if not dl_btn:
            return []
        first_link = dl_btn.find("a", href=True)
        if not first_link:
            return []
        async with session.get(first_link["href"]) as resp2:
            html2 = await resp2.text()

        soup2 = BeautifulSoup(html2, "html.parser")
        final_links = []
        for div in soup2.find_all("div", class_="dlink dl"):
            a_tag = div.find("a", href=True)
            name = div.get_text(strip=True)
            if a_tag and name:
                final_links.append((name, a_tag["href"]))
        return final_links
    except asyncio.TimeoutError:
        logger.warning(f"Timeout while fetching {page_url}")
        return []
    except Exception as e:
        logger.error(f"Error fetching download page {page_url}: {e}")
        return []

#_____________________[ Tg Msg Hndlr ]_________________#

# Your group link & bot username

OFFICIAL_GROUP_LINK = "https://t.me/+7KGGY-i3Os1mZGE1"
BOT_USERNAME = "@mwaww_bot"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_type = update.effective_chat.type
    
    if chat_type in ["group", "supergroup"]:
        await update.message.reply_text("👋 Hello! Send a movie name to search.")
    else:
        keyboard = [
            [InlineKeyboardButton("➕ Add me to another group", url=f"https://t.me/{BOT_USERNAME}?startgroup=true")],
            [InlineKeyboardButton("📌 Join my official group", url=OFFICIAL_GROUP_LINK)],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "⚠️ This bot only works in groups.\n\n"
            "👉 Add me to a group and give admin permission.",
            reply_markup=reply_markup
        )



async def handle_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in ["group", "supergroup"]:
        return
    query = update.message.text.strip()
    if not query:
        return
    asyncio.create_task(delete_after_delay(context, update.message.chat_id, update.message.message_id, 60)) # Auto delete mesg after 60 sec
    searching_msg = await update.message.reply_text(f"🔍 Searching for: {query}")
    asyncio.create_task(delete_after_delay(context, searching_msg.chat_id, searching_msg.message_id, 45))  # Auto delete mesg after 60 sec
    movies = await search_movie(query)
    if not movies:
        no_result_msg = await update.message.reply_text("❌ No results found.")
        asyncio.create_task(delete_after_delay(context, no_result_msg.chat_id, no_result_msg.message_id, 45)) # Auto delete mesg after 45 sec
        return

    context.user_data['movie_results'] = movies
    context.user_data['current_page'] = 0
    await bot_movpg_sgst(update.message.chat_id, context, page=0)


async def delete_after_delay(context, chat_id, message_id, delay: int):
    await asyncio.sleep(delay)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


async def bot_movpg_sgst(chat_id, context, page):
    movies = context.user_data['movie_results']
    total = len(movies)
    max_page = max((total - 1) // ITEMS_PER_PAGE, 0)
    page = max(0, min(page, max_page))
    context.user_data['current_page'] = page
    start = page * ITEMS_PER_PAGE
    end = min(start + ITEMS_PER_PAGE, total)
    movie_slice = movies[start:end]
    keyboard = [[InlineKeyboardButton(f"{start+i+1}. {title}", callback_data=f"movie_{start+i}")]
        for i, (title, _) in enumerate(movie_slice)]
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⏮ Prev", callback_data="prev_page"))
    if page < max_page:
        nav_buttons.append(InlineKeyboardButton("⏭ Next", callback_data="next_page"))
    if nav_buttons:
        keyboard.append(nav_buttons)

    await context.bot.send_message(chat_id=chat_id,text=f"🎬 Select a movie (page {page+1}/{max_page+1}):",reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    movies = context.user_data.get('movie_results', [])
    # Auto delete old mesg 
    try:
        await context.bot.delete_message(chat_id=query.message.chat_id, message_id=query.message.message_id)
    except Exception:
        pass

    total = len(movies)
    max_page = max((total - 1) // ITEMS_PER_PAGE, 0)

    if data == "next_page":
        page = min(context.user_data.get('current_page', 0) + 1, max_page)
        await bot_movpg_sgst(query.message.chat_id, context, page)

    elif data == "prev_page":
        page = max(context.user_data.get('current_page', 0) - 1, 0)
        await bot_movpg_sgst(query.message.chat_id, context, page)

    elif data.startswith("movie_"):
        index = int(data.split("_")[1])
        if index < 0 or index >= len(movies):
            await context.bot.send_message(chat_id=query.message.chat_id, text="⚠️ Invalid selection.")
            return

        title, url = movies[index]
        loading_msg = await context.bot.send_message(chat_id=query.message.chat_id, text="⏳ Request for download links...")
        links = await scrp_dwnlod_pge(url)

        if not links:
            try:
                await loading_msg.edit_text("❌ No download links found.")
            except Exception:
                await context.bot.send_message(chat_id=query.message.chat_id, text="❌ No download links found...")
            return

        # Clean link names
        keyboard = []
        for name, link in links:
            clean_name = re.sub(r"[{}]", "", name).strip()
            label = f"📁 {clean_name}"
            keyboard.append([InlineKeyboardButton(label, url=link)])

        try:
            message = await loading_msg.edit_text("📥 Available Downloads:",
                reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception:
            message = await context.bot.send_message(
                chat_id=query.message.chat_id,text="📥 Available Downloads:",reply_markup=InlineKeyboardMarkup(keyboard))

        await asyncio.sleep(60)
        try:
            await context.bot.delete_message(chat_id=query.message.chat_id, message_id=message.message_id)
        except Exception:
            pass
    else:
        await context.bot.send_message(chat_id=query.message.chat_id, text="⚠️ Invalid ....")


#_____________________[ Main ]_________________#
def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable not set")

    request = HTTPXRequest(connect_timeout=20, read_timeout=20, write_timeout=20, pool_timeout=20)
    app = ApplicationBuilder().token(BOT_TOKEN).request(request).build()
    app.post_shutdown = on_shutdown

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search))
    app.add_handler(CallbackQueryHandler(button_handler))

    logger.info("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
