# 🚀 Deploy to Your Hostinger VPS

**VPS IP:** 31.97.35.144

---

## 🔐 Step 1: Initial Connection & Security Setup

### Connect to VPS
```bash
ssh root@31.97.35.144
# When prompted, enter the password provided
```

### Immediately Change Root Password
```bash
passwd
# Enter a NEW strong password and save it securely
```

### Update System
```bash
apt update && apt upgrade -y
```

### Create Deploy User (More Secure)
```bash
# Create new user
adduser deploy
# Set a strong password when prompted

# Add to sudo group
usermod -aG sudo deploy

# Switch to deploy user
su - deploy
```

---

## 🐳 Step 2: Install Docker & Dependencies

```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add deploy user to docker group
sudo usermod -aG docker deploy

# Install Docker Compose
sudo apt install docker-compose -y

# Install Nginx
sudo apt install nginx -y

# Install Git
sudo apt install git -y

# Install Certbot (for SSL)
sudo apt install certbot python3-certbot-nginx -y

# Restart to apply group changes
exit
# Login again as deploy user
ssh deploy@31.97.35.144
```

---

## 📦 Step 3: Deploy Backend

### Clone Repository
```bash
cd ~
git clone https://github.com/YOUR_USERNAME/Safety_Agent.git
cd Safety_Agent
```

### Create Production Environment File
```bash
cd docker-compose
nano .postgres.production
```

**Paste this content:**
```env
POSTGRES_DB=oinride_production
POSTGRES_USER=oinride_admin
POSTGRES_PASSWORD=SafetyAgent2025!SecureDB
POSTGRES_PASSWORD_FLAT=SafetyAgent2025!SecureDB
POSTGRES_HOST=db
POSTGRES_PORT=5432
GOOGLE_API_KEY=YOUR_GOOGLE_API_KEY_HERE
PGADMIN_EMAIL=admin@oinride.com
PGADMIN_PASSWORD=PgAdmin2025!Secure
```

**Save:** Press `Ctrl+X`, then `Y`, then `Enter`

**⚠️ IMPORTANT:** Replace `YOUR_GOOGLE_API_KEY_HERE` with your actual Google API key

### Update Django Settings
```bash
cd ~/Safety_Agent
nano Safety_agent_Django/settings.py
```

**Find and update these lines:**

```python
# Change DEBUG to False
DEBUG = False

# Update ALLOWED_HOSTS (add your domain or IP)
ALLOWED_HOSTS = [
    '31.97.35.144',
    'api.your-domain.com',  # If you have a domain
    'localhost',
]

# Add CSRF trusted origins
CSRF_TRUSTED_ORIGINS = [
    'http://31.97.35.144',
    'https://31.97.35.144',
    'https://api.your-domain.com',  # If you have a domain
]
```

**Save:** Press `Ctrl+X`, then `Y`, then `Enter`

### Add Gunicorn to Requirements
```bash
echo "gunicorn==21.2.0" >> requirements.txt
```

### Build and Start Services
```bash
cd docker-compose

# Build containers
docker-compose -f docker-compose.production.yml build

# Start services
docker-compose -f docker-compose.production.yml up -d

# Check status
docker-compose -f docker-compose.production.yml ps

# View logs to ensure everything is running
docker-compose -f docker-compose.production.yml logs -f web
# Press Ctrl+C to exit logs
```

### Run Database Migrations
```bash
docker-compose -f docker-compose.production.yml exec web python manage.py migrate
```

### Create Django Superuser
```bash
docker-compose -f docker-compose.production.yml exec web python manage.py createsuperuser
# Follow prompts to create admin user
```

### Test Backend Locally
```bash
curl http://localhost:8000/chatlog/get-all-users/
# Should return JSON with users
```

---

## 🌐 Step 4: Configure Nginx

### Create Backend Configuration
```bash
sudo nano /etc/nginx/sites-available/safety-agent-backend
```

**Paste this content:**
```nginx
server {
    listen 80;
    server_name 31.97.35.144;

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }

    location /media/ {
        alias /home/deploy/Safety_Agent/media/;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }

    location /static/ {
        alias /home/deploy/Safety_Agent/staticfiles/;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }
}
```

**Save:** Press `Ctrl+X`, then `Y`, then `Enter`

### Enable Site
```bash
# Enable the configuration
sudo ln -s /etc/nginx/sites-available/safety-agent-backend /etc/nginx/sites-enabled/

# Remove default site
sudo rm /etc/nginx/sites-enabled/default

# Test configuration
sudo nginx -t

# Restart Nginx
sudo systemctl restart nginx

# Check status
sudo systemctl status nginx
```

---

## 🔥 Step 5: Configure Firewall

```bash
# Allow SSH
sudo ufw allow 22

# Allow HTTP
sudo ufw allow 80

# Allow HTTPS
sudo ufw allow 443

# Enable firewall
sudo ufw enable

# Check status
sudo ufw status
```

---

## ✅ Step 6: Test Your Deployment

### Test from your local machine:
```bash
# Test health check
curl http://31.97.35.144/chatlog/get-all-users/

# Test in browser
# Open: http://31.97.35.144/admin/
# Login with the superuser you created
```

---

## 🔒 Step 7: Setup SSL (If you have a domain)

**Only do this if you have a domain pointing to 31.97.35.144**

### Configure DNS
Before running SSL setup, ensure your domain's A record points to: `31.97.35.144`

### Get SSL Certificate
```bash
# Replace api.your-domain.com with your actual domain
sudo certbot --nginx -d api.your-domain.com
```

Certbot will:
- Automatically configure SSL
- Set up auto-renewal
- Redirect HTTP to HTTPS

---

## 📊 Step 8: Monitor Your Application

### View Backend Logs
```bash
cd ~/Safety_Agent/docker-compose
docker-compose -f docker-compose.production.yml logs -f web
```

### View Nginx Logs
```bash
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### Check Service Status
```bash
# Docker containers
docker ps

# Nginx
sudo systemctl status nginx

# Disk space
df -h

# Memory usage
free -h
```

---

## 🔄 Step 9: Deploy Frontend (Next.js)

### Install Node.js
```bash
# Install Node.js 20.x
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Verify
node --version
npm --version
```

### Clone Frontend Repository
```bash
cd ~
git clone https://github.com/YOUR_USERNAME/oinride-agent-ai.git
cd oinride-agent-ai
```

### Create Environment File
```bash
nano .env.local
```

**Add:**
```env
# API Configuration (server-side proxy)
API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_API_TARGET=http://localhost:8000

# Next.js Configuration
NEXT_PUBLIC_APP_URL=http://31.97.35.144
```

### Create PM2 Ecosystem File (Recommended - Persists After Reboot)
```bash
nano ecosystem.config.cjs
```
**Note:** Use `.cjs` extension because the project uses ES modules (`"type": "module"` in package.json).

**Add:**
```javascript
module.exports = {
  apps: [
    {
      name: 'oinride-frontend',
      cwd: '/home/deploy/oinride-agent-ai',
      script: 'npm',
      args: 'start',
      env: {
        NODE_ENV: 'production',
        PORT: 3000,
        API_BASE_URL: 'http://localhost:8000',
        NEXT_PUBLIC_API_TARGET: 'http://localhost:8000',
        NEXT_PUBLIC_APP_URL: 'http://31.97.35.144'
      },
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '500M',
      error_file: '/home/deploy/logs/frontend-error.log',
      out_file: '/home/deploy/logs/frontend-out.log',
      log_file: '/home/deploy/logs/frontend-combined.log',
      time: true
    }
  ]
};
```

### Build and Start
```bash
# Create logs directory
mkdir -p ~/logs

# Install dependencies (use --legacy-peer-deps if needed)
npm install --legacy-peer-deps

# Build the application
npm run build

# Install PM2 globally
sudo npm install -g pm2

# Start with PM2 using ecosystem file
pm2 start ecosystem.config.cjs

# Save PM2 configuration (IMPORTANT - makes it persist)
pm2 save

# Setup PM2 to start on boot
pm2 startup
# Copy and run the command it outputs (looks like: sudo env PATH=... pm2 startup systemd -u deploy --hp /home/deploy)

# Verify the startup hook
pm2 save
```

### Verify PM2 is Working
```bash
# Check status
pm2 status

# Should show:
# ┌─────┬────────────────────┬─────────────┬─────────┬─────────┬──────────┐
# │ id  │ name               │ namespace   │ mode    │ status  │ cpu      │
# ├─────┼────────────────────┼─────────────┼─────────┼─────────┼──────────┤
# │ 0   │ oinride-frontend   │ default     │ fork    │ online  │ 0%       │
# └─────┴────────────────────┴─────────────┴─────────┴─────────┴──────────┘

# View logs
pm2 logs oinride-frontend

# Monitor resources
pm2 monit
```

### Configure Nginx for Frontend
```bash
sudo nano /etc/nginx/sites-available/safety-agent-frontend
```

**Add:**
```nginx
server {
    listen 80;
    server_name your-frontend-domain.com;  # Or use another IP/subdomain

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/safety-agent-frontend /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## 🛠️ Common Commands

### Backend Management
```bash
cd ~/Safety_Agent/docker-compose

# Restart backend
docker-compose -f docker-compose.production.yml restart web

# View logs
docker-compose -f docker-compose.production.yml logs -f

# Stop all
docker-compose -f docker-compose.production.yml down

# Start all
docker-compose -f docker-compose.production.yml up -d

# Update code
cd ~/Safety_Agent
git pull
cd docker-compose
docker-compose -f docker-compose.production.yml restart web
```

### Frontend Management
```bash
# Restart
pm2 restart oinride-frontend

# View logs
pm2 logs oinride-frontend

# Status
pm2 status

# Stop frontend
pm2 stop oinride-frontend

# Delete and recreate (if needed)
pm2 delete oinride-frontend
pm2 start ecosystem.config.cjs

# Update code
cd ~/oinride-agent-ai
git pull
npm install --legacy-peer-deps
npm run build
pm2 restart oinride-frontend

# If PM2 forgets the app after reboot, recreate it:
cd ~/oinride-agent-ai
pm2 start ecosystem.config.cjs
pm2 save
```

---

## 📦 Backup Script

Create automated backups:

```bash
nano ~/backup.sh
```

**Add:**
```bash
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/home/deploy/backups"

mkdir -p $BACKUP_DIR

# Backup database
docker exec safety_agent_db pg_dump -U oinride_admin oinride_production > $BACKUP_DIR/db_$DATE.sql

# Backup media files
tar -czf $BACKUP_DIR/media_$DATE.tar.gz /home/deploy/Safety_Agent/media/

# Keep only last 7 days
find $BACKUP_DIR -name "*.sql" -mtime +7 -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +7 -delete

echo "Backup completed: $DATE"
```

```bash
# Make executable
chmod +x ~/backup.sh

# Test
./backup.sh

# Schedule daily backups at 2 AM
crontab -e
# Add this line:
0 2 * * * /home/deploy/backup.sh >> /home/deploy/backup.log 2>&1
```

---

## ✅ Deployment Checklist

- [ ] Connected to VPS
- [ ] Changed root password
- [ ] Created deploy user
- [ ] Installed Docker & dependencies
- [ ] Cloned repository
- [ ] Created `.postgres.production` file
- [ ] Updated Django settings
- [ ] Built Docker containers
- [ ] Ran migrations
- [ ] Created superuser
- [ ] Configured Nginx
- [ ] Enabled firewall
- [ ] Tested backend API
- [ ] Deployed frontend (if applicable)
- [ ] Setup SSL (if domain available)
- [ ] Configured backups

---

## 🆘 Troubleshooting

**Can't connect to backend:**
```bash
# Check if containers are running
docker ps

# Check backend logs
docker-compose -f docker-compose.production.yml logs web

# Check Nginx
sudo nginx -t
sudo systemctl status nginx

# Check firewall
sudo ufw status
```

**502 Bad Gateway:**
```bash
# Backend is probably down
docker-compose -f docker-compose.production.yml restart web
```

**Database connection error:**
```bash
# Check database container
docker ps | grep db
docker-compose -f docker-compose.production.yml logs db
```

**PM2 forgets app name after reboot:**
```bash
# This happens when pm2 save wasn't run or startup wasn't configured

# Step 1: Go to frontend directory
cd ~/oinride-agent-ai

# Step 2: Check if ecosystem.config.cjs exists
ls -la ecosystem.config.cjs

# Step 3: If missing, create it (see Step 9 above)

# Step 4: Start the app
pm2 start ecosystem.config.cjs

# Step 5: IMPORTANT - Save the configuration
pm2 save

# Step 6: Setup startup (run as the deploy user)
pm2 startup
# Copy and execute the command it outputs

# Step 7: Save again after startup setup
pm2 save

# Verify it's saved
pm2 list
cat ~/.pm2/dump.pm2
```

**PM2 shows "errored" status:**
```bash
# Check the error logs
pm2 logs oinride-frontend --err --lines 50

# Common fixes:
# 1. Port 3000 already in use
lsof -i :3000
kill -9 <PID>

# 2. Build not done
cd ~/oinride-agent-ai
npm run build
pm2 restart oinride-frontend

# 3. Missing .next folder
ls -la .next
# If missing, rebuild: npm run build

# 4. Node modules issue
rm -rf node_modules
npm install --legacy-peer-deps
npm run build
pm2 restart oinride-frontend
```

---

## 📞 Access Points After Deployment

- **API:** http://31.97.35.144/
- **Django Admin:** http://31.97.35.144/admin/
- **pgAdmin:** http://31.97.35.144:5050/ (accessible via SSH tunnel)
- **API Documentation:** http://31.97.35.144/chatlog/

---

## 🎯 Next Steps

1. Test all API endpoints
2. Upload test PDFs
3. Test chat functionality
4. Configure your frontend to use the backend API
5. Setup monitoring (optional)
6. Configure domain name (optional)

---

**Your backend will be live at:** http://31.97.35.144

**Ready to deploy? Follow the steps above!** 🚀
