# Security Hardening Checklist for Oinride VPS

This checklist helps prevent future malware infections and security breaches like the system3d cryptominer incident.

## 🚨 Critical Priority (Do These NOW)

### 1. Change All Passwords and Keys

- [ ] **Generate new SSH keys** (if compromised during malware incident)
  ```bash
  ssh-keygen -t ed25519 -C "oinride-production-$(date +%Y%m%d)"
  ```

- [ ] **Generate new Django SECRET_KEY**
  ```bash
  python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
  ```

- [ ] **Generate new PostgreSQL password**
  ```bash
  openssl rand -base64 32
  ```

- [ ] **Revoke old GitHub Personal Access Tokens** and create new ones
  - Go to: https://github.com/settings/tokens
  - Delete any old tokens
  - Create new token with ONLY `read:packages` scope

- [ ] **Update all GitHub Secrets** with new values

### 2. Verify VPS is Clean

- [ ] **Check for suspicious processes**
  ```bash
  ps aux | grep -E "system3d|kdevtmpfsi|kinsing|xmrig"
  top -bn1 | head -20
  ```

- [ ] **Check for suspicious cron jobs**
  ```bash
  sudo crontab -l -u root
  sudo crontab -l -u oinrideadmin
  cat /etc/cron.d/*
  cat /etc/cron.daily/*
  ```

- [ ] **Check for suspicious network connections**
  ```bash
  sudo netstat -tulpn | grep ESTABLISHED
  sudo ss -tunap | grep ESTAB
  ```

- [ ] **Check system startup scripts**
  ```bash
  sudo systemctl list-units --type=service --state=running
  ls -la /etc/systemd/system/
  ls -la ~/.config/systemd/user/
  ```

- [ ] **Scan for rootkits**
  ```bash
  sudo apt install -y rkhunter chkrootkit
  sudo rkhunter --check --skip-keypress
  sudo chkrootkit
  ```

### 3. Firewall Configuration

- [ ] **Verify UFW is enabled and configured correctly**
  ```bash
  sudo ufw status verbose
  ```

  Expected output:
  ```
  Status: active
  To                         Action      From
  --                         ------      ----
  22/tcp                     ALLOW       Anywhere
  80/tcp                     ALLOW       Anywhere
  443/tcp                    ALLOW       Anywhere
  ```

- [ ] **Block all other ports**
  ```bash
  sudo ufw default deny incoming
  sudo ufw default allow outgoing
  sudo ufw reload
  ```

- [ ] **Rate limit SSH to prevent brute force**
  ```bash
  sudo ufw limit 22/tcp comment 'SSH rate limit'
  ```

### 4. SSH Hardening

- [ ] **Disable password authentication** (key-only)
  ```bash
  sudo nano /etc/ssh/sshd_config
  ```

  Set these values:
  ```
  PasswordAuthentication no
  PubkeyAuthentication yes
  PermitRootLogin no
  ChallengeResponseAuthentication no
  UsePAM no
  ```

- [ ] **Restart SSH service**
  ```bash
  sudo systemctl restart sshd
  ```

- [ ] **Test SSH connection** before closing current session
  ```bash
  # In a NEW terminal window:
  ssh oinrideadmin@31.97.35.144
  ```

### 5. Install Fail2Ban (Automatic IP Blocking)

- [ ] **Install and configure Fail2Ban**
  ```bash
  sudo apt update
  sudo apt install -y fail2ban
  ```

- [ ] **Create Fail2Ban configuration**
  ```bash
  sudo tee /etc/fail2ban/jail.local > /dev/null <<'EOF'
  [DEFAULT]
  bantime = 1h
  findtime = 10m
  maxretry = 5

  [sshd]
  enabled = true
  port = 22
  logpath = /var/log/auth.log

  [nginx-http-auth]
  enabled = true
  port = 80,443
  logpath = /var/log/nginx/error.log

  [nginx-limit-req]
  enabled = true
  port = 80,443
  logpath = /var/log/nginx/error.log
  maxretry = 10
  EOF
  ```

- [ ] **Start Fail2Ban**
  ```bash
  sudo systemctl enable fail2ban
  sudo systemctl start fail2ban
  sudo fail2ban-client status
  ```

---

## 🔒 High Priority (Do These Within 24 Hours)

### 6. Enable Automatic Security Updates

- [ ] **Install unattended-upgrades**
  ```bash
  sudo apt install -y unattended-upgrades
  sudo dpkg-reconfigure -plow unattended-upgrades
  ```

- [ ] **Configure automatic updates**
  ```bash
  sudo tee /etc/apt/apt.conf.d/50unattended-upgrades > /dev/null <<'EOF'
  Unattended-Upgrade::Allowed-Origins {
      "${distro_id}:${distro_codename}-security";
      "${distro_id}ESMApps:${distro_codename}-apps-security";
  };
  Unattended-Upgrade::AutoFixInterruptedDpkg "true";
  Unattended-Upgrade::Automatic-Reboot "false";
  Unattended-Upgrade::Mail "your-email@example.com";
  EOF
  ```

### 7. Docker Security

- [ ] **Run Docker containers as non-root** (already implemented in Dockerfiles ✓)

- [ ] **Scan Docker images for vulnerabilities**
  ```bash
  # Install Docker Scout
  docker scout quickview ghcr.io/mahmoudsayed0/osa-backend:latest
  docker scout cves ghcr.io/mahmoudsayed0/osa-frontend:latest
  docker scout cves ghcr.io/mahmoudsayed0/osa-admin:latest
  ```

- [ ] **Limit Docker container resources**
  Add to each service in docker-compose.yml:
  ```yaml
  deploy:
    resources:
      limits:
        cpus: '2.0'
        memory: 2G
      reservations:
        memory: 512M
  ```

- [ ] **Enable Docker content trust**
  ```bash
  export DOCKER_CONTENT_TRUST=1
  ```

### 8. File Integrity Monitoring

- [ ] **Install AIDE (Advanced Intrusion Detection Environment)**
  ```bash
  sudo apt install -y aide
  sudo aideinit
  sudo mv /var/lib/aide/aide.db.new /var/lib/aide/aide.db
  ```

- [ ] **Create AIDE check cron job**
  ```bash
  sudo tee /etc/cron.daily/aide > /dev/null <<'EOF'
  #!/bin/bash
  /usr/bin/aide --check | mail -s "AIDE Report for $(hostname)" your-email@example.com
  EOF
  sudo chmod +x /etc/cron.daily/aide
  ```

### 9. Log Monitoring

- [ ] **Install logwatch**
  ```bash
  sudo apt install -y logwatch
  ```

- [ ] **Configure daily log reports**
  ```bash
  sudo tee /etc/cron.daily/00logwatch > /dev/null <<'EOF'
  #!/bin/bash
  /usr/sbin/logwatch --output mail --mailto your-email@example.com --detail high
  EOF
  sudo chmod +x /etc/cron.daily/00logwatch
  ```

- [ ] **Monitor Docker logs**
  ```bash
  # Check for suspicious activity
  docker-compose -f /opt/oinride/backend/docker-compose.yml logs --tail=100 | grep -E "error|warning|fail"
  ```

### 10. Database Security

- [ ] **Use strong PostgreSQL password** (already configured ✓)

- [ ] **Restrict database to localhost only** (already configured ✓)

- [ ] **Enable PostgreSQL logging**
  ```bash
  docker-compose -f /opt/oinride/backend/docker-compose.yml exec db psql -U pgadmin_z9f3 -c "ALTER SYSTEM SET log_connections = on;"
  docker-compose -f /opt/oinride/backend/docker-compose.yml exec db psql -U pgadmin_z9f3 -c "ALTER SYSTEM SET log_disconnections = on;"
  docker-compose -f /opt/oinride/backend/docker-compose.yml restart db
  ```

---

## 🛡️ Medium Priority (Do These Within 1 Week)

### 11. SSL/TLS Certificate Setup

- [ ] **Point domain to VPS** (update DNS records)

- [ ] **Install Certbot**
  ```bash
  sudo apt install -y certbot python3-certbot-nginx
  ```

- [ ] **Generate SSL certificate**
  ```bash
  sudo certbot --nginx -d oinride.com -d www.oinride.com
  ```

- [ ] **Enable auto-renewal**
  ```bash
  sudo systemctl enable certbot.timer
  sudo certbot renew --dry-run
  ```

- [ ] **Update environment variables to use HTTPS**
  - Update GitHub Secrets
  - Update backend .env file

### 12. Backup Strategy

- [ ] **Create automated database backups**
  ```bash
  sudo tee /usr/local/bin/backup-database.sh > /dev/null <<'EOF'
  #!/bin/bash
  BACKUP_DIR="/opt/oinride/backups"
  DATE=$(date +%Y%m%d_%H%M%S)
  mkdir -p $BACKUP_DIR

  docker-compose -f /opt/oinride/backend/docker-compose.yml exec -T db \
    pg_dump -U pgadmin_z9f3 oinride | gzip > $BACKUP_DIR/oinride_$DATE.sql.gz

  # Keep only last 30 days of backups
  find $BACKUP_DIR -name "oinride_*.sql.gz" -mtime +30 -delete
  EOF
  sudo chmod +x /usr/local/bin/backup-database.sh
  ```

- [ ] **Schedule daily backups**
  ```bash
  sudo tee -a /etc/crontab > /dev/null <<'EOF'
  0 2 * * * root /usr/local/bin/backup-database.sh
  EOF
  ```

- [ ] **Store backups off-site** (e.g., AWS S3, Google Cloud Storage)

### 13. Nginx Security Headers

- [ ] **Add additional security headers** (already partially configured ✓)

- [ ] **Enable CSP (Content Security Policy)**
  Add to Nginx config:
  ```nginx
  add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline';" always;
  ```

- [ ] **Enable HSTS (HTTP Strict Transport Security)** after SSL setup
  ```nginx
  add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
  ```

### 14. Rate Limiting

- [ ] **Configure Nginx rate limiting**
  ```nginx
  # Add to /etc/nginx/nginx.conf in http block
  limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
  limit_req_zone $binary_remote_addr zone=login_limit:10m rate=5r/m;

  # Then in server block for API endpoints:
  location /chatlog {
      limit_req zone=api_limit burst=20 nodelay;
      # ... rest of proxy config
  }
  ```

### 15. Monitoring and Alerting

- [ ] **Set up uptime monitoring** (e.g., UptimeRobot, Pingdom)
  - Monitor: http://31.97.35.144
  - Alert email: your-email@example.com

- [ ] **Monitor disk space**
  ```bash
  sudo tee /usr/local/bin/check-disk-space.sh > /dev/null <<'EOF'
  #!/bin/bash
  THRESHOLD=80
  USAGE=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')

  if [ $USAGE -gt $THRESHOLD ]; then
    echo "WARNING: Disk usage is at ${USAGE}% on $(hostname)" | mail -s "Disk Space Alert" your-email@example.com
  fi
  EOF
  sudo chmod +x /usr/local/bin/check-disk-space.sh
  ```

- [ ] **Schedule disk space checks**
  ```bash
  sudo tee -a /etc/crontab > /dev/null <<'EOF'
  0 */6 * * * root /usr/local/bin/check-disk-space.sh
  EOF
  ```

---

## 📊 Low Priority (Nice to Have)

### 16. Advanced Monitoring

- [ ] **Install Prometheus + Grafana** for metrics
- [ ] **Set up centralized logging** (ELK stack or Loki)
- [ ] **Enable Docker metrics collection**

### 17. Vulnerability Scanning

- [ ] **Enable Dependabot** on GitHub repositories
  - Go to repository Settings → Security & analysis
  - Enable Dependabot alerts and security updates

- [ ] **Run periodic vulnerability scans**
  ```bash
  sudo apt install -y lynis
  sudo lynis audit system
  ```

### 18. Network Segmentation

- [ ] **Create separate Docker networks** for each service (already partially done ✓)
- [ ] **Implement VPN access** for SSH (e.g., WireGuard)

---

## 🔍 Regular Maintenance Schedule

### Daily
- [ ] Check Fail2Ban logs: `sudo fail2ban-client status sshd`
- [ ] Review Docker container health: `docker ps`
- [ ] Check system resources: `htop` or `top`

### Weekly
- [ ] Review system logs: `sudo journalctl -p err -b`
- [ ] Check for package updates: `sudo apt update && sudo apt list --upgradable`
- [ ] Review backup success: `ls -lh /opt/oinride/backups/`

### Monthly
- [ ] Rotate GitHub Personal Access Tokens
- [ ] Review Nginx access logs for suspicious activity
- [ ] Test disaster recovery procedures
- [ ] Review and update firewall rules

### Quarterly
- [ ] Change all passwords and secrets
- [ ] Audit user access and permissions
- [ ] Review and update security policies
- [ ] Perform penetration testing

---

## 🚨 Incident Response Plan

If you detect malware or suspicious activity:

1. **Immediate Actions**
   - [ ] Disconnect affected services: `docker-compose down`
   - [ ] Block suspicious IPs in firewall: `sudo ufw deny from <IP>`
   - [ ] Take system snapshot/backup
   - [ ] Document everything

2. **Investigation**
   - [ ] Check process list: `ps aux`
   - [ ] Check network connections: `sudo netstat -tulpn`
   - [ ] Check cron jobs: `sudo crontab -l -u root`
   - [ ] Check system logs: `sudo journalctl -xe`

3. **Remediation**
   - [ ] Kill malicious processes: `sudo kill -9 <PID>`
   - [ ] Remove malicious files and cron jobs
   - [ ] Change ALL passwords and keys
   - [ ] Restore from known-good backup if necessary

4. **Recovery**
   - [ ] Verify system is clean
   - [ ] Restart services: `docker-compose up -d`
   - [ ] Monitor closely for 48 hours

5. **Post-Incident**
   - [ ] Document lessons learned
   - [ ] Update security procedures
   - [ ] Implement additional preventive measures

---

## ✅ Security Checklist Summary

**Critical** (16 items) - Complete within 24 hours
- ✓ Change all passwords and keys
- ✓ Verify VPS is clean
- ✓ Configure firewall
- ✓ Harden SSH
- ✓ Install Fail2Ban

**High Priority** (10 items) - Complete within 1 week
- ⏳ Enable automatic updates
- ⏳ Docker security hardening
- ⏳ File integrity monitoring
- ⏳ Log monitoring
- ⏳ Database security

**Medium Priority** (5 items) - Complete within 1 month
- ⏳ SSL/TLS setup
- ⏳ Backup strategy
- ⏳ Rate limiting
- ⏳ Monitoring and alerting

**Low Priority** - Ongoing improvements
- 📅 Advanced monitoring
- 📅 Vulnerability scanning
- 📅 Regular maintenance

---

## 📚 Additional Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [CIS Ubuntu 22.04 Benchmark](https://www.cisecurity.org/benchmark/ubuntu_linux)
- [Docker Security Best Practices](https://docs.docker.com/engine/security/)
- [Nginx Security Guide](https://nginx.org/en/docs/http/ngx_http_ssl_module.html)

---

**Remember:** Security is an ongoing process, not a one-time setup. Review this checklist regularly and stay informed about new threats and best practices.
