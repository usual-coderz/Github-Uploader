import os
import json
import time
import zipfile
import base64
import requests
from datetime import datetime
from pyrogram import Client, filters

# ==============================
# CONFIG
# ==============================
API_ID = 12345  # Your API_ID
API_HASH = "YOUR_API_HASH"  # Your API_HASH
BOT_TOKEN = "YOUR_BOT_TOKEN"  # Your Bot Token

# 👑 ADMIN IDS - ADD YOUR TELEGRAM ID HERE
ADMIN_IDS = [123456789]  # Replace with your user ID (@userinfobot)

DB = "users.json"
DL = "downloads"
EXT = "extracted"

os.makedirs(DL, exist_ok=True)
os.makedirs(EXT, exist_ok=True)

if not os.path.exists(DB):
    json.dump({}, open(DB, "w"))

# ==============================
# BOT
# ==============================
app = Client(
    "GithubPushBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ==============================
# UTILS
# ==============================
def is_admin(user_id):
    return user_id in ADMIN_IDS

def save_user(uid, data):
    db = json.load(open(DB))
    db[str(uid)] = {
        **(db.get(str(uid), {})),
        **data,
        "last_seen": datetime.now().isoformat()
    }
    json.dump(db, open(DB, "w"), indent=4)

def get_user(uid):
    db = json.load(open(DB))
    return db.get(str(uid), {})

def get_all_users():
    db = json.load(open(DB))
    return [int(uid) for uid in db.keys()]

# ==============================
# GITHUB API
# ==============================
def create_repo(token, repo_name, visibility="private"):
    url = "https://api.github.com/user/repos"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    
    data = {
        "name": repo_name,
        "private": visibility.lower() == "private",
        "auto_init": True
    }
    
    response = requests.post(url, json=data, headers=headers)
    return response.status_code == 201

def upload_file(token, repo, branch, file_path, repo_path):
    try:
        with open(file_path, "rb") as f:
            content = base64.b64encode(f.read()).decode()
        
        url = f"https://api.github.com/repos/{repo}/contents/{repo_path}"
        headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
        
        data = {
            "message": f"Upload {repo_path}",
            "content": content,
            "branch": branch
        }
        
        response = requests.put(url, json=data, headers=headers)
        return response.status_code in [200, 201]
    except:
        return False

def progress_bar(percent):
    filled = int(percent / 10)
    return "█" * filled + "░" * (10 - filled)

# ==============================
# USER COMMANDS
# ==============================
@app.on_message(filters.command("start"))
async def start(_, message):
    welcome = """
🤖 <b>Github Push Bot</b>

<b>Commands:</b>
• /makeconfig - Setup repo
• /config - View config  
• /push - Upload ZIP (reply)

<b>Usage:</b>
1. /makeconfig TOKEN|BRANCH|REPO|private
2. Send ZIP file
3. Reply /push
"""
    await message.reply(welcome, parse_mode="md")

@app.on_message(filters.command("makeconfig"))
async def makeconfig(_, message):
    try:
        args = message.text.split(None, 1)[1]
        token, branch, repo, vis = [x.strip() for x in args.split("|")]
        
        vis = vis.lower()
        if vis not in ["private", "public"]:
            return await message.reply("❌ Use <code>private</code> or <code>public</code>")
        
        repo_name = repo.split("/")[-1]
        if create_repo(token, repo_name, vis):
            save_user(message.from_user.id, {
                "token": token, "branch": branch, "repo": repo, "visibility": vis,
                "username": message.from_user.username or "N/A"
            })
            await message.reply("✅ Config saved & repo created!")
        else:
            await message.reply("❌ Failed to create repo. Check token.")
            
    except:
        await message.reply(
            "<b>Usage:</b>\n"
            "<code>/makeconfig TOKEN|BRANCH|USER/REPO|private/public</code>\n\n"
            "<b>Example:</b>\n"
            "<code>/makeconfig ghp_xxx|main|user/repo|private</code>",
            parse_mode="md"
        )

@app.on_message(filters.command("config"))
async def show_config(_, message):
    cfg = get_user(message.from_user.id)
    if not cfg:
        return await message.reply("❌ No config. Use /makeconfig")
    
    await message.reply(
        f"⚙️ <b>Config</b>\n\n"
        f"📂 <b>Repo</b>: <code>{cfg['repo']}</code>\n"
        f"🌿 <b>Branch</b>: <code>{cfg['branch']}</code>\n"
        f"🔒 <b>Visibility</b>: <code>{cfg['visibility'].title()}</code>",
        parse_mode="md"
    )

@app.on_message(filters.command("push"))
async def push_zip(client, message):
    if not message.reply_to_message:
        return await message.reply("❌ Reply to ZIP file!")
    
    doc = message.reply_to_message.document
    if not doc or not doc.file_name.lower().endswith(".zip"):
        return await message.reply("❌ Reply to <b>ZIP file</b> only!")
    
    cfg = get_user(message.from_user.id)
    if not cfg:
        return await message.reply("❌ Setup: <code>/makeconfig</code>")
    
    status_msg = await message.reply("📥 <b>Downloading...</b>")
    
    try:
        zip_path = await message.reply_to_message.download(file_name=f"{DL}/{doc.file_name}")
        await status_msg.edit("📦 <b>Extracting...</b>")
        
        extract_dir = f"{EXT}/{doc.file_name[:-4]}"
        os.makedirs(extract_dir, exist_ok=True)
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(extract_dir)
        
        files = []
        total_size = 0
        for root, _, fs in os.walk(extract_dir):
            for f in fs:
                path = os.path.join(root, f)
                files.append(path)
                total_size += os.path.getsize(path)
        
        if not files:
            await status_msg.edit("❌ No files in ZIP!")
            return
        
        uploaded = 0
        start = time.time()
        success = 0
        
        await status_msg.edit(f"🚀 <b>Upload started...</b> <i>{len(files)} files</i>")
        
        for i, file_path in enumerate(files, 1):
            repo_path = os.path.relpath(file_path, extract_dir)
            if upload_file(cfg["token"], cfg["repo"], cfg["branch"], file_path, repo_path):
                success += 1
            
            uploaded += os.path.getsize(file_path)
            elapsed = time.time() - start
            speed = uploaded / elapsed / 1024 / 1024 if elapsed else 0
            percent = min(100, int(uploaded / total_size * 100))
            
            await status_msg.edit(
                f"<code>[{progress_bar(percent)}] {percent}%</code>\n"
                f"⚡ <b>{speed:.1f}MB/s</b> | {i}/{len(files)} ✅{success}"
            )
        
        repo_url = f"https://github.com/{cfg['repo']}"
        os.system(f"rm -rf '{zip_path}' '{extract_dir}'")
        await status_msg.edit(f"✅ <b>Done!</b> [{success}/{len(files)}]\n🔗 <a href='{repo_url}'>View Repo</a>")
        
    except Exception as e:
        await status_msg.edit("❌ <b>Upload failed!</b>")
        print(f"Error: {e}")

# ==============================
# 👑 ADMIN PANEL
# ==============================
@app.on_message(filters.command("stats") & filters.private)
async def admin_stats(_, message):
    if not is_admin(message.from_user.id):
        return await message.reply("❌ Unauthorized!")
    
    users = get_all_users()
    active = sum(1 for uid in users if get_user(uid).get('token'))
    
    stats = f"""👑 <b>ADMIN PANEL - STATS</b>

👥 <b>Total Users</b>: <code>{len(users)}</code>
✅ <b>Active Users</b>: <code>{active}</code>
📊 <b>Active %</b>: <code>{active/len(users)*100:.1f}%</code>
💾 <b>DB Size</b>: <code>{os.path.getsize(DB)/1024:.1f} KB</code>

<b>👑 ADMIN COMMANDS:</b>
<code>/users</code> - List users
<code>/broadcast</code> - Mass message
<code>/clean</code> - Clean temp files
<code>/addadmin ID</code> - Add admin
<code>/admins</code> - List admins
"""
    await message.reply(stats, parse_mode="md")

@app.on_message(filters.command("users") & filters.private)
async def admin_users(_, message):
    if not is_admin(message.from_user.id):
        return
    
    users = get_all_users()
    if not users:
        return await message.reply("❌ No users")
    
    user_list = []
    for uid in users[:25]:
        data = get_user(uid)
        username = data.get('username', 'N/A')
        has_config = "✅" if data.get('token') else "❌"
        last_seen = data.get('last_seen', 'Never')[:10]
        user_list.append(f"{has_config} <code>{uid}</code> <code>{username}</code> <code>{last_seen}</code>")
    
    text = f"👥 <b>USERS</b> (<i>{len(users)} total</i>)\n\n" + "\n".join(user_list[:20])
    await message.reply(text, parse_mode="md")

@app.on_message(filters.command("broadcast") & filters.private)
async def admin_broadcast(_, message):
    if not is_admin(message.from_user.id):
        return
    
    if not message.reply_to_message:
        return await message.reply("❌ Reply to message to broadcast!")
    
    users = get_all_users()
    msg_text = message.reply_to_message.text or message.reply_to_message.caption or ""
    
    await message.reply(f"📢 <b>Broadcasting</b> to <code>{len(users)}</code> users...")
    success, failed = 0, 0
    
    for uid in users:
        try:
            await app.send_message(uid, msg_text)
            success += 1
            time.sleep(0.05)
        except:
            failed += 1
    
    await message.reply(
        f"✅ <b>BROADCAST COMPLETE</b>\n"
        f"📤 <b>Success</b>: <code>{success}</code>\n"
        f"❌ <b>Failed</b>: <code>{failed}</code>\n"
        f"📊 <b>Reach</b>: <code>{success/len(users)*100:.1f}%</code>",
        parse_mode="md"
    )

@app.on_message(filters.command("clean") & filters.private)
async def admin_clean(_, message):
    if not is_admin(message.from_user.id):
        return
    
    cleaned_dl = len(os.listdir(DL)) if os.path.exists(DL) else 0
    cleaned_ext = len(os.listdir(EXT)) if os.path.exists(EXT) else 0
    
    os.system(f"rm -rf {DL}/* {EXT}/* 2>/dev/null")
    os.makedirs(DL, exist_ok=True)
    os.makedirs(EXT, exist_ok=True)
    
    await message.reply(
        f"🧹 <b>Cleaned!</b>\n"
        f"📁 <b>Downloads</b>: <code>{cleaned_dl}</code> files\n"
        f"📦 <b>Extracted</b>: <code>{cleaned_ext}</code> folders",
        parse_mode="md"
    )

@app.on_message(filters.command("addadmin") & filters.private)
async def add_admin(_, message):
    if not is_admin(message.from_user.id):
        return
    
    try:
        new_id = int(message.text.split()[1])
        if new_id not in ADMIN_IDS:
            ADMIN_IDS.append(new_id)
            await message.reply(f"✅ Admin <code>{new_id}</code> added!")
        else:
            await message.reply("❌ Already admin!")
    except:
        await message.reply("❌ <b>Usage:</b> <code>/addadmin 123456789</code>", parse_mode="md")

@app.on_message(filters.command("admins") & filters.private)
async def list_admins(_, message):
    if not is_admin(message.from_user.id):
        return
    
    admin_list = "\n".join([f"<code>{aid}</code>" for aid in ADMIN_IDS])
    await message.reply(f"👑 <b>ADMINS</b>\n\n{admin_list}", parse_mode="md")

# ==============================
# RUN
# ==============================
if __name__ == "__main__":
    print("🚀 Github Push Bot + Admin Panel Started!")
    print("✅ Parse mode fixed: 'md' instead of 'markdown'")
    app.run()