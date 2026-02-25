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
# DATABASE
# ==============================
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
# GITHUB API FUNCTIONS
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

# ==============================
# PROGRESS BAR
# ==============================
def progress_bar(percent):
    filled = int(percent / 10)
    return "█" * filled + "░" * (10 - filled)

# ==============================
# /MAKECONFIG
# ==============================
@app.on_message(filters.command("makeconfig"))
async def makeconfig(_, message):
    try:
        args = message.text.split(None, 1)[1]
        token, branch, repo, vis = [x.strip() for x in args.split("|")]
        
        vis = vis.lower()
        if vis not in ["private", "public"]:
            return await message.reply("❌ Use `private` or `public` for visibility")
        
        # Test token and create repo
        repo_name = repo.split("/")[-1]
        if create_repo(token, repo_name, vis):
            save_user(message.from_user.id, {
                "token": token,
                "branch": branch,
                "repo": repo,
                "visibility": vis
            })
            await message.reply("✅ Config saved & repo created successfully!")
        else:
            await message.reply("❌ Failed to create repo. Check your GitHub token.")
            
    except Exception as e:
        await message.reply(
            "```Usage:\n/makeconfig TOKEN | BRANCH | USER/REPO | private/public```\n\n"
            "Example:\n`/makeconfig ghp_xxx | main | username/myrepo | private`",
            parse_mode="markdown"
        )

# ==============================
# /CONFIG
# ==============================
@app.on_message(filters.command("config"))
async def show_config(_, message):
    cfg = get_user(message.from_user.id)
    
    if not cfg:
        return await message.reply("❌ No config found. Use /makeconfig first.")
    
    config_text = f"""⚙️ **Your Config**

📂 **Repo**: `{cfg['repo']}`
🌿 **Branch**: `{cfg['branch']}`
🔒 **Visibility**: `{cfg['visibility'].title()}`
"""
    await message.reply(config_text, parse_mode="markdown")

# ==============================
# /PUSH ZIP
# ==============================
@app.on_message(filters.command("push"))
async def push_zip(client, message):
    if not message.reply_to_message:
        return await message.reply("❌ Reply to a ZIP file!")
    
    doc = message.reply_to_message.document
    if not doc or not doc.file_name.lower().endswith(".zip"):
        return await message.reply("❌ Please reply to a **ZIP file** only!")
    
    cfg = get_user(message.from_user.id)
    if not cfg:
        return await message.reply("❌ Setup config first: `/makeconfig`")
    
    status_msg = await message.reply("📥 **Downloading ZIP file...**")
    
    try:
        # Download ZIP
        zip_path = await message.reply_to_message.download(
            file_name=f"{DL}/{doc.file_name}"
        )
        await status_msg.edit("📦 **Extracting ZIP file...**")
        
        # Extract ZIP
        extract_dir = f"{EXT}/{doc.file_name[:-4]}"
        os.makedirs(extract_dir, exist_ok=True)
        
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(extract_dir)
        
        # Get all files
        files = []
        total_size = 0
        
        for root, _, filenames in os.walk(extract_dir):
            for filename in filenames:
                file_path = os.path.join(root, filename)
                files.append(file_path)
                total_size += os.path.getsize(file_path)
        
        if not files:
            await status_msg.edit("❌ No files found in ZIP!")
            return
        
        # Upload files
        uploaded = 0
        start_time = time.time()
        success_count = 0
        
        await status_msg.edit(
            f"🚀 **Upload Started**\n"
            f"📁 Files: {len(files)}\n"
            f"💾 Size: {total_size/1024/1024:.1f} MB"
        )
        
        for i, file_path in enumerate(files, 1):
            repo_path = os.path.relpath(file_path, extract_dir)
            
            if upload_file(
                cfg["token"], 
                cfg["repo"], 
                cfg["branch"], 
                file_path, 
                repo_path
            ):
                success_count += 1
            
            file_size = os.path.getsize(file_path)
            uploaded += file_size
            
            elapsed = time.time() - start_time
            speed = uploaded / elapsed / 1024 / 1024 if elapsed > 0 else 0
            remaining = total_size - uploaded
            eta = remaining / speed if speed > 0 else 0
            
            percent = min(100, int(uploaded / total_size * 100))
            
            await status_msg.edit(
                f"🚀 **Uploading to GitHub**\n\n"
                f"`[{progress_bar(percent)}] {percent}%`\n\n"
                f"⚡ **Speed**: {speed:.2f} MB/s\n"
                f"📄 **Files**: {i}/{len(files)} ✅{success_count}\n"
                f"⏳ **ETA**: {int(eta)}s"
            )
        
        # Cleanup
        os.system(f"rm -rf '{zip_path}' '{extract_dir}'")
        
        repo_url = f"https://github.com/{cfg['repo']}/tree/{cfg['branch']}"
        await status_msg.edit(
            f"✅ **Upload Completed!**\n\n"
            f"📊 **Stats**:\n"
            f"• Files: {len(files)}\n"
            f"• Success: {success_count}\n"
            f"• Failed: {len(files) - success_count}\n\n"
            f"🔗 **[View Repo]({repo_url})**",
            disable_web_page_preview=False
        )
        
    except Exception as e:
        await status_msg.edit("❌ **Upload failed!** Check logs or try again.")
        print(f"Error: {e}")

# ==============================
# /STATS
# ==============================
@app.on_message(filters.command("stats"))
async def stats(_, message):
    users = get_all_users()
    active_users = sum(1 for uid in users if get_user(uid).get('token'))
    
    stats_text = f"""📊 **Bot Stats**

👥 **Total Users**: `{len(users)}`
✅ **Active Users**: `{active_users}`
💾 **Database**: `{os.path.getsize(DB)} bytes`
"""
    await message.reply(stats_text, parse_mode="markdown")

# ==============================
# /USERS
# ==============================
@app.on_message(filters.command("users"))
async def list_users(_, message):
    users = get_all_users()
    if not users:
        return await message.reply("❌ No users found.")
    
    user_list = []
    for uid in users[:20]:  # Limit to 20 users
        user_data = get_user(uid)
        username = user_data.get('username', 'N/A')
        status = "✅ Active" if user_data.get('token') else "❌ Inactive"
        user_list.append(f"`{uid}` - {username} - {status}")
    
    users_text = "**Active Users:**\n" + "\n".join(user_list)
    await message.reply(users_text, parse_mode="markdown")

# ==============================
# /BROADCAST
# ==============================
@app.on_message(filters.command("broadcast"))
async def broadcast(_, message):
    if not message.reply_to_message:
        return await message.reply("❌ Reply to message to broadcast!")
    
    users = get_all_users()
    broadcast_msg = message.reply_to_message.text or message.reply_to_message.caption or " "
    
    success = 0
    failed = 0
    
    await message.reply(f"📢 Broadcasting to {len(users)} users...")
    
    for uid in users:
        try:
            await app.send_message(uid, broadcast_msg)
            success += 1
        except:
            failed += 1
    
    await message.reply(
        f"✅ **Broadcast Complete**\n"
        f"• Success: `{success}`\n"
        f"• Failed: `{failed}`",
        parse_mode="markdown"
    )

# ==============================
# START
# ==============================
@app.on_message(filters.command("start"))
async def start(_, message):
    welcome_text = """
🤖 **GitHub Push Bot**

**Commands:**
• `/makeconfig` - Setup repo config
• `/config` - View your config  
• `/push` - Upload ZIP (reply to ZIP)
• `/stats` - Bot statistics
• `/users` - List users (admin)
• `/broadcast` - Broadcast msg (admin)

**Usage:**
1. `/makeconfig TOKEN|BRANCH|REPO|private`
2. Send ZIP file
3. Reply `/push`
"""
    await message.reply(welcome_text, parse_mode="markdown")

# ==============================
# RUN BOT
# ==============================
if __name__ == "__main__":
    print("🚀 Starting GitHub Push Bot...")
    app.run()
