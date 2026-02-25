import os
import json
import time
import zipfile
import base64
import requests
from datetime import datetime
from pyrogram import Client, filters

# ==============================
# CONFIG - CHANGE THESE
# ==============================
API_ID = 22657083
API_HASH = "d6186691704bd901bdab275ceaab88f3"
BOT_TOKEN = "8757979136:AAGJ7vwPPwf_BypyYk1i9LMNPfOJ2nMP5Ac"

# 👑 YOUR TELEGRAM USER ID (get from @userinfobot)
ADMIN_IDS = [2083251445]  

DB = "users.json"
DL = "downloads"
EXT = "extracted"

os.makedirs(DL, exist_ok=True)
os.makedirs(EXT, exist_ok=True)

if not os.path.exists(DB):
    with open(DB, "w") as f:
        json.dump({}, f)

app = Client("GithubPushBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ==============================
# FUNCTIONS
# ==============================
def is_admin(user_id):
    return user_id in ADMIN_IDS

def save_user(uid, data):
    db = json.load(open(DB))
    db[str(uid)] = {**(db.get(str(uid), {})), **data, "last_seen": datetime.now().isoformat()}
    with open(DB, "w") as f:
        json.dump(db, f, indent=4)

def get_user(uid):
    try:
        return json.load(open(DB)).get(str(uid), {})
    except:
        return {}

def get_all_users():
    try:
        return [int(uid) for uid in json.load(open(DB)).keys()]
    except:
        return []

def create_repo(token, repo_name, visibility="private"):
    url = "https://api.github.com/user/repos"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    data = {"name": repo_name, "private": visibility.lower() == "private", "auto_init": True}
    r = requests.post(url, json=data, headers=headers)
    return r.status_code == 201

def upload_file(token, repo, branch, file_path, repo_path):
    try:
        with open(file_path, "rb") as f:
            content = base64.b64encode(f.read()).decode()
        url = f"https://api.github.com/repos/{repo}/contents/{repo_path}"
        headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
        data = {"message": f"Upload {repo_path}", "content": content, "branch": branch}
        r = requests.put(url, json=data, headers=headers)
        return r.status_code in [200, 201]
    except:
        return False

def progress_bar(percent):
    filled = int(percent / 10)
    return "█" * filled + "░" * (10 - filled)

# ==============================
# COMMANDS
# ==============================
@app.on_message(filters.command("start"))
async def start(_, message):
    await message.reply("""
🤖 Github Push Bot

Commands:
/makeconfig - Setup repo
/config - View config  
/push - Upload ZIP (reply to ZIP)

Usage:
1. /makeconfig TOKEN|BRANCH|REPO|private
2. Send ZIP file
3. Reply /push

Admin: /stats /users /broadcast
""")

@app.on_message(filters.command("makeconfig"))
async def makeconfig(_, message):
    try:
        args = message.text.split(maxsplit=1)[1]
        token, branch, repo, vis = [x.strip() for x in args.split("|")]
        if vis.lower() not in ["private", "public"]:
            return await message.reply("Use private/public")
        
        repo_name = repo.split("/")[-1]
        if create_repo(token, repo_name, vis):
            save_user(message.from_user.id, {
                "token": token, "branch": branch, "repo": repo, "visibility": vis,
                "username": message.from_user.username or "N/A"
            })
            await message.reply("✅ Config saved & repo created!")
        else:
            await message.reply("❌ Failed to create repo")
    except:
        await message.reply("""
Usage:
/makeconfig TOKEN | BRANCH | USER/REPO | private/public

Example:
/makeconfig ghp_xxx | main | user/repo | private
        """)

@app.on_message(filters.command("config"))
async def show_config(_, message):
    cfg = get_user(message.from_user.id)
    if not cfg:
        return await message.reply("No config. Use /makeconfig")
    await message.reply(f"""
Config:
Repo: {cfg['repo']}
Branch: {cfg['branch']}
Visibility: {cfg['visibility'].title()}
    """)

@app.on_message(filters.command("push"))
async def push_zip(client, message):

    if not message.reply_to_message:
        return await message.reply("❌ Reply to ZIP file!")

    doc = message.reply_to_message.document
    if not doc or not doc.file_name.lower().endswith(".zip"):
        return await message.reply("❌ ZIP file only!")

    cfg = get_user(message.from_user.id)
    if not cfg:
        return await message.reply("⚠️ Setup first using /makeconfig")

    status = await message.reply("📥 Downloading ZIP...")

    try:
        # ======================
        # DOWNLOAD
        # ======================
        zip_path = await message.reply_to_message.download(
            file_name=f"{DL}/{doc.file_name}"
        )

        await status.edit("📦 Extracting ZIP...")

        extract_dir = f"{EXT}/{doc.file_name[:-4]}"
        os.makedirs(extract_dir, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(extract_dir)

        # ======================
        # REMOVE ROOT FOLDER
        # ======================
        items = os.listdir(extract_dir)

        if len(items) == 1:
            first = os.path.join(extract_dir, items[0])
            if os.path.isdir(first):
                extract_dir = first

        # ======================
        # COLLECT FILES
        # ======================
        files = []
        total_size = 0

        for root, _, filenames in os.walk(extract_dir):
            for name in filenames:
                path = os.path.join(root, name)
                files.append(path)
                total_size += os.path.getsize(path)

        if not files:
            return await status.edit("❌ ZIP empty!")

        await status.edit(f"🚀 Uploading {len(files)} files...")

        uploaded = 0
        success = 0
        start = time.time()

        # ======================
        # UPLOAD LOOP
        # ======================
        for i, file_path in enumerate(files, 1):

            repo_path = os.path.relpath(
                file_path,
                extract_dir
            ).replace("\\", "/")

            ok = upload_file(
                cfg["token"],
                cfg["repo"],
                cfg["branch"],
                file_path,
                repo_path
            )

            if ok:
                success += 1

            uploaded += os.path.getsize(file_path)

            percent = int((uploaded / total_size) * 100)
            elapsed = time.time() - start
            speed = uploaded / elapsed / 1024 / 1024 if elapsed else 0

            await status.edit(
                f"📤 Uploading...\n"
                f"[{progress_bar(percent)}] {percent}%\n"
                f"⚡ {speed:.2f} MB/s\n"
                f"📁 {i}/{len(files)} ✅{success}"
            )

        # ======================
        # CLEANUP
        # ======================
        os.system(f"rm -rf '{zip_path}' '{EXT}/{doc.file_name[:-4]}'")

        repo_url = f"https://github.com/{cfg['repo']}"

        await status.edit(
            f"✅ Upload Complete!\n\n"
            f"📦 Files: {success}/{len(files)}\n"
            f"🔗 Repo:\n{repo_url}"
        )

    except Exception as e:
        print(e)
        await status.edit("❌ Upload Failed!")

# ==============================
# ADMIN COMMANDS
# ==============================
@app.on_message(filters.command("stats"))
async def admin_stats(_, message):
    if not is_admin(message.from_user.id):
        return
    users = get_all_users()
    active = sum(1 for uid in users if get_user(uid).get('token'))
    await message.reply(f"""
ADMIN STATS:
Total Users: {len(users)}
Active Users: {active}
Active %: {active/len(users)*100:.1f}%
DB Size: {os.path.getsize(DB)/1024:.1f} KB

COMMANDS:
/users /broadcast /clean /addadmin ID /admins
    """)

@app.on_message(filters.command("users"))
async def admin_users(_, message):
    if not is_admin(message.from_user.id):
        return
    users = get_all_users()
    if not users:
        return await message.reply("No users")
    
    text = "USERS:\n"
    for uid in users[:20]:
        data = get_user(uid)
        status = "✅" if data.get('token') else "❌"
        username = data.get('username', 'N/A')
        text += f"{status} {uid} {username}\n"
    await message.reply(text)

@app.on_message(filters.command("broadcast"))
async def admin_broadcast(_, message):
    if not is_admin(message.from_user.id):
        return
    if not message.reply_to_message:
        return await message.reply("Reply to message!")
    
    users = get_all_users()
    text = message.reply_to_message.text or message.reply_to_message.caption or ""
    
    await message.reply(f"Broadcasting to {len(users)} users...")
    success = failed = 0
    
    for uid in users:
        try:
            await app.send_message(uid, text)
            success += 1
            time.sleep(0.1)
        except:
            failed += 1
    
    await message.reply(f"Broadcast done!\nSuccess: {success}\nFailed: {failed}")

@app.on_message(filters.command("clean"))
async def admin_clean(_, message):
    if not is_admin(message.from_user.id):
        return
    os.system(f"rm -rf {DL}/* {EXT}/* 2>/dev/null")
    await message.reply("Temp files cleaned!")

@app.on_message(filters.command("addadmin"))
async def add_admin(_, message):
    if not is_admin(message.from_user.id):
        return
    try:
        new_id = int(message.text.split()[1])
        if new_id not in ADMIN_IDS:
            ADMIN_IDS.append(new_id)
            await message.reply(f"Admin {new_id} added!")
        else:
            await message.reply("Already admin!")
    except:
        await message.reply("Usage: /addadmin 123456789")

@app.on_message(filters.command("admins"))
async def list_admins(_, message):
    if not is_admin(message.from_user.id):
        return
    await message.reply(f"Admins: {ADMIN_IDS}")

print("🚀 Bot Started! NO PARSE_MODE USED!")
app.run()