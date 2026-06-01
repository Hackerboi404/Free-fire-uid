# 🤖 Telegram Group Management Bot

## Setup Kaise Kare

### Step 1: Bot Token Lo
1. Telegram par `@BotFather` ko message karo
2. `/newbot` command do
3. Naam aur username do
4. Token copy kar lo

### Step 2: Apna User ID Lo
- `@userinfobot` ko `/start` karo — woh aapka User ID batayega

### Step 3: Bot Ko Group Admin Banao
Bot ko group mein add karo aur **Admin** banao in permissions ke saath:
- ✅ Delete messages
- ✅ Ban users
- ✅ Restrict members
- ✅ Pin messages
- ✅ Invite users via link

> ⚠️ Aap khud non-admin bhi reh sakte ho — commands tab bhi kaam karenge!

---

## Render Par Deploy Kaise Kare

### Step 1: GitHub Par Upload Karo
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

### Step 2: Render.com Par Jao
1. [render.com](https://render.com) par free account banao
2. **New → Web Service** click karo
3. GitHub repo connect karo
4. Ye settings rakho:
   - **Environment**: Python
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bot.py`

### Step 3: Environment Variables Set Karo
Render dashboard mein **Environment** tab par:
| Key | Value |
|-----|-------|
| `BOT_TOKEN` | BotFather se mila token |
| `OWNER_ID` | Aapka Telegram User ID |

### Step 4: Deploy Karo
**Create Web Service** click karo — bot live ho jayega!

---

## Commands List

| Command | Kaam |
|---------|------|
| `/auth` | User ko authorize karo (reply karo) |
| `/unauth` | Authorization hatao |
| `/authlist` | Authorized users dekho |
| `/ban` | User ko ban karo |
| `/unban` | Ban hatao |
| `/mute` | User ko mute karo |
| `/unmute` | Mute hatao |
| `/kick` | User ko kick karo |
| `/punish` | Messages auto-delete hote rahenge |
| `/unpunish` | Punishment hatao |
| `/purge` | Kai messages ek saath delete karo |
| `/pin` | Message pin karo |
| `/unpin` | Message unpin karo |
| `/lock [type]` | Content type lock karo |
| `/unlock [type]` | Unlock karo |
| `/locks` | Active locks dekho |

### Lock Types:
`text`, `media`, `photo`, `video`, `sticker`, `gif`, `poll`, `link`, `invite`, `pin`, `info`, `all`

---

## Important Notes
- **Bot admin hona chahiye** — baaki sab kuch automatic hai
- **Aap non-admin bhi reh sakte ho** — aapke commands tab bhi kaam karenge
- Authorized users bhi sabhi commands use kar sakte hain
- SQLite database automatically create ho jaata hai
