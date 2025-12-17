# Oinride CI/CD Pipeline - Complete Deployment Instructions

## 🎯 Overview

This guide provides **step-by-step instructions** for setting up the complete CI/CD pipeline for Oinride platform. Follow these instructions carefully to deploy your backend, frontend, and admin panel to your VPS at `31.97.35.144`.

**What this pipeline does:**
- Automatically builds Docker images when you create a release tag (v1.0.0, v1.1.0, etc.)
- Pushes images to GitHub Container Registry (ghcr.io)
- Deploys to your VPS via SSH
- Runs migrations and collects static files (backend)
- Zero downtime after initial setup

---

## 📋 Prerequisites

Before starting, ensure you have:

- [ ] VPS at 31.97.35.144 with Ubuntu 22.04
- [ ] Docker and Docker Compose installed on VPS
- [ ] Nginx installed on VPS
- [ ] UFW firewall configured (ports 22, 80, 443 open)
- [ ] SSH access to VPS as `oinrideadmin` user
- [ ] GitHub accounts with access to all 3 repositories
- [ ] Your VPS is clean (no malware - see SECURITY_HARDENING_CHECKLIST.md)

---

## 🚀 Part 1: Push Code Changes to GitHub

I've created all the necessary Docker and CI/CD configuration files for you. Now you need to push these changes to your GitHub repositories.

### Step 1.1: Backend Repository (OSA-Server / Safety_Agent)

```bash
cd /Users/mahmoudomar/Work/Oinride/Safety_Agent

# Check what files were created
git status

# Add all new files
git add .github/workflows/deploy.yml
git add docker-compose.prod.yml
git add .env.production.example
git add nginx.conf.prod
git add vps-setup.sh
git add GITHUB_SECRETS.md
git add SECURITY_HARDENING_CHECKLIST.md
git add DEPLOYMENT_INSTRUCTIONS.md

# Commit changes
git commit -m "Add CI/CD pipeline with Docker deployment

- Add GitHub Actions workflow for automated deployment
- Add production docker-compose configuration
- Add VPS setup script and documentation
- Add security hardening checklist
- Configure deployment to trigger on version tags

🤖 Generated with Claude Code"

# Push to GitHub
git push origin main
```

### Step 1.2: Frontend Repository (oinride_agent_ai)

```bash
cd /Users/mahmoudomar/Work/Oinride/oinride_agent_ai

# Check what files were created
git status

# Add all new files
git add Dockerfile
git add .dockerignore
git add next.config.js
git add .github/workflows/deploy.yml
git add docker-compose.prod.yml

# Commit changes
git commit -m "Add Docker support and CI/CD pipeline

- Add multi-stage Dockerfile for production builds
- Enable Next.js standalone output mode
- Add GitHub Actions workflow for automated deployment
- Add production docker-compose configuration
- Configure environment variables injection at build time

🤖 Generated with Claude Code"

# Push to GitHub
git push origin main
```

### Step 1.3: Admin Panel Repository (OSA-admin-panal / oinride-admin-panel)

```bash
cd /Users/mahmoudomar/Work/Oinride/oinride-admin-panel

# Check what files were created
git status

# Add all new files
git add Dockerfile
git add .dockerignore
git add next.config.ts
git add .github/workflows/deploy.yml
git add docker-compose.prod.yml

# Commit changes
git commit -m "Add Docker support and CI/CD pipeline

- Add multi-stage Dockerfile for production builds
- Enable Next.js standalone output mode
- Add GitHub Actions workflow for automated deployment
- Add production docker-compose configuration
- Configure environment variables injection at build time

🤖 Generated with Claude Code"

# Push to GitHub
git push origin main
```

---

## 🔐 Part 2: Configure GitHub Secrets

You need to add secrets to each GitHub repository. These secrets are encrypted and used by GitHub Actions during deployment.

### Step 2.1: Generate Required Secrets

**On your local machine:**

```bash
# 1. Display your SSH private key (for VPS_SSH_KEY)
cat ~/.ssh/id_ed25519

# Copy the ENTIRE output including BEGIN and END lines

# 2. Generate new Django SECRET_KEY
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# Copy the output

# 3. Generate new PostgreSQL password (optional - can use existing)
openssl rand -base64 32

# Copy the output
```

### Step 2.2: Add Secrets to Backend Repository

**Repository:** OSA-Server (or your backend repo name)

1. Go to: `https://github.com/MahmoudSayed0/OSA-Server/settings/secrets/actions`
2. Click **"New repository secret"** for each of the following:

| Secret Name | Value |
|------------|-------|
| `VPS_HOST` | `31.97.35.144` |
| `VPS_USERNAME` | `oinrideadmin` |
| `VPS_SSH_KEY` | Your SSH private key (from `cat ~/.ssh/id_ed25519`) |
| `POSTGRES_PASSWORD` | `R7u!xVw2sKp@3yNq` (or generate new one) |
| `DJANGO_SECRET_KEY` | Generated Django secret key |
| `GOOGLE_API_KEY` | `YOUR_GOOGLE_API_KEY_HERE` |
| `GOOGLE_CLIENT_ID` | `891175220269-btcbo6gf0jouraq9m936s8gnqdmo9hbj.apps.googleusercontent.com` |

### Step 2.3: Add Secrets to Frontend Repository

**Repository:** oinride_agent_ai

1. Go to: `https://github.com/YOUR_USERNAME/oinride_agent_ai/settings/secrets/actions`
2. Click **"New repository secret"** for each of the following:

| Secret Name | Value |
|------------|-------|
| `VPS_HOST` | `31.97.35.144` |
| `VPS_USERNAME` | `oinrideadmin` |
| `VPS_SSH_KEY` | Your SSH private key (same as backend) |
| `NEXT_PUBLIC_API_TARGET` | `http://31.97.35.144:8000` |
| `NEXT_PUBLIC_APP_URL` | `http://31.97.35.144:3006` |
| `NEXT_PUBLIC_GOOGLE_CLIENT_ID` | `891175220269-btcbo6gf0jouraq9m936s8gnqdmo9hbj.apps.googleusercontent.com` |

### Step 2.4: Add Secrets to Admin Panel Repository

**Repository:** OSA-admin-panal

1. Go to: `https://github.com/MahmoudSayed0/OSA-admin-panal/settings/secrets/actions`
2. Click **"New repository secret"** for each of the following:

| Secret Name | Value |
|------------|-------|
| `VPS_HOST` | `31.97.35.144` |
| `VPS_USERNAME` | `oinrideadmin` |
| `VPS_SSH_KEY` | Your SSH private key (same as backend) |
| `ADMIN_NEXT_PUBLIC_API_URL` | `http://31.97.35.144:8000` |
| `ADMIN_NEXT_PUBLIC_APP_NAME` | `Oinride Safety Agent Admin` |
| `ADMIN_NEXT_PUBLIC_APP_URL` | `http://31.97.35.144:3005` |

**📝 Detailed instructions:** See `GITHUB_SECRETS.md` for more information

---

## 🖥️ Part 3: Setup VPS

Now you need to configure your VPS server to receive deployments.

### Step 3.1: Copy Setup Script to VPS

**On your local machine:**

```bash
# Copy the setup script to your VPS
scp /Users/mahmoudomar/Work/Oinride/Safety_Agent/vps-setup.sh oinrideadmin@31.97.35.144:~/
```

### Step 3.2: Run Setup Script on VPS

**SSH into your VPS:**

```bash
ssh oinrideadmin@31.97.35.144
```

**Run the setup script:**

```bash
# Make script executable
chmod +x ~/vps-setup.sh

# Run the script
bash ~/vps-setup.sh
```

This script will:
- ✅ Create directory structure (/opt/oinride/*)
- ✅ Create docker-compose.yml files for all 3 services
- ✅ Create backend .env file template
- ✅ Configure Nginx
- ✅ Login to GitHub Container Registry

**⚠️ IMPORTANT:** After the script completes, you MUST edit the backend .env file:

```bash
nano /opt/oinride/backend/.env
```

Replace these values:
- `POSTGRES_PASSWORD` → Use the same value you added to GitHub Secrets
- `DJANGO_SECRET_KEY` → Use the same value you added to GitHub Secrets
- `GOOGLE_API_KEY` → Your actual Google API key
- `GOOGLE_CLIENT_ID` → Your actual Google Client ID

Save and exit (Ctrl+X, then Y, then Enter)

### Step 3.3: Verify VPS Setup

```bash
# Check directory structure
ls -la /opt/oinride/

# Should show:
# backend/
# frontend/
# admin-panel/

# Verify Nginx configuration
sudo nginx -t

# Check firewall
sudo ufw status

# Test GitHub Container Registry login
docker pull ghcr.io/mahmoudsayed0/osa-backend:latest || echo "No images yet - this is expected"
```

---

## 🎉 Part 4: First Deployment (Test)

Now let's test the CI/CD pipeline by creating a test release!

### Step 4.1: Create Test Release for Backend

```bash
cd /Users/mahmoudomar/Work/Oinride/Safety_Agent

# Create a test tag
git tag -a v0.1.0 -m "Test deployment - Backend v0.1.0"

# Push the tag to trigger GitHub Actions
git push origin v0.1.0
```

### Step 4.2: Monitor GitHub Actions

1. Go to: `https://github.com/MahmoudSayed0/OSA-Server/actions`
2. You should see a workflow running for "Build and Deploy Backend"
3. Click on the workflow to see logs
4. Wait for it to complete (approximately 5-10 minutes)

**If successful, you'll see:**
- ✅ Checkout code
- ✅ Login to GitHub Container Registry
- ✅ Build and push Docker image
- ✅ Deploy to VPS
- ✅ Run migrations
- ✅ Collect static files

### Step 4.3: Verify Backend Deployment

**On your VPS:**

```bash
ssh oinrideadmin@31.97.35.144

# Check if containers are running
docker ps

# Should show:
# osa_backend_web
# osa_backend_db

# Check container logs
docker-compose -f /opt/oinride/backend/docker-compose.yml logs --tail=50 web

# Test the backend API
curl http://localhost:8000/health/
```

**In your browser:**
```
http://31.97.35.144/chatlog/
```

Should show Django API response!

### Step 4.4: Deploy Frontend

```bash
cd /Users/mahmoudomar/Work/Oinride/oinride_agent_ai

# Create release tag
git tag -a v0.1.0 -m "Test deployment - Frontend v0.1.0"
git push origin v0.1.0
```

Monitor at: GitHub Actions page for frontend repository

**Verify frontend:**
```
http://31.97.35.144/
```

### Step 4.5: Deploy Admin Panel

```bash
cd /Users/mahmoudomar/Work/Oinride/oinride-admin-panel

# Create release tag
git tag -a v0.1.0 -m "Test deployment - Admin Panel v0.1.0"
git push origin v0.1.0
```

Monitor at: GitHub Actions page for admin repository

**Verify admin panel:**
```
http://31.97.35.144/admin-panel
```

---

## 🔄 Part 5: Production Deployment Workflow

After successful testing, here's how to deploy updates:

### For Regular Updates:

1. **Make your code changes**
2. **Test locally**
3. **Commit and push to GitHub:**
   ```bash
   git add .
   git commit -m "Your change description"
   git push origin main
   ```

4. **Create a release tag:**
   ```bash
   git tag -a v1.0.0 -m "Production release v1.0.0"
   git push origin v1.0.0
   ```

5. **GitHub Actions automatically:**
   - Builds Docker image
   - Pushes to ghcr.io
   - Deploys to VPS
   - Runs migrations (backend only)
   - Restarts containers

6. **Verify deployment:**
   - Check GitHub Actions logs
   - Test the application in browser
   - Check VPS logs if needed

### Versioning Guidelines:

Use semantic versioning (MAJOR.MINOR.PATCH):
- `v1.0.0` → First production release
- `v1.0.1` → Bug fix (patch)
- `v1.1.0` → New feature (minor)
- `v2.0.0` → Breaking change (major)

---

## 🛑 Part 6: Troubleshooting

### Issue: GitHub Actions fails with "Permission denied (publickey)"

**Solution:**
```bash
# Verify your SSH key is correct
cat ~/.ssh/id_ed25519

# Test SSH connection
ssh oinrideadmin@31.97.35.144

# Re-add VPS_SSH_KEY secret to GitHub if needed
```

### Issue: Docker pull fails with "unauthorized"

**Solution:**
```bash
# On VPS, re-login to GitHub Container Registry
ssh oinrideadmin@31.97.35.144

# Generate new GitHub PAT at: https://github.com/settings/tokens/new
# Scope: read:packages

# Login
echo "YOUR_PAT" | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
```

### Issue: "Secret not found" in GitHub Actions

**Solution:**
- Go to repository Settings → Secrets and variables → Actions
- Verify all secrets are added correctly
- Secret names are case-sensitive
- Re-add the missing secret

### Issue: Container won't start

**Solution:**
```bash
ssh oinrideadmin@31.97.35.144

# Check logs
docker-compose -f /opt/oinride/backend/docker-compose.yml logs web

# Common issues:
# - Missing environment variables in .env
# - Database connection failed
# - Port already in use

# Restart containers
docker-compose -f /opt/oinride/backend/docker-compose.yml restart
```

### Issue: Nginx shows 502 Bad Gateway

**Solution:**
```bash
# Check if containers are running
docker ps

# If not running, start them
cd /opt/oinride/backend
docker-compose up -d

# Check Nginx logs
sudo tail -f /var/log/nginx/error.log
```

---

## 🔒 Part 7: Security - Prevent Future Malware

**⚠️ CRITICAL:** Follow the security hardening checklist to prevent malware infections like the system3d cryptominer you experienced.

### Immediate Actions (Do Now):

1. **Run security checklist:**
   ```bash
   # Read and follow the checklist
   cat /Users/mahmoudomar/Work/Oinride/Safety_Agent/SECURITY_HARDENING_CHECKLIST.md
   ```

2. **Install Fail2Ban (blocks brute force attacks):**
   ```bash
   ssh oinrideadmin@31.97.35.144
   sudo apt update
   sudo apt install -y fail2ban
   sudo systemctl enable fail2ban
   sudo systemctl start fail2ban
   ```

3. **Enable automatic security updates:**
   ```bash
   sudo apt install -y unattended-upgrades
   sudo dpkg-reconfigure -plow unattended-upgrades
   ```

4. **Disable SSH password authentication (key-only):**
   ```bash
   sudo nano /etc/ssh/sshd_config

   # Set these values:
   PasswordAuthentication no
   PermitRootLogin no

   # Save and restart
   sudo systemctl restart sshd
   ```

5. **Scan for malware weekly:**
   ```bash
   # Install security tools
   sudo apt install -y rkhunter chkrootkit lynis

   # Run scan
   sudo rkhunter --check --skip-keypress
   sudo chkrootkit
   sudo lynis audit system
   ```

### Why These Steps Matter:

The system3d cryptominer you had was likely installed through:
- Weak SSH passwords (brute force attack)
- Unpatched security vulnerabilities
- Compromised user credentials
- Malicious scripts in cron jobs

By following the security checklist, you:
- ✅ Block brute force attacks automatically
- ✅ Keep system updated with security patches
- ✅ Remove password-based authentication
- ✅ Detect malware before it spreads
- ✅ Monitor system for suspicious activity

**📚 Full security guide:** `SECURITY_HARDENING_CHECKLIST.md`

---

## 📊 Part 8: Monitoring and Maintenance

### Daily Checks:

```bash
# Check container health
docker ps

# Check resource usage
htop

# Check recent logs
docker-compose -f /opt/oinride/backend/docker-compose.yml logs --tail=50 web
```

### Weekly Maintenance:

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Check disk space
df -h

# Review Fail2Ban blocks
sudo fail2ban-client status sshd

# Check for security updates
sudo unattended-upgrades --dry-run
```

### Monthly Tasks:

- [ ] Review GitHub Actions workflow runs
- [ ] Check Docker image sizes (optimize if needed)
- [ ] Rotate secrets (change passwords)
- [ ] Test backup restoration
- [ ] Review Nginx access logs

---

## 🎓 Additional Resources

- **GitHub Secrets Guide:** `GITHUB_SECRETS.md`
- **Security Hardening:** `SECURITY_HARDENING_CHECKLIST.md`
- **VPS Setup Script:** `vps-setup.sh`
- **Nginx Configuration:** `nginx.conf.prod`
- **Docker Compose Files:** `docker-compose.prod.yml` (in each repo)

---

## 📞 Getting Help

If you encounter issues:

1. **Check GitHub Actions logs** - Most issues show up here
2. **Check VPS logs:**
   ```bash
   docker-compose logs
   sudo journalctl -xe
   sudo tail -f /var/log/nginx/error.log
   ```
3. **Verify secrets are added correctly**
4. **Test SSH connection manually**
5. **Check firewall settings:** `sudo ufw status`

---

## ✅ Deployment Checklist

### On Your Machine:
- [ ] Push code to GitHub (all 3 repos)
- [ ] Add GitHub Secrets (all 3 repos)
- [ ] Generate required secrets (SSH key, Django secret, etc.)

### On VPS:
- [ ] Run vps-setup.sh script
- [ ] Edit /opt/oinride/backend/.env with actual secrets
- [ ] Verify Nginx configuration
- [ ] Login to GitHub Container Registry
- [ ] Follow security hardening checklist

### First Deployment:
- [ ] Create v0.1.0 tags for all 3 repos
- [ ] Monitor GitHub Actions workflows
- [ ] Verify all services are running
- [ ] Test all URLs in browser

### Security:
- [ ] Install Fail2Ban
- [ ] Enable automatic updates
- [ ] Disable SSH password authentication
- [ ] Scan for malware
- [ ] Configure monitoring

---

## 🎉 Success!

If you've followed all steps, you now have:
- ✅ Automated CI/CD pipeline
- ✅ Dockerized applications
- ✅ Secure VPS deployment
- ✅ Easy release process (just create tags!)
- ✅ Protection against malware
- ✅ Professional development workflow

**Next deployment is just one command:**
```bash
git tag -a v1.0.1 -m "New feature"
git push origin v1.0.1
```

Congratulations! Your Oinride platform is now deployed professionally! 🚀
