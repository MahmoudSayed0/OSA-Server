# 🚀 Quick Reference - VPS Deployment

## 📋 Pre-Deployment Checklist

- [ ] VPS with Ubuntu 22.04
- [ ] Domain name configured (e.g., `api.yourdomain.com`)
- [ ] DNS A record pointing to VPS IP
- [ ] SSH access to VPS
- [ ] Google API key for Gemini

---

## 🎯 One-Command Deployment

```bash
# On your VPS
wget https://raw.githubusercontent.com/yourusername/Safety_Agent/main/deploy.sh
chmod +x deploy.sh
./deploy.sh
```

---

## 📦 Manual Deployment Steps

### 1. Initial Setup (One-time)

```bash
# Connect to VPS
ssh root@your-vps-ip

# Update system
apt update && apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh && sh get-docker.sh

# Install Docker Compose
apt install docker-compose nginx git -y

# Create deploy user
adduser deploy
usermod -aG sudo,docker deploy
su - deploy
```

### 2. Deploy Backend

```bash
# Clone repository
cd ~
git clone https://github.com/yourusername/Safety_Agent.git
cd Safety_Agent

# Create environment file
cd docker-compose
nano .postgres.production
# Add: POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, GOOGLE_API_KEY

# Build and start
docker-compose -f docker-compose.production.yml build
docker-compose -f docker-compose.production.yml up -d

# Run migrations
docker-compose -f docker-compose.production.yml exec web python manage.py migrate

# Create superuser
docker-compose -f docker-compose.production.yml exec web python manage.py createsuperuser
```

### 3. Configure Nginx

```bash
# Create config
sudo nano /etc/nginx/sites-available/backend
```

Paste this:
```nginx
server {
    listen 80;
    server_name api.your-domain.com;
    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /media/ {
        alias /home/deploy/Safety_Agent/media/;
    }
}
```

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/backend /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 4. Setup SSL

```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx -y

# Get certificate
sudo certbot --nginx -d api.your-domain.com

# Auto-renewal is automatic
```

---

## 🔧 Common Commands

### Backend Management

```bash
cd ~/Safety_Agent/docker-compose

# View status
docker-compose -f docker-compose.production.yml ps

# View logs
docker-compose -f docker-compose.production.yml logs -f web

# Restart
docker-compose -f docker-compose.production.yml restart web

# Stop all
docker-compose -f docker-compose.production.yml down

# Start all
docker-compose -f docker-compose.production.yml up -d

# Update code
git pull
docker-compose -f docker-compose.production.yml restart web
```

### Database Commands

```bash
# Access database
docker-compose -f docker-compose.production.yml exec db psql -U oinride_user -d oinride_production

# Backup database
docker exec safety_agent_db pg_dump -U oinride_user oinride_production > backup_$(date +%Y%m%d).sql

# Restore database
cat backup.sql | docker exec -i safety_agent_db psql -U oinride_user -d oinride_production

# Run migrations
docker-compose -f docker-compose.production.yml exec web python manage.py migrate

# Create superuser
docker-compose -f docker-compose.production.yml exec web python manage.py createsuperuser
```

### Nginx Commands

```bash
# Test configuration
sudo nginx -t

# Restart Nginx
sudo systemctl restart nginx

# Reload Nginx (no downtime)
sudo systemctl reload nginx

# View logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### SSL Certificate

```bash
# Renew certificates
sudo certbot renew

# Test renewal
sudo certbot renew --dry-run

# View certificates
sudo certbot certificates
```

---

## 🔍 Debugging

### Check if services are running

```bash
# Docker containers
docker ps

# Nginx
sudo systemctl status nginx

# Check ports
sudo netstat -tlnp | grep -E '8000|80|443'
```

### View logs

```bash
# Backend logs
docker-compose -f docker-compose.production.yml logs -f web

# Database logs
docker-compose -f docker-compose.production.yml logs -f db

# Nginx error logs
sudo tail -f /var/log/nginx/error.log
```

### Test API

```bash
# Health check
curl http://localhost:8000/health/

# Test endpoint
curl http://localhost:8000/chatlog/get-all-users/

# With SSL
curl https://api.your-domain.com/health/
```

---

## 📊 Architecture Overview

```
Internet
    │
    ├─→ your-domain.com → Nginx:443 → Next.js:3000 (Frontend)
    │
    └─→ api.your-domain.com → Nginx:443 → Django:8000 (Backend)
                                              │
                                              ├─→ PostgreSQL+pgvector
                                              ├─→ Media Files
                                              └─→ pgAdmin:5050
```

---

## 🔐 Security Checklist

- [ ] Changed all default passwords
- [ ] `DEBUG=False` in Django settings
- [ ] SSL certificates installed
- [ ] Firewall enabled (`ufw`)
- [ ] Regular backups configured
- [ ] `ALLOWED_HOSTS` properly set
- [ ] Secret keys in environment variables
- [ ] Database password is strong
- [ ] pgAdmin password changed
- [ ] SSH key authentication enabled

---

## 📱 Monitoring

### Check disk space
```bash
df -h
```

### Check memory usage
```bash
free -h
```

### Check CPU usage
```bash
top
# or
htop
```

### Check Docker resource usage
```bash
docker stats
```

---

## 🔄 Update Deployment

```bash
cd ~/Safety_Agent

# Pull latest code
git pull

# Rebuild containers
cd docker-compose
docker-compose -f docker-compose.production.yml build web

# Run migrations
docker-compose -f docker-compose.production.yml exec web python manage.py migrate

# Restart services
docker-compose -f docker-compose.production.yml restart web

# Check logs
docker-compose -f docker-compose.production.yml logs -f web
```

---

## 📞 Support

**View this guide online:**
https://github.com/yourusername/Safety_Agent/blob/main/DEPLOYMENT_GUIDE.md

**Common Issues:**
- Backend not accessible → Check Nginx logs and Docker logs
- Database connection error → Check `.postgres.production` file
- SSL issues → Run `sudo certbot renew`
- 502 Bad Gateway → Backend is down, check `docker ps`
- File upload issues → Check `client_max_body_size` in Nginx

---

## 🎯 Endpoints to Test

After deployment, test these:

✅ `https://api.your-domain.com/health/` - Health check
✅ `https://api.your-domain.com/admin/` - Django admin
✅ `https://api.your-domain.com/chatlog/get-all-users/` - API test
✅ `https://your-domain.com` - Frontend
✅ `https://api.your-domain.com/pgadmin/` - Database admin

---

Good luck! 🚀
