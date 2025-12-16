# Complete VPS Fresh Deployment Guide

## STEP 1: Wipe VPS Clean (Nuclear Option)

### Option A: Provider Control Panel (RECOMMENDED)
1. Go to your VPS hosting provider control panel
2. Look for "Reinstall OS" or "Rebuild VPS"
3. Select: **Ubuntu 22.04 LTS** (or latest stable)
4. This will completely wipe everything and start fresh
5. Wait 5-10 minutes for completion

### Option B: Manual Wipe (if provider doesn't support reinstall)
**⚠️ WARNING: This deletes EVERYTHING!**

```bash
# SSH into VPS
ssh root@31.97.35.144

# Backup ONLY the database (if you need it)
docker exec docker-compose-db-1 pg_dump -U pgadmin_z9f3 oinride > ~/backup.sql

# Stop all containers
docker stop $(docker ps -aq)
docker rm $(docker ps -aq)

# Remove all Docker images, volumes, networks
docker system prune -a --volumes -f

# Delete all files except /boot and /proc
cd /
rm -rf /home/* /root/* /opt/* /srv/* /tmp/* /var/tmp/*
rm -rf /usr/local/*

# Reboot to complete
reboot
```

---

## STEP 2: Fresh VPS Setup (After Reinstall)

SSH into your fresh VPS:
```bash
ssh root@31.97.35.144
```

### 2.1: Update System and Install Essentials

```bash
# Update package lists
apt update && apt upgrade -y

# Install essential tools
apt install -y \
    curl \
    wget \
    git \
    ufw \
    fail2ban \
    htop \
    build-essential

# Set timezone
timedatectl set-timezone America/New_York  # Change to your timezone
```

### 2.2: Create Non-Root User (Security Best Practice)

```bash
# Create new sudo user
adduser oinrideadmin
# Enter password when prompted

# Add to sudo group
usermod -aG sudo oinrideadmin

# Set up SSH keys for new user
mkdir -p /home/oinrideadmin/.ssh
chmod 700 /home/oinrideadmin/.ssh
```

**On your local machine**, copy your SSH key:
```bash
ssh-copy-id oinrideadmin@31.97.35.144
```

### 2.3: Configure Firewall (UFW)

```bash
# Default policies
ufw default deny incoming
ufw default allow outgoing

# Allow SSH (IMPORTANT: Do this BEFORE enabling!)
ufw allow 22/tcp

# Allow HTTP and HTTPS
ufw allow 80/tcp
ufw allow 443/tcp

# Enable firewall
ufw --force enable

# Check status
ufw status verbose
```

### 2.4: Install Docker and Docker Compose

```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Add user to docker group
usermod -aG docker oinrideadmin

# Install Docker Compose
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# Verify installation
docker --version
docker-compose --version
```

### 2.5: Install Node.js and npm

```bash
# Install Node.js 20.x LTS
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs

# Verify installation
node --version  # Should show v20.x
npm --version
```

### 2.6: Install Nginx

```bash
# Install Nginx
apt install -y nginx

# Start and enable Nginx
systemctl start nginx
systemctl enable nginx

# Check status
systemctl status nginx
```

---

## STEP 3: Deploy Oinride Backend (Django)

### 3.1: Clone Repository

```bash
# Create app directory
mkdir -p /opt/oinride
cd /opt/oinride

# Clone your repository
git clone https://github.com/MahmoudSayed0/OSA-Server.git backend
cd backend
```

### 3.2: Create Production .env File

```bash
# Create .env file
nano .env
```

**Paste this content** (UPDATE ALL VALUES):

```bash
# =====================================
# Django Settings
# =====================================
DJANGO_SECRET_KEY=YOUR_NEW_VERY_LONG_RANDOM_SECRET_KEY_GENERATE_NEW_ONE
DEBUG=False
ALLOWED_HOSTS=31.97.35.144,oinride.com,www.oinride.com

# =====================================
# PostgreSQL Database
# =====================================
POSTGRES_DB=oinride
POSTGRES_USER=pgadmin_z9f3
POSTGRES_PASSWORD=NEW_STRONG_PASSWORD_HERE_CHANGE_THIS
POSTGRES_PASSWORD_FLAT=NEW_STRONG_PASSWORD_HERE_CHANGE_THIS
POSTGRES_HOST=db
POSTGRES_PORT=5432

# Full connection string (URL-encode password)
PGVECTOR_CONNECTION=postgresql+psycopg2://pgadmin_z9f3:YOUR_URL_ENCODED_PASSWORD@db:5432/oinride

# =====================================
# Google AI (Gemini API)
# =====================================
GOOGLE_API_KEY=AIzaSyDWU0U4C7-9rlRfC8ODSjbvjHKKo55AeSc

# =====================================
# Google OAuth
# =====================================
GOOGLE_CLIENT_ID=891175220269-btcbo6gf0jouraq9m936s8gnqdmo9hbj.apps.googleusercontent.com

# Admin Panel Credentials
ADMIN_USERNAME=admin
ADMIN_EMAIL=admin@oinride.com
ADMIN_PASSWORD=NEW_STRONG_ADMIN_PASSWORD_CHANGE_THIS
```

**IMPORTANT**: Generate new secrets:
```bash
# Generate Django SECRET_KEY
python3 -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'

# Generate strong password
openssl rand -base64 32
```

### 3.3: Start Docker Containers

```bash
cd /opt/oinride/backend/docker-compose

# Build and start containers
docker-compose up -d --build

# Check containers are running
docker-compose ps

# Check logs
docker-compose logs -f web
```

### 3.4: Run Django Migrations

```bash
# Run migrations
docker-compose exec web python manage.py migrate

# Create superuser
docker-compose exec web python manage.py createsuperuser

# Collect static files
docker-compose exec web python manage.py collectstatic --noinput
```

---

## STEP 4: Deploy Frontend (Next.js)

### 4.1: Clone Frontend Repositories

```bash
cd /opt/oinride

# Clone frontend (user-facing app)
git clone https://github.com/YOUR_USERNAME/oinride_agent_ai.git frontend

# Clone admin panel
git clone https://github.com/YOUR_USERNAME/oinride-admin-panel.git admin-panel
```

### 4.2: Set Up Frontend Environment

```bash
cd /opt/oinride/frontend

# Create .env.local
nano .env.local
```

**Paste this**:
```bash
NEXT_PUBLIC_API_URL=http://31.97.35.144:8000
NEXT_PUBLIC_GOOGLE_CLIENT_ID=891175220269-btcbo6gf0jouraq9m936s8gnqdmo9hbj.apps.googleusercontent.com
```

```bash
# Install dependencies
npm install

# Build for production
npm run build

# Test it runs
npm start
# Press Ctrl+C to stop
```

### 4.3: Set Up Admin Panel

```bash
cd /opt/oinride/admin-panel

# Create .env.local
nano .env.local
```

**Paste this**:
```bash
NEXT_PUBLIC_API_URL=http://31.97.35.144:8000
```

```bash
# Install dependencies
npm install

# Build for production
npm run build
```

---

## STEP 5: Set Up Process Manager (PM2)

```bash
# Install PM2 globally
npm install -g pm2

# Start frontend
cd /opt/oinride/frontend
pm2 start npm --name "oinride-frontend" -- start

# Start admin panel
cd /opt/oinride/admin-panel
pm2 start npm --name "oinride-admin" -- start

# Save PM2 configuration
pm2 save

# Set PM2 to start on boot
pm2 startup
# Run the command it outputs

# Check status
pm2 list
pm2 logs
```

---

## STEP 6: Configure Nginx Reverse Proxy

```bash
# Create Nginx configuration
nano /etc/nginx/sites-available/oinride
```

**Paste this configuration**:

```nginx
# Redirect HTTP to HTTPS (after SSL setup)
server {
    listen 80;
    server_name 31.97.35.144 oinride.com www.oinride.com;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
    limit_req_zone $binary_remote_addr zone=general_limit:10m rate=100r/s;

    # Frontend (Next.js User App)
    location / {
        limit_req zone=general_limit burst=50 nodelay;
        proxy_pass http://localhost:3006;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }

    # Admin Panel
    location /admin-panel {
        limit_req zone=general_limit burst=30 nodelay;
        rewrite ^/admin-panel(.*)$ $1 break;
        proxy_pass http://localhost:3005;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }

    # Django Backend API
    location /chatlog {
        limit_req zone=api_limit burst=20 nodelay;
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        client_max_body_size 20M;
    }

    # Django Static Files
    location /static/ {
        alias /opt/oinride/backend/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Django Media Files
    location /media/ {
        alias /opt/oinride/backend/media/;
        expires 7d;
        add_header Cache-Control "public";
    }
}
```

```bash
# Enable the site
ln -s /etc/nginx/sites-available/oinride /etc/nginx/sites-enabled/

# Remove default site
rm /etc/nginx/sites-enabled/default

# Test Nginx configuration
nginx -t

# Restart Nginx
systemctl restart nginx
```

---

## STEP 7: Set Up SSL Certificate (HTTPS)

```bash
# Install Certbot
apt install -y certbot python3-certbot-nginx

# Get SSL certificate
certbot --nginx -d oinride.com -d www.oinride.com

# Follow prompts:
# - Enter email
# - Agree to terms
# - Choose to redirect HTTP to HTTPS

# Test auto-renewal
certbot renew --dry-run

# Certificate will auto-renew every 90 days
```

---

## STEP 8: Set Up Fail2Ban (Brute Force Protection)

```bash
# Create custom jail
nano /etc/fail2ban/jail.local
```

**Paste this**:
```ini
[sshd]
enabled = true
port = 22
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 3600
findtime = 600

[nginx-http-auth]
enabled = true
filter = nginx-http-auth
port = http,https
logpath = /var/log/nginx/error.log
maxretry = 5
bantime = 3600

[nginx-limit-req]
enabled = true
filter = nginx-limit-req
port = http,https
logpath = /var/log/nginx/error.log
maxretry = 10
bantime = 3600
```

```bash
# Restart fail2ban
systemctl restart fail2ban

# Check status
fail2ban-client status
```

---

## STEP 9: Set Up Automated Backups

```bash
# Create backup script
nano /root/backup.sh
```

**Paste this**:
```bash
#!/bin/bash
BACKUP_DIR="/root/backups"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Backup PostgreSQL database
docker exec docker-compose-db-1 pg_dump -U pgadmin_z9f3 oinride | gzip > $BACKUP_DIR/db_backup_$DATE.sql.gz

# Backup media files
tar -czf $BACKUP_DIR/media_backup_$DATE.tar.gz /opt/oinride/backend/media/

# Keep only last 7 days of backups
find $BACKUP_DIR -name "*.gz" -mtime +7 -delete

echo "Backup completed: $DATE"
```

```bash
# Make executable
chmod +x /root/backup.sh

# Add to crontab (daily at 2 AM)
crontab -e
```

Add this line:
```
0 2 * * * /root/backup.sh >> /var/log/backup.log 2>&1
```

---

## STEP 10: Monitoring and Maintenance

### Set Up Log Rotation

```bash
nano /etc/logrotate.d/oinride
```

**Paste this**:
```
/var/log/nginx/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 www-data adm
    sharedscripts
    postrotate
        systemctl reload nginx
    endscript
}
```

### Monitoring Commands

```bash
# Check all services
systemctl status nginx
systemctl status fail2ban
docker-compose ps
pm2 list

# Monitor resources
htop

# Check logs
docker-compose logs -f web
pm2 logs
tail -f /var/log/nginx/error.log

# Check disk space
df -h

# Check memory
free -h
```

---

## STEP 11: Security Hardening

### SSH Hardening

```bash
nano /etc/ssh/sshd_config
```

**Change these settings**:
```
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
MaxAuthTries 3
```

```bash
# Restart SSH
systemctl restart sshd
```

### Set Up Automatic Security Updates

```bash
apt install -y unattended-upgrades
dpkg-reconfigure -plow unattended-upgrades
```

---

## STEP 12: Verification Checklist

Run these tests to ensure everything works:

```bash
# 1. Test Django API
curl http://localhost:8000/chatlog/health/

# 2. Test frontend
curl http://localhost:3006

# 3. Test admin panel
curl http://localhost:3005

# 4. Test Nginx
curl http://31.97.35.144

# 5. Check Docker containers
docker-compose ps

# 6. Check PM2 processes
pm2 list

# 7. Check firewall
ufw status

# 8. Check fail2ban
fail2ban-client status

# 9. Test database connection
docker exec docker-compose-db-1 psql -U pgadmin_z9f3 -d oinride -c "SELECT 1;"

# 10. Check SSL certificate (after setup)
curl https://oinride.com
```

---

## Common Issues and Fixes

### Issue: Port already in use
```bash
# Find what's using the port
lsof -i :8000
# Kill the process
kill -9 <PID>
```

### Issue: Docker containers won't start
```bash
# Check logs
docker-compose logs web
# Restart containers
docker-compose restart
```

### Issue: Nginx 502 Bad Gateway
```bash
# Check if backends are running
pm2 list
docker-compose ps
# Restart Nginx
systemctl restart nginx
```

### Issue: Permission denied
```bash
# Fix ownership
chown -R oinrideadmin:oinrideadmin /opt/oinride
```

---

## Final Notes

1. **Change ALL passwords** after initial setup
2. **Set up monitoring** (UptimeRobot, New Relic, etc.)
3. **Configure DNS** to point to your VPS IP
4. **Test backups regularly** - restore from backup to verify
5. **Monitor logs daily** for suspicious activity
6. **Update packages weekly**: `apt update && apt upgrade -y`

---

## Need Help?

Check these logs if something goes wrong:
- Django: `docker-compose logs -f web`
- Frontend: `pm2 logs oinride-frontend`
- Admin: `pm2 logs oinride-admin`
- Nginx: `tail -f /var/log/nginx/error.log`
- System: `journalctl -xe`

**Your VPS is now clean and secure!** 🎉
