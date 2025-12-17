# GitHub Secrets Configuration Guide

This document explains all GitHub Secrets that need to be added to your repositories for the CI/CD pipeline to work.

## Overview

GitHub Secrets are encrypted environment variables that are used during GitHub Actions workflows. They keep sensitive information secure and out of your codebase.

---

## How to Add Secrets to GitHub

1. Go to your repository on GitHub
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **"New repository secret"**
4. Enter the secret name (exactly as shown below)
5. Enter the secret value
6. Click **"Add secret"**

---

## Secrets for ALL 3 Repositories

These secrets must be added to **ALL THREE** repositories:
- OSA-Server (Backend)
- oinride_agent_ai (Frontend)
- OSA-admin-panal (Admin Panel)

### 1. VPS_HOST
**Value:** `31.97.35.144`
**Purpose:** The IP address of your VPS server

### 2. VPS_USERNAME
**Value:** `oinrideadmin`
**Purpose:** The SSH username for VPS access

### 3. VPS_SSH_KEY
**Value:** Your private SSH key content (see instructions below)
**Purpose:** Authentication for SSH deployment

#### How to Get VPS_SSH_KEY Value:

On your local machine:
```bash
# Display your private SSH key
cat ~/.ssh/id_ed25519

# Copy the ENTIRE output including:
# -----BEGIN OPENSSH PRIVATE KEY-----
# ... (all the key content)
# -----END OPENSSH PRIVATE KEY-----
```

**IMPORTANT:**
- Copy the entire key including the BEGIN and END lines
- Do NOT share this key publicly
- This is different from your public key (id_ed25519.pub)

---

## Secrets for Backend Repository (OSA-Server)

Add these secrets ONLY to the **OSA-Server** repository:

### 4. POSTGRES_PASSWORD
**Value:** `R7u!xVw2sKp@3yNq` (or generate a new strong password)
**Purpose:** PostgreSQL database password

To generate a new secure password:
```bash
openssl rand -base64 32
```

### 5. DJANGO_SECRET_KEY
**Value:** (Generate a new secret key - see below)
**Purpose:** Django's secret key for cryptographic signing

To generate a new Django secret key:
```bash
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Or use this online generator: https://djecrety.ir/

### 6. GOOGLE_API_KEY
**Value:** `AIzaSyDWU0U4C7-9rlRfC8ODSjbvjHKKo55AeSc` (your existing key)
**Purpose:** Google Maps API access

### 7. GOOGLE_CLIENT_ID
**Value:** `891175220269-btcbo6gf0jouraq9m936s8gnqdmo9hbj.apps.googleusercontent.com`
**Purpose:** Google OAuth authentication

---

## Secrets for Frontend Repository (oinride_agent_ai)

Add these secrets ONLY to the **oinride_agent_ai** repository:

### 8. NEXT_PUBLIC_API_TARGET
**Value:** `http://31.97.35.144:8000`
**Purpose:** Backend API URL for frontend to connect to

**Note:** Change to `https://` after setting up SSL certificate

### 9. NEXT_PUBLIC_APP_URL
**Value:** `http://31.97.35.144:3006`
**Purpose:** Frontend application URL

**Note:** Change to your domain after DNS setup (e.g., `https://oinride.com`)

### 10. NEXT_PUBLIC_GOOGLE_CLIENT_ID
**Value:** `891175220269-btcbo6gf0jouraq9m936s8gnqdmo9hbj.apps.googleusercontent.com`
**Purpose:** Google OAuth for frontend

---

## Secrets for Admin Panel Repository (OSA-admin-panal)

Add these secrets ONLY to the **OSA-admin-panal** repository:

### 11. ADMIN_NEXT_PUBLIC_API_URL
**Value:** `http://31.97.35.144:8000`
**Purpose:** Backend API URL for admin panel

**Note:** Change to `https://` after setting up SSL certificate

### 12. ADMIN_NEXT_PUBLIC_APP_NAME
**Value:** `Oinride Safety Agent Admin`
**Purpose:** Display name for admin panel

### 13. ADMIN_NEXT_PUBLIC_APP_URL
**Value:** `http://31.97.35.144:3005`
**Purpose:** Admin panel application URL

**Note:** Change to your domain after DNS setup (e.g., `https://oinride.com/admin-panel`)

---

## Quick Reference Table

| Secret Name | Backend | Frontend | Admin | Description |
|-------------|---------|----------|-------|-------------|
| VPS_HOST | ✅ | ✅ | ✅ | VPS IP address |
| VPS_USERNAME | ✅ | ✅ | ✅ | SSH username |
| VPS_SSH_KEY | ✅ | ✅ | ✅ | SSH private key |
| POSTGRES_PASSWORD | ✅ | ❌ | ❌ | Database password |
| DJANGO_SECRET_KEY | ✅ | ❌ | ❌ | Django secret |
| GOOGLE_API_KEY | ✅ | ❌ | ❌ | Google Maps API |
| GOOGLE_CLIENT_ID | ✅ | ❌ | ❌ | Backend OAuth |
| NEXT_PUBLIC_API_TARGET | ❌ | ✅ | ❌ | Frontend API URL |
| NEXT_PUBLIC_APP_URL | ❌ | ✅ | ❌ | Frontend URL |
| NEXT_PUBLIC_GOOGLE_CLIENT_ID | ❌ | ✅ | ❌ | Frontend OAuth |
| ADMIN_NEXT_PUBLIC_API_URL | ❌ | ❌ | ✅ | Admin API URL |
| ADMIN_NEXT_PUBLIC_APP_NAME | ❌ | ❌ | ✅ | Admin name |
| ADMIN_NEXT_PUBLIC_APP_URL | ❌ | ❌ | ✅ | Admin URL |

---

## Security Best Practices

1. **Never commit secrets to git** - Always use GitHub Secrets
2. **Rotate secrets regularly** - Change passwords every 90 days
3. **Use strong passwords** - At least 32 characters with random characters
4. **Limit access** - Only add collaborators who need access
5. **Monitor usage** - Check GitHub Actions logs for any suspicious activity
6. **Use different secrets for production and development**

---

## Testing Your Secrets

After adding all secrets, you can test them by:

1. Creating a test tag (see DEPLOYMENT_INSTRUCTIONS.md)
2. Monitoring the GitHub Actions workflow
3. Checking workflow logs for any "Secret not found" errors

If a secret is missing, the workflow will fail with a clear error message.

---

## Troubleshooting

### "Secret not found" Error
- **Cause:** Secret name is misspelled or not added
- **Fix:** Double-check the secret name matches exactly (case-sensitive)

### "Permission denied (publickey)" Error
- **Cause:** VPS_SSH_KEY is incorrect or not added
- **Fix:** Verify you copied the entire private key including BEGIN/END lines

### Build Arguments Not Working
- **Cause:** Secret names don't match workflow file
- **Fix:** Compare secret names in workflow file with GitHub Secrets page

---

## Need Help?

If you encounter issues:
1. Check GitHub Actions workflow logs
2. Verify all secrets are added correctly
3. Test SSH connection manually: `ssh -i ~/.ssh/id_ed25519 oinrideadmin@31.97.35.144`
4. Review workflow files in `.github/workflows/deploy.yml`
