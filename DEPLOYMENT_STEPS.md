# 🚀 VPS Deployment - Step by Step Guide

## ❓ Your Questions Answered:

### 1. **Where will folders be added?**
```
/home/deploy/
├── Safety_Agent/              ← Backend (Django + PostgreSQL)
│   ├── chatlog/
│   ├── docker-compose/
│   ├── media/                 ← Your uploaded PDFs
│   └── ...
│
└── oinride-agent-ai/          ← Frontend (Next.js)
    ├── src/
    ├── .next/
    └── ...
```

### 2. **Will this deploy both frontend AND backend?**
**YES!** ✅ The script deploys:
- ✅ Backend (Django API + PostgreSQL + Docker)
- ✅ Frontend (Next.js + React)
- ✅ Nginx (to serve both)
- ✅ Everything configured and connected

### 3. **Should we use root or create a deploy user?**
**Create a deploy user** (MUCH safer!) 🔐

The script will:
1. First run as **root** → Creates `deploy` user
2. Then run as **deploy** → Installs everything

---

## 🔧 Deployment Instructions

### Step 1: Connect to VPS as Root

```bash
ssh root@31.97.35.144
# Password: -Wckg0LS2j'E63qSF(Y4
```

### Step 2: Download and Run Script (as ROOT)

```bash
# Download the script
wget https://raw.githubusercontent.com/HabibaIbrahim/Safety_Agent/main/deploy-secure.sh

# Make it executable
chmod +x deploy-secure.sh

# Run as ROOT (it will create deploy user)
./deploy-secure.sh
```

**What happens:**
- ✅ Creates `deploy` user
- ✅ Adds `deploy` to sudo and docker groups
- ✅ Asks you to set a password for `deploy` user
- ✅ Tells you to switch to `deploy` user

### Step 3: Switch to Deploy User

```bash
# Switch to deploy user
su - deploy

# Run the script again (now as deploy user)
./deploy-secure.sh
```

**What happens:**
- ✅ Installs Docker, Docker Compose, Node.js, PM2, Git, Nginx
- ✅ Clones backend repository to `/home/deploy/Safety_Agent`
- ✅ Clones frontend repository to `/home/deploy/oinride-agent-ai`
- ✅ Asks for your **Google API Key** and **Database Password**
- ✅ Builds and starts backend with Docker
- ✅ Builds and starts frontend with PM2
- ✅ Configures Nginx to serve both

**Note:** If Docker is installed for the first time, you'll need to:
1. Log out: `exit`
2. Log back in: `ssh deploy@31.97.35.144`
3. Run script again: `./deploy-secure.sh`

### Step 4: Create Django Admin User

```bash
cd ~/Safety_Agent/docker-compose
docker-compose -f docker-compose.production.yml exec web python manage.py createsuperuser
```

### Step 5: Test Your Deployment

**Test Backend API:**
```bash
curl http://31.97.35.144/chatlog/get-all-users/
```

**Open in Browser:**
- Frontend: `http://31.97.35.144/`
- Admin Panel: `http://31.97.35.144/admin/`

---

## 📊 Managing Your Application

### View Logs

**Backend Logs:**
```bash
cd ~/Safety_Agent/docker-compose
docker-compose -f docker-compose.production.yml logs -f web
```

**Frontend Logs:**
```bash
pm2 logs frontend
```

**Nginx Logs:**
```bash
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### Check Status

**Backend Status:**
```bash
cd ~/Safety_Agent/docker-compose
docker-compose -f docker-compose.production.yml ps
```

**Frontend Status:**
```bash
pm2 status
```

**Nginx Status:**
```bash
sudo systemctl status nginx
```

### Restart Services

**Restart Backend:**
```bash
cd ~/Safety_Agent/docker-compose
docker-compose -f docker-compose.production.yml restart
```

**Restart Frontend:**
```bash
pm2 restart frontend
```

**Restart Nginx:**
```bash
sudo systemctl restart nginx
```

### Update Application

**Update Backend:**
```bash
cd ~/Safety_Agent
git pull
cd docker-compose
docker-compose -f docker-compose.production.yml restart
```

**Update Frontend:**
```bash
cd ~/oinride-agent-ai
git pull
npm install
npm run build
pm2 restart frontend
```

---

## 🔒 Security Notes

### Deployed User Setup:
- **User:** `deploy`
- **Home:** `/home/deploy`
- **Groups:** `sudo`, `docker`
- **Password:** Set during deployment

### Firewall Rules:
- Port 22 (SSH) ✅
- Port 80 (HTTP) ✅
- Port 443 (HTTPS) ✅

### Passwords You'll Need:
1. **Deploy user password** - Set during Step 2
2. **Database password** - Set during Step 3
3. **Google API Key** - Provided during Step 3
4. **Django admin password** - Set during Step 4

---

## 🌐 Application Structure After Deployment

```
VPS: 31.97.35.144
│
├── Frontend (Next.js)
│   URL: http://31.97.35.144/
│   Location: /home/deploy/oinride-agent-ai
│   Process: PM2
│   Port: 3000 (internal)
│
├── Backend (Django)
│   API: http://31.97.35.144/chatlog/
│   Admin: http://31.97.35.144/admin/
│   Location: /home/deploy/Safety_Agent
│   Process: Docker (Gunicorn)
│   Port: 8000 (internal)
│
├── Database (PostgreSQL)
│   Location: Docker container
│   Port: 5432 (internal)
│
└── Nginx (Reverse Proxy)
    Port: 80 (public)
    Serves: Frontend + Backend
```

---

## ❓ Troubleshooting

### Can't connect to application?
```bash
# Check all services
pm2 status
docker ps
sudo systemctl status nginx

# Check logs
pm2 logs frontend
cd ~/Safety_Agent/docker-compose && docker-compose logs
sudo tail /var/log/nginx/error.log
```

### Frontend shows 502 Bad Gateway?
```bash
# Frontend is probably down
pm2 restart frontend
pm2 logs frontend
```

### Backend API not responding?
```bash
# Backend is probably down
cd ~/Safety_Agent/docker-compose
docker-compose -f docker-compose.production.yml restart
docker-compose -f docker-compose.production.yml logs
```

### Can't upload files?
```bash
# Check media directory permissions
ls -la ~/Safety_Agent/media
sudo chown -R deploy:deploy ~/Safety_Agent/media
```

---

## 📞 Quick Reference

**SSH to VPS:**
```bash
ssh deploy@31.97.35.144
```

**Stop Everything:**
```bash
# Stop backend
cd ~/Safety_Agent/docker-compose
docker-compose -f docker-compose.production.yml down

# Stop frontend
pm2 stop frontend

# Stop Nginx
sudo systemctl stop nginx
```

**Start Everything:**
```bash
# Start backend
cd ~/Safety_Agent/docker-compose
docker-compose -f docker-compose.production.yml up -d

# Start frontend
pm2 start frontend

# Start Nginx
sudo systemctl start nginx
```

---

**Deployment takes ~10-15 minutes total.**

**Ready to deploy? Follow the steps above!** 🚀
