#!/bin/bash

################################################################################
# Oinride VPS Setup Script
#
# This script sets up the production environment on your VPS (31.97.35.144)
# Run this script ONCE after wiping the VPS or on fresh installation
#
# Usage: bash vps-setup.sh
################################################################################

set -e  # Exit on any error

echo "========================================="
echo "Oinride VPS Setup Script"
echo "========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to print colored output
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_info() {
    echo -e "${BLUE}→ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

################################################################################
# Step 1: Create Directory Structure
################################################################################

print_info "Step 1: Creating directory structure..."

sudo mkdir -p /opt/oinride/{backend,frontend,admin-panel}
sudo chown -R $USER:$USER /opt/oinride

print_success "Directory structure created"

################################################################################
# Step 2: Setup Backend Configuration
################################################################################

print_info "Step 2: Setting up backend configuration..."

# Create docker-compose.yml for backend
cat > /opt/oinride/backend/docker-compose.yml <<'EOF'
version: '3.8'

services:
  db:
    image: ankane/pgvector:latest
    container_name: osa_backend_db
    restart: unless-stopped
    environment:
      POSTGRES_DB: oinride
      POSTGRES_USER: pgadmin_z9f3
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - backend
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U pgadmin_z9f3"]
      interval: 10s
      timeout: 5s
      retries: 5

  web:
    image: ghcr.io/mahmoudsayed0/osa-backend:latest
    container_name: osa_backend_web
    restart: unless-stopped
    ports:
      - "127.0.0.1:8000:8000"
    environment:
      DJANGO_SECRET_KEY: ${DJANGO_SECRET_KEY}
      DEBUG: "False"
      ALLOWED_HOSTS: ${ALLOWED_HOSTS}
      POSTGRES_DB: oinride
      POSTGRES_USER: pgadmin_z9f3
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_HOST: db
      POSTGRES_PORT: 5432
      GOOGLE_API_KEY: ${GOOGLE_API_KEY}
      GOOGLE_CLIENT_ID: ${GOOGLE_CLIENT_ID}
    depends_on:
      db:
        condition: service_healthy
    networks:
      - backend
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health/"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

volumes:
  postgres_data:

networks:
  backend:
    driver: bridge
EOF

# Create .env template for backend
cat > /opt/oinride/backend/.env <<'EOF'
# PostgreSQL Database Configuration
POSTGRES_PASSWORD=CHANGE_THIS_PASSWORD

# Django Configuration
DJANGO_SECRET_KEY=CHANGE_THIS_SECRET_KEY
ALLOWED_HOSTS=31.97.35.144,oinride.com,www.oinride.com

# Google API Configuration
GOOGLE_API_KEY=YOUR_GOOGLE_API_KEY
GOOGLE_CLIENT_ID=YOUR_GOOGLE_CLIENT_ID
EOF

chmod 600 /opt/oinride/backend/.env

print_success "Backend configuration created"
print_warning "IMPORTANT: Edit /opt/oinride/backend/.env and replace all placeholder values!"

################################################################################
# Step 3: Setup Frontend Configuration
################################################################################

print_info "Step 3: Setting up frontend configuration..."

cat > /opt/oinride/frontend/docker-compose.yml <<'EOF'
version: '3.8'

services:
  frontend:
    image: ghcr.io/mahmoudsayed0/osa-frontend:latest
    container_name: osa_frontend
    restart: unless-stopped
    ports:
      - "127.0.0.1:3006:3006"
    environment:
      NODE_ENV: production
    networks:
      - frontend
    healthcheck:
      test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider", "http://localhost:3006/"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

networks:
  frontend:
    driver: bridge
EOF

print_success "Frontend configuration created"

################################################################################
# Step 4: Setup Admin Panel Configuration
################################################################################

print_info "Step 4: Setting up admin panel configuration..."

cat > /opt/oinride/admin-panel/docker-compose.yml <<'EOF'
version: '3.8'

services:
  admin:
    image: ghcr.io/mahmoudsayed0/osa-admin:latest
    container_name: osa_admin
    restart: unless-stopped
    ports:
      - "127.0.0.1:3005:3005"
    environment:
      NODE_ENV: production
    networks:
      - admin
    healthcheck:
      test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider", "http://localhost:3005/"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

networks:
  admin:
    driver: bridge
EOF

print_success "Admin panel configuration created"

################################################################################
# Step 5: Setup Nginx Configuration
################################################################################

print_info "Step 5: Setting up Nginx configuration..."

sudo tee /etc/nginx/sites-available/oinride > /dev/null <<'EOF'
server {
    listen 80;
    server_name 31.97.35.144 oinride.com www.oinride.com;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Increase upload size for file uploads
    client_max_body_size 20M;

    # Frontend (Next.js User App) - Port 3006
    location / {
        proxy_pass http://127.0.0.1:3006;
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

    # Admin Panel - Port 3005
    location /admin-panel {
        rewrite ^/admin-panel(.*)$ $1 break;
        proxy_pass http://127.0.0.1:3005;
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

    # Django Backend API - Port 8000
    location /chatlog {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }

    location /api {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
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

    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/xml text/javascript application/x-javascript application/xml+rss application/json;
}
EOF

# Enable the site
sudo ln -sf /etc/nginx/sites-available/oinride /etc/nginx/sites-enabled/

# Remove default site if exists
sudo rm -f /etc/nginx/sites-enabled/default

# Test nginx configuration
sudo nginx -t

if [ $? -eq 0 ]; then
    sudo systemctl reload nginx
    print_success "Nginx configuration applied successfully"
else
    print_error "Nginx configuration test failed. Please check the config."
    exit 1
fi

################################################################################
# Step 6: Login to GitHub Container Registry
################################################################################

print_info "Step 6: GitHub Container Registry authentication..."
print_warning "You need a GitHub Personal Access Token with 'read:packages' scope"
print_info "Generate one at: https://github.com/settings/tokens/new"
echo ""
read -p "Enter your GitHub username: " GITHUB_USERNAME
read -sp "Enter your GitHub Personal Access Token: " GITHUB_TOKEN
echo ""

echo "$GITHUB_TOKEN" | docker login ghcr.io -u "$GITHUB_USERNAME" --password-stdin

if [ $? -eq 0 ]; then
    print_success "Successfully logged in to GitHub Container Registry"
else
    print_error "Failed to login to GitHub Container Registry"
    exit 1
fi

################################################################################
# Step 7: Create Static Files Directories
################################################################################

print_info "Step 7: Creating static files directories..."

sudo mkdir -p /opt/oinride/backend/{staticfiles,media}
sudo chown -R $USER:$USER /opt/oinride/backend/{staticfiles,media}

print_success "Static files directories created"

################################################################################
# Summary
################################################################################

echo ""
echo "========================================="
echo "Setup Complete!"
echo "========================================="
echo ""
print_success "VPS setup completed successfully!"
echo ""
print_info "Next Steps:"
echo "  1. Edit /opt/oinride/backend/.env with your actual secrets"
echo "  2. Add GitHub Secrets to your repositories (see GITHUB_SECRETS.md)"
echo "  3. Push your code to GitHub"
echo "  4. Create a release tag to trigger deployment: git tag v1.0.0 && git push origin v1.0.0"
echo ""
print_warning "Important Files to Edit:"
echo "  - /opt/oinride/backend/.env (REQUIRED - add your secrets)"
echo ""
print_info "Verify Setup:"
echo "  - Check Docker: docker ps"
echo "  - Check Nginx: sudo nginx -t"
echo "  - Check firewall: sudo ufw status"
echo ""
print_success "Your VPS is now ready for CI/CD deployments!"
