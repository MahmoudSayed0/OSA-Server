# 🚀 Deployment Guide - Django Backend + Next.js Frontend on VPS

## 📋 Table of Contents
1. [VPS Requirements](#vps-requirements)
2. [Initial VPS Setup](#initial-vps-setup)
3. [Deploy Backend (Django + PostgreSQL)](#deploy-backend)
4. [Deploy Frontend (Next.js)](#deploy-frontend)
5. [Configure Nginx](#configure-nginx)
6. [SSL Certificate Setup](#ssl-certificate)
7. [Environment Variables](#environment-variables)
8. [Post-Deployment](#post-deployment)

---

## 1. VPS Requirements

### Minimum Specs:
- **CPU:** 2 cores
- **RAM:** 4 GB (for Django + PostgreSQL + pgvector + Next.js)
- **Storage:** 20 GB SSD
- **OS:** Ubuntu 22.04 LTS (recommended)

### Software Needed:
- Docker & Docker Compose
- Nginx
- Git
- Node.js 18+ (for Next.js)
- Certbot (for SSL)

---

## 2. Initial VPS Setup

### Step 1: Connect to VPS
```bash
ssh root@your-vps-ip
```

### Step 2: Update System
```bash
apt update && apt upgrade -y
```

### Step 3: Install Docker & Docker Compose
```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Install Docker Compose
apt install docker-compose -y

# Start Docker
systemctl start docker
systemctl enable docker

# Verify installation
docker --version
docker-compose --version
```

### Step 4: Install Nginx
```bash
apt install nginx -y
systemctl start nginx
systemctl enable nginx
```

### Step 5: Install Node.js (for Next.js)
```bash
# Install Node.js 20.x
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs

# Verify
node --version
npm --version
```

### Step 6: Install Git
```bash
apt install git -y
```

### Step 7: Create Deployment User (Optional but Recommended)
```bash
adduser deploy
usermod -aG sudo deploy
usermod -aG docker deploy
su - deploy
```

---

## 3. Deploy Backend (Django + PostgreSQL)

### Step 1: Clone Repository
```bash
cd /home/deploy
git clone https://github.com/yourusername/Safety_Agent.git
cd Safety_Agent
```

### Step 2: Create Production Environment File
```bash
cd docker-compose
nano .postgres.production
```

Add the following:
```env
POSTGRES_DB=oinride_production
POSTGRES_USER=oinride_user
POSTGRES_PASSWORD=YOUR_STRONG_PASSWORD_HERE
POSTGRES_PASSWORD_FLAT=YOUR_STRONG_PASSWORD_HERE
POSTGRES_HOST=db
POSTGRES_PORT=5432
```

**Important:** Change `YOUR_STRONG_PASSWORD_HERE` to a strong password!

### Step 3: Update Django Settings for Production

Edit `Safety_agent_Django/settings.py`:
```python
# Add your domain to ALLOWED_HOSTS
ALLOWED_HOSTS = [
    'your-domain.com',
    'www.your-domain.com',
    'your-vps-ip',
    'localhost'
]

# Update DEBUG
DEBUG = False  # IMPORTANT: Set to False in production

# Add CSRF trusted origins
CSRF_TRUSTED_ORIGINS = [
    'https://your-domain.com',
    'https://www.your-domain.com'
]

# Update CORS settings (if using CORS)
CORS_ALLOWED_ORIGINS = [
    'https://your-frontend-domain.com',
    'https://www.your-frontend-domain.com'
]
```

### Step 4: Update Docker Compose for Production

Create `docker-compose.production.yml`:
```yaml
version: '3'

volumes:
  postgres_data: {}
  postgres_data_backups: {}
  pgadmin_data: {}
  media_files: {}

services:
  db:
    build:
      context: ../.
      dockerfile: ./docker-compose/Dockerfile
    image: local_db
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - postgres_data_backups:/backups
    env_file:
      - ./.postgres.production
    restart: always
    networks:
      - backend

  web:
    build:
      context: ../
      dockerfile: ./docker-compose/Dockerfile.django
    command: >
      sh -c "python manage.py migrate &&
             python manage.py collectstatic --noinput &&
             gunicorn Safety_agent_Django.wsgi:application --bind 0.0.0.0:8000 --workers 4 --timeout 120"
    volumes:
      - ../:/app
      - media_files:/app/media
    ports:
      - "127.0.0.1:8000:8000"
    env_file:
      - ./.postgres.production
    depends_on:
      - db
    restart: always
    networks:
      - backend

  pgadmin:
    image: dpage/pgadmin4:latest
    environment:
      PGADMIN_DEFAULT_EMAIL: admin@admin.com
      PGADMIN_DEFAULT_PASSWORD: CHANGE_THIS_PASSWORD
      PGADMIN_CONFIG_SERVER_MODE: 'True'
    volumes:
      - pgadmin_data:/var/lib/pgadmin
    ports:
      - "127.0.0.1:5050:80"
    depends_on:
      - db
    restart: always
    networks:
      - backend

networks:
  backend:
    driver: bridge
```

### Step 5: Install Gunicorn (Production Server)

Add to `requirements.txt`:
```txt
gunicorn==21.2.0
```

### Step 6: Build and Start Services
```bash
cd docker-compose

# Build images
docker-compose -f docker-compose.production.yml build

# Start services
docker-compose -f docker-compose.production.yml up -d

# Check status
docker-compose -f docker-compose.production.yml ps

# View logs
docker-compose -f docker-compose.production.yml logs -f web
```

### Step 7: Create Django Superuser
```bash
docker-compose -f docker-compose.production.yml exec web python manage.py createsuperuser
```

---

## 4. Deploy Frontend (Next.js)

### Step 1: Clone Frontend Repository
```bash
cd /home/deploy
git clone https://github.com/yourusername/oinride-agent-ai.git
cd oinride-agent-ai
```

### Step 2: Create Environment File
```bash
nano .env.local
```

Add:
```env
# API Configuration (server-side proxy to Django backend)
API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_API_TARGET=http://localhost:8000

# Next.js Configuration
NEXT_PUBLIC_APP_URL=https://your-domain.com
```

### Step 3: Create PM2 Ecosystem Config File
This ensures PM2 remembers your app configuration after reboots:
```bash
nano ecosystem.config.cjs
```
**Note:** Use `.cjs` extension because the project uses ES modules (`"type": "module"` in package.json).

Add:
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
        NEXT_PUBLIC_APP_URL: 'https://your-domain.com'
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

### Step 4: Install Dependencies
```bash
# Create logs directory
mkdir -p ~/logs

# Install dependencies (use --legacy-peer-deps for React 19 compatibility)
npm install --legacy-peer-deps
```

### Step 5: Build Next.js App
```bash
npm run build
```

### Step 6: Install PM2 (Process Manager)
```bash
npm install -g pm2
```

### Step 7: Start Next.js with PM2
```bash
# Start using ecosystem config file
pm2 start ecosystem.config.cjs

# Save PM2 configuration (CRITICAL - makes it persist after reboot)
pm2 save

# Setup PM2 to start on boot
pm2 startup
# IMPORTANT: Copy and run the command it outputs!
# Example: sudo env PATH=$PATH:/usr/bin pm2 startup systemd -u deploy --hp /home/deploy

# Save again after startup setup
pm2 save

# Verify
pm2 status
pm2 logs oinride-frontend
```

---

## 5. Configure Nginx

### Step 1: Create Backend Configuration
```bash
sudo nano /etc/nginx/sites-available/backend
```

Add:
```nginx
# Backend API Configuration
server {
    listen 80;
    server_name api.your-domain.com;

    client_max_body_size 10M;

    # Django Backend
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }

    # Media files
    location /media/ {
        alias /home/deploy/Safety_Agent/media/;
    }

    # pgAdmin (optional - for database management)
    location /pgadmin/ {
        proxy_pass http://127.0.0.1:5050/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Step 2: Create Frontend Configuration
```bash
sudo nano /etc/nginx/sites-available/frontend
```

Add:
```nginx
# Frontend Configuration
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Step 3: Enable Sites
```bash
# Enable configurations
sudo ln -s /etc/nginx/sites-available/backend /etc/nginx/sites-enabled/
sudo ln -s /etc/nginx/sites-available/frontend /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Restart Nginx
sudo systemctl restart nginx
```

---

## 6. SSL Certificate Setup

### Step 1: Install Certbot
```bash
sudo apt install certbot python3-certbot-nginx -y
```

### Step 2: Get SSL Certificates
```bash
# For backend
sudo certbot --nginx -d api.your-domain.com

# For frontend
sudo certbot --nginx -d your-domain.com -d www.your-domain.com
```

### Step 3: Auto-Renewal Setup
```bash
# Test renewal
sudo certbot renew --dry-run

# Certbot automatically sets up auto-renewal via cron
```

---

## 7. Environment Variables

### Backend Environment Variables
Create `/home/deploy/Safety_Agent/.env.production`:
```env
DEBUG=False
SECRET_KEY=your-super-secret-key-change-this
ALLOWED_HOSTS=api.your-domain.com,your-vps-ip

# Database
POSTGRES_DB=oinride_production
POSTGRES_USER=oinride_user
POSTGRES_PASSWORD=YOUR_STRONG_PASSWORD
POSTGRES_HOST=db
POSTGRES_PORT=5432

# Google Gemini API
GOOGLE_API_KEY=your-google-api-key

# CORS
CORS_ALLOWED_ORIGINS=https://your-domain.com,https://www.your-domain.com
```

### Frontend Environment Variables
Create `/home/deploy/frontend/.env.production`:
```env
NEXT_PUBLIC_API_URL=https://api.your-domain.com
NEXT_PUBLIC_WS_URL=wss://api.your-domain.com
```

---

## 8. Post-Deployment

### Step 1: Set Up Firewall
```bash
# Allow SSH, HTTP, HTTPS
sudo ufw allow 22
sudo ufw allow 80
sudo ufw allow 443

# Enable firewall
sudo ufw enable
```

### Step 2: Setup Backup Script
```bash
nano /home/deploy/backup.sh
```

Add:
```bash
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/home/deploy/backups"

# Create backup directory
mkdir -p $BACKUP_DIR

# Backup PostgreSQL database
docker exec docker-compose-db-1 pg_dump -U oinride_user oinride_production > $BACKUP_DIR/db_backup_$DATE.sql

# Backup media files
tar -czf $BACKUP_DIR/media_backup_$DATE.tar.gz /home/deploy/Safety_Agent/media/

# Keep only last 7 days of backups
find $BACKUP_DIR -name "*.sql" -mtime +7 -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +7 -delete

echo "Backup completed: $DATE"
```

Make executable:
```bash
chmod +x /home/deploy/backup.sh
```

Add to crontab:
```bash
crontab -e
```

Add:
```
0 2 * * * /home/deploy/backup.sh >> /home/deploy/backup.log 2>&1
```

### Step 3: Monitoring & Logs

View backend logs:
```bash
cd /home/deploy/Safety_Agent/docker-compose
docker-compose -f docker-compose.production.yml logs -f web
```

View frontend logs:
```bash
pm2 logs frontend
```

View Nginx logs:
```bash
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### Step 4: Health Check Endpoints

Add to Django `urls.py`:
```python
from django.http import JsonResponse

def health_check(request):
    return JsonResponse({"status": "healthy"})

urlpatterns = [
    path('health/', health_check),
    # ... other paths
]
```

---

## 🔧 Useful Commands

### Backend Management
```bash
# Restart backend
cd /home/deploy/Safety_Agent/docker-compose
docker-compose -f docker-compose.production.yml restart web

# Run migrations
docker-compose -f docker-compose.production.yml exec web python manage.py migrate

# Collect static files
docker-compose -f docker-compose.production.yml exec web python manage.py collectstatic --noinput

# Create superuser
docker-compose -f docker-compose.production.yml exec web python manage.py createsuperuser

# View logs
docker-compose -f docker-compose.production.yml logs -f
```

### Frontend Management
```bash
# Restart frontend
pm2 restart oinride-frontend

# View status
pm2 status

# View logs
pm2 logs oinride-frontend

# Monitor resources
pm2 monit

# Rebuild and restart
cd /home/deploy/oinride-agent-ai
git pull
npm install --legacy-peer-deps
npm run build
pm2 restart oinride-frontend

# If PM2 forgets the app after reboot:
cd /home/deploy/oinride-agent-ai
pm2 start ecosystem.config.cjs
pm2 save
```

### Nginx Management
```bash
# Test configuration
sudo nginx -t

# Restart
sudo systemctl restart nginx

# Reload (no downtime)
sudo systemctl reload nginx

# Check status
sudo systemctl status nginx
```

---

## 🎯 Final Architecture

```
Internet
   │
   ├─→ your-domain.com (Frontend) → Nginx:80/443 → Next.js:3000
   │
   └─→ api.your-domain.com (Backend) → Nginx:80/443 → Django:8000
                                                          │
                                                          └─→ PostgreSQL+pgvector
                                                          └─→ pgAdmin:5050
```

---

## 📊 Deployment Checklist

- [ ] VPS setup complete
- [ ] Docker & Docker Compose installed
- [ ] Backend deployed and running
- [ ] Frontend deployed and running
- [ ] Nginx configured
- [ ] SSL certificates installed
- [ ] Environment variables set
- [ ] Database migrated
- [ ] Media files accessible
- [ ] Firewall configured
- [ ] Backup script configured
- [ ] Health checks working
- [ ] Domain DNS configured
- [ ] Test all API endpoints
- [ ] Test file uploads
- [ ] Test PDF preview
- [ ] Test chat sessions

---

## 🆘 Troubleshooting

**Backend not accessible:**
```bash
# Check Docker containers
docker ps

# Check logs
docker-compose -f docker-compose.production.yml logs web

# Check Nginx
sudo nginx -t
sudo systemctl status nginx
```

**Frontend not accessible:**
```bash
# Check PM2
pm2 status
pm2 logs oinride-frontend

# Rebuild
npm run build
pm2 restart oinride-frontend
```

**PM2 forgets app after reboot:**
```bash
# This happens when pm2 save wasn't run properly

# Step 1: Recreate the app
cd /home/deploy/oinride-agent-ai
pm2 start ecosystem.config.cjs

# Step 2: Save the configuration
pm2 save

# Step 3: Setup startup hook
pm2 startup
# Run the command it outputs (with sudo)

# Step 4: Save again
pm2 save

# Verify
pm2 list
```

**Database connection issues:**
```bash
# Check database container
docker ps | grep db

# Check database logs
docker-compose -f docker-compose.production.yml logs db

# Connect to database
docker exec -it docker-compose-db-1 psql -U oinride_user -d oinride_production
```

**SSL certificate issues:**
```bash
# Renew certificate
sudo certbot renew

# Check certificate status
sudo certbot certificates
```

---

## 🔐 Security Best Practices

1. **Change all default passwords**
2. **Use environment variables for secrets**
3. **Enable firewall (ufw)**
4. **Keep system updated**: `apt update && apt upgrade`
5. **Setup fail2ban**: `apt install fail2ban`
6. **Regular backups**
7. **Monitor logs regularly**
8. **Use strong passwords**
9. **Disable root SSH login** (use deploy user)
10. **Keep Docker images updated**

---

Good luck with your deployment! 🚀
