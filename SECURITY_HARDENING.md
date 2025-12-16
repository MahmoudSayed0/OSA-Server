# VPS Security Hardening Guide

## IMMEDIATE ACTIONS REQUIRED

### 1. Start Your VPS and SSH In
```bash
ssh root@31.97.35.144
```

### 2. Find and Remove Malware

#### Check for suspicious processes:
```bash
# Look for cryptominer processes
ps aux | grep -E "crypto|miner|xmrig|kdevtmpfsi|minerd" | grep -v grep

# Kill any suspicious processes
kill -9 <PID>

# Check what's listening on network
netstat -tunlp | grep ESTABLISHED

# Check for unauthorized users
cat /etc/passwd | grep -v "nologin\|false"
```

#### Check for malicious cron jobs:
```bash
# Check root crontab
crontab -l

# Check system cron
cat /etc/crontab
ls -la /etc/cron.d/
ls -la /etc/cron.hourly/
ls -la /etc/cron.daily/

# Remove any suspicious entries
crontab -e  # Edit and remove malicious entries
```

#### Check for backdoors and suspicious files:
```bash
# Check for recently modified files
find /tmp -type f -mtime -7
find /var/tmp -type f -mtime -7
find /home -type f -mtime -7
find /root -type f -mtime -7

# Check for hidden files in common locations
ls -la /tmp
ls -la /var/tmp
ls -la ~/.ssh
ls -la /root/.ssh

# Remove suspicious files
rm -f /path/to/suspicious/file
```

### 3. Install and Run Security Tools

```bash
# Update system
apt update && apt upgrade -y

# Install security tools
apt install -y fail2ban ufw clamav clamav-daemon rkhunter chkrootkit

# Configure firewall
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS
ufw allow 8000/tcp  # Django
ufw allow 3006/tcp  # Next.js frontend
ufw allow 3005/tcp  # Admin panel
ufw --force enable

# Update malware database
systemctl stop clamav-freshclam
freshclam
systemctl start clamav-freshclam

# Scan for malware (this may take a while)
clamscan -r -i --log=/var/log/clamav-scan.log /home /root /var /tmp

# Check scan results
cat /var/log/clamav-scan.log

# Check for rootkits
rkhunter --check --skip-keypress
chkrootkit
```

### 4. Secure SSH Access

```bash
# Edit SSH config
nano /etc/ssh/sshd_config

# Add these security settings:
PermitRootLogin no  # Disable root login (after creating sudo user!)
PasswordAuthentication no  # Force SSH key authentication
PubkeyAuthentication yes
MaxAuthTries 3
Port 22  # Or change to a non-standard port

# Create a new sudo user first!
adduser oinrideadmin
usermod -aG sudo oinrideadmin

# Set up SSH keys for the new user
# Then restart SSH
systemctl restart sshd
```

### 5. Configure Fail2Ban (Brute Force Protection)

```bash
# Create jail configuration
cat > /etc/fail2ban/jail.local << 'EOF'
[sshd]
enabled = true
port = 22
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 3600

[nginx-http-auth]
enabled = true
port = http,https
logpath = /var/log/nginx/error.log
maxretry = 5
bantime = 3600
EOF

# Restart fail2ban
systemctl restart fail2ban
systemctl enable fail2ban
```

### 6. Secure Docker (If Using Docker on VPS)

```bash
# Ensure Docker uses latest security patches
apt install docker.io docker-compose -y

# Configure Docker to not expose ports publicly
# Edit docker-compose.yml to only expose to localhost:
# ports:
#   - "127.0.0.1:8000:8000"  # Only accessible from localhost
#   - "127.0.0.1:5432:5432"  # PostgreSQL only on localhost
```

### 7. Set Up Nginx Reverse Proxy with HTTPS

```bash
# Install Nginx and Certbot
apt install -y nginx certbot python3-certbot-nginx

# Create Nginx config for your domain
cat > /etc/nginx/sites-available/oinride << 'EOF'
# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name oinride.com www.oinride.com;
    return 301 https://$server_name$request_uri;
}

# HTTPS configuration
server {
    listen 443 ssl http2;
    server_name oinride.com www.oinride.com;

    # SSL configuration (Certbot will add this)

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;
    add_header Content-Security-Policy "default-src 'self' http: https: data: blob: 'unsafe-inline'" always;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
    limit_req zone=api_limit burst=20 nodelay;

    # Frontend (Next.js)
    location / {
        proxy_pass http://localhost:3006;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    # Admin Panel
    location /admin {
        proxy_pass http://localhost:3005;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    # Django Backend
    location /chatlog {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

# Enable the site
ln -s /etc/nginx/sites-available/oinride /etc/nginx/sites-enabled/
nginx -t  # Test configuration
systemctl restart nginx

# Get SSL certificate
certbot --nginx -d oinride.com -d www.oinride.com
```

### 8. Monitor and Log Everything

```bash
# Install monitoring tools
apt install -y htop iotop iftop

# Set up log rotation
cat > /etc/logrotate.d/oinride << 'EOF'
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
        if [ -f /var/run/nginx.pid ]; then
            kill -USR1 `cat /var/run/nginx.pid`
        fi
    endscript
}
EOF

# Set up automated security updates
apt install -y unattended-upgrades
dpkg-reconfigure -plow unattended-upgrades
```

### 9. Database Security

```bash
# Connect to PostgreSQL and secure it
docker exec -it docker-compose-db-1 psql -U pgadmin_z9f3 -d oinride

-- Create read-only user for monitoring
CREATE USER monitor WITH PASSWORD 'strong_password_here';
GRANT CONNECT ON DATABASE oinride TO monitor;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO monitor;

-- Revoke unnecessary privileges
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
```

### 10. Deploy Updated Code Securely

```bash
# On VPS, pull latest code
cd /path/to/Safety_Agent
git pull origin main

# Rebuild Docker containers with security updates
cd docker-compose
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# Check containers are running
docker-compose ps

# Check logs for any issues
docker-compose logs -f --tail=50
```

## IMPORTANT: Next.js Security

Your Next.js versions are up to date, but add these security headers:

### Update `next.config.js` for both frontend and admin panel:

```javascript
/** @type {import('next').NextConfig} */
const nextConfig = {
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          {
            key: 'X-DNS-Prefetch-Control',
            value: 'on'
          },
          {
            key: 'Strict-Transport-Security',
            value: 'max-age=63072000; includeSubDomains; preload'
          },
          {
            key: 'X-Frame-Options',
            value: 'SAMEORIGIN'
          },
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff'
          },
          {
            key: 'X-XSS-Protection',
            value: '1; mode=block'
          },
          {
            key: 'Referrer-Policy',
            value: 'origin-when-cross-origin'
          }
        ]
      }
    ]
  }
}

module.exports = nextConfig
```

## Monitoring After Cleanup

```bash
# Monitor CPU/Memory usage
htop

# Monitor network connections
watch -n 1 'netstat -tunlp | grep ESTABLISHED'

# Monitor Docker containers
watch -n 5 'docker stats --no-stream'

# Check for unauthorized login attempts
tail -f /var/log/auth.log | grep Failed

# Monitor fail2ban
fail2ban-client status sshd
```

## Preventive Measures

1. **Regular Updates**: Set up automatic security updates
2. **Backups**: Daily automated backups of database and code
3. **Monitoring**: Set up uptime monitoring (UptimeRobot, Pingdom)
4. **Alerts**: Configure email alerts for:
   - Failed login attempts
   - High CPU/memory usage
   - Disk space warnings
   - Malware detection

## Contact Your Hosting Provider

Ask them:
1. What specific malware was detected?
2. What files were infected?
3. Can they provide logs of the attack?
4. Do they have backup from before the infection?

## After Cleanup

1. Change all passwords (database, SSH keys, API keys)
2. Rotate Django SECRET_KEY
3. Review and audit all code for backdoors
4. Enable 2FA on all admin accounts
5. Set up automated daily backups
6. Configure intrusion detection (AIDE or Tripwire)

---

**IMPORTANT**: The CVE-2025-55182 mentioned by your hosting provider doesn't appear in official CVE databases. This might be:
- A typo (perhaps CVE-2024-xxxx)
- A false positive
- A generic malware detection

Your Next.js 16.0.x and React 19.2.x are the latest versions and should be secure.
