#!/bin/bash

# Secure Full Stack VPS Deployment Script
# Part 1: Run as ROOT to create deploy user
# Part 2: Run as DEPLOY user to install everything

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo "🚀 Safety Agent - Secure Full Stack Deployment"
echo "==============================================="

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo -e "${BLUE}Running as root - Setting up deploy user...${NC}\n"

    # Create deploy user if doesn't exist
    if id "deploy" &>/dev/null; then
        echo -e "${GREEN}✓ Deploy user already exists${NC}"
    else
        echo -e "${YELLOW}Creating deploy user...${NC}"
        adduser --disabled-password --gecos "" deploy
        echo -e "${GREEN}✓ Deploy user created${NC}"
    fi

    # Add deploy to sudo and docker groups
    usermod -aG sudo deploy
    usermod -aG docker deploy 2>/dev/null || echo "Docker group will be added later"

    # Set password for deploy user
    echo -e "${YELLOW}Please set a password for deploy user:${NC}"
    passwd deploy

    # Copy this script to deploy user's home
    cp "$0" /home/deploy/deploy-secure.sh
    chown deploy:deploy /home/deploy/deploy-secure.sh
    chmod +x /home/deploy/deploy-secure.sh

    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}✓ Deploy user setup complete!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "${YELLOW}Now switch to deploy user and run the script again:${NC}"
    echo -e "  su - deploy"
    echo -e "  ./deploy-secure.sh"
    echo ""
    exit 0
fi

# From here on, running as deploy user
echo -e "${BLUE}Running as deploy user - Installing application...${NC}\n"

set -e

# Get VPS IP
VPS_IP=$(hostname -I | awk '{print $1}')
echo -e "${BLUE}VPS IP: ${VPS_IP}${NC}\n"

# Step 1: Update system
echo -e "${YELLOW}[1/12] Updating system...${NC}"
sudo apt update && sudo apt upgrade -y

# Step 2: Install Docker
echo -e "${YELLOW}[2/12] Installing Docker...${NC}"
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker deploy
    rm get-docker.sh
    echo -e "${GREEN}✓ Docker installed${NC}"
    echo -e "${YELLOW}⚠️  You need to log out and log back in for Docker group to take effect${NC}"
    echo -e "${YELLOW}   After logging back in, run this script again${NC}"
    exit 0
else
    echo -e "${GREEN}✓ Docker already installed${NC}"
fi

# Check if user is in docker group
if ! groups | grep -q docker; then
    echo -e "${RED}⚠️  You are not in the docker group yet${NC}"
    echo -e "${YELLOW}   Log out and log back in, then run this script again${NC}"
    exit 1
fi

# Step 3: Install Docker Compose
echo -e "${YELLOW}[3/12] Installing Docker Compose...${NC}"
if ! command -v docker-compose &> /dev/null; then
    sudo apt install docker-compose -y
    echo -e "${GREEN}✓ Docker Compose installed${NC}"
else
    echo -e "${GREEN}✓ Docker Compose already installed${NC}"
fi

# Step 4: Install Nginx
echo -e "${YELLOW}[4/12] Installing Nginx...${NC}"
sudo apt install nginx -y
echo -e "${GREEN}✓ Nginx installed${NC}"

# Step 5: Install Git
echo -e "${YELLOW}[5/12] Installing Git...${NC}"
sudo apt install git -y
echo -e "${GREEN}✓ Git installed${NC}"

# Step 6: Install Node.js 20.x
echo -e "${YELLOW}[6/12] Installing Node.js...${NC}"
if ! command -v node &> /dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt install -y nodejs
    echo -e "${GREEN}✓ Node.js installed (version: $(node --version))${NC}"
else
    echo -e "${GREEN}✓ Node.js already installed (version: $(node --version))${NC}"
fi

# Step 7: Install PM2
echo -e "${YELLOW}[7/12] Installing PM2...${NC}"
if ! command -v pm2 &> /dev/null; then
    sudo npm install -g pm2
    echo -e "${GREEN}✓ PM2 installed${NC}"
else
    echo -e "${GREEN}✓ PM2 already installed${NC}"
fi

# Step 8: Clone Backend Repository
echo -e "${YELLOW}[8/12] Setting up Backend...${NC}"
cd ~
if [ -d "Safety_Agent" ]; then
    echo -e "${YELLOW}Backend directory exists, pulling latest changes...${NC}"
    cd Safety_Agent
    git pull
else
    git clone https://github.com/HabibaIbrahim/Safety_Agent.git
    cd Safety_Agent
fi
echo -e "${GREEN}✓ Backend repository ready at: ~/Safety_Agent${NC}"

# Step 9: Configure Backend Environment
echo -e "${YELLOW}[9/12] Configuring Backend...${NC}"

# Check if environment file already exists
if [ -f "docker-compose/.postgres.production" ]; then
    echo -e "${YELLOW}Environment file already exists${NC}"
    read -p "Do you want to update it? (y/n): " UPDATE_ENV
    if [ "$UPDATE_ENV" != "y" ]; then
        echo -e "${YELLOW}Skipping environment configuration${NC}"
        cd docker-compose
    else
        read -p "Enter Google API Key: " GOOGLE_KEY
        read -sp "Enter database password: " DB_PASS
        echo
        cd docker-compose
        cat > .postgres.production <<EOF
POSTGRES_DB=oinride_production
POSTGRES_USER=oinride_admin
POSTGRES_PASSWORD=$DB_PASS
POSTGRES_PASSWORD_FLAT=$DB_PASS
POSTGRES_HOST=db
POSTGRES_PORT=5432
GOOGLE_API_KEY=$GOOGLE_KEY
PGADMIN_EMAIL=admin@oinride.com
PGADMIN_PASSWORD=Admin2025!Secure
EOF
        echo -e "${GREEN}✓ Environment file updated${NC}"
    fi
else
    read -p "Enter Google API Key: " GOOGLE_KEY
    read -sp "Enter database password: " DB_PASS
    echo
    cd docker-compose
    cat > .postgres.production <<EOF
POSTGRES_DB=oinride_production
POSTGRES_USER=oinride_admin
POSTGRES_PASSWORD=$DB_PASS
POSTGRES_PASSWORD_FLAT=$DB_PASS
POSTGRES_HOST=db
POSTGRES_PORT=5432
GOOGLE_API_KEY=$GOOGLE_KEY
PGADMIN_EMAIL=admin@oinride.com
PGADMIN_PASSWORD=Admin2025!Secure
EOF
    echo -e "${GREEN}✓ Environment file created${NC}"
fi

# Build and start backend
echo -e "${YELLOW}Building Docker containers (this may take a few minutes)...${NC}"
docker-compose -f docker-compose.production.yml build

echo -e "${YELLOW}Starting backend services...${NC}"
docker-compose -f docker-compose.production.yml up -d

echo -e "${YELLOW}Waiting for services to start...${NC}"
sleep 15

# Run migrations
echo -e "${YELLOW}Running database migrations...${NC}"
docker-compose -f docker-compose.production.yml exec -T web python manage.py migrate

# Collect static files
echo -e "${YELLOW}Collecting static files...${NC}"
docker-compose -f docker-compose.production.yml exec -T web python manage.py collectstatic --noinput

echo -e "${GREEN}✓ Backend deployed at: /home/deploy/Safety_Agent${NC}"

# Step 10: Clone Frontend Repository
echo -e "${YELLOW}[10/12] Setting up Frontend...${NC}"
cd ~
if [ -d "oinride-agent-ai" ]; then
    echo -e "${YELLOW}Frontend directory exists, pulling latest changes...${NC}"
    cd oinride-agent-ai
    git pull
else
    git clone https://github.com/MahmoudSayed0/oinride-agent-ai.git oinride-agent-ai
    cd oinride-agent-ai
fi
echo -e "${GREEN}✓ Frontend repository ready at: ~/oinride-agent-ai${NC}"

# Step 11: Configure and Deploy Frontend
echo -e "${YELLOW}[11/12] Deploying Frontend...${NC}"

# Create production environment file
cat > .env.local <<EOF
# API Configuration (Server-side - proxy will use this)
API_BASE_URL=http://localhost:8000

# Frontend Configuration
NEXT_PUBLIC_API_TARGET=http://${VPS_IP}
NEXT_PUBLIC_APP_URL=http://${VPS_IP}
EOF

echo -e "${YELLOW}Installing frontend dependencies (this may take a few minutes)...${NC}"
npm install

echo -e "${YELLOW}Building frontend...${NC}"
npm run build

# Stop existing PM2 process if running
pm2 delete frontend 2>/dev/null || true

# Start with PM2
echo -e "${YELLOW}Starting frontend with PM2...${NC}"
pm2 start npm --name "frontend" -- start

# Save PM2 configuration
pm2 save

# Setup PM2 to start on boot
sudo env PATH=$PATH:/usr/bin pm2 startup systemd -u deploy --hp /home/deploy
pm2 save

echo -e "${GREEN}✓ Frontend deployed at: /home/deploy/oinride-agent-ai${NC}"

# Step 12: Configure Nginx
echo -e "${YELLOW}[12/12] Configuring Nginx...${NC}"

sudo tee /etc/nginx/sites-available/safety-agent > /dev/null <<EOF
server {
    listen 80;
    server_name ${VPS_IP};

    client_max_body_size 10M;

    # Backend API endpoints
    location /chatlog/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }

    # Django Admin
    location /admin/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # Static files (Django)
    location /static/ {
        alias /home/deploy/Safety_Agent/staticfiles/;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }

    # Media files (Uploaded PDFs)
    location /media/ {
        alias /home/deploy/Safety_Agent/media/;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }

    # Frontend - Next.js application (all other requests)
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_cache_bypass \$http_upgrade;
    }
}
EOF

# Enable site
sudo ln -sf /etc/nginx/sites-available/safety-agent /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# Test Nginx configuration
sudo nginx -t

# Restart Nginx
sudo systemctl restart nginx

echo -e "${GREEN}✓ Nginx configured and restarted${NC}"

# Configure firewall
echo -e "${YELLOW}Configuring firewall...${NC}"
sudo ufw allow 22
sudo ufw allow 80
sudo ufw allow 443
echo "y" | sudo ufw enable || true

echo -e "${GREEN}✓ Firewall configured${NC}"

# Summary
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✓ Full Stack Deployment Complete! 🎉${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}📁 Folder Locations:${NC}"
echo -e "  Backend:  /home/deploy/Safety_Agent"
echo -e "  Frontend: /home/deploy/oinride-agent-ai"
echo ""
echo -e "${BLUE}🌐 Your application is now running at:${NC}"
echo -e "  Frontend:     http://${VPS_IP}"
echo -e "  Backend API:  http://${VPS_IP}/chatlog/"
echo -e "  Django Admin: http://${VPS_IP}/admin/"
echo ""
echo -e "${BLUE}👤 Create Django Admin User:${NC}"
echo "  cd ~/Safety_Agent/docker-compose"
echo "  docker-compose -f docker-compose.production.yml exec web python manage.py createsuperuser"
echo ""
echo -e "${BLUE}🧪 Test Your Deployment:${NC}"
echo "  curl http://${VPS_IP}/chatlog/get-all-users/"
echo "  curl http://${VPS_IP}/"
echo ""
echo -e "${BLUE}📊 View Logs:${NC}"
echo "  Backend:  cd ~/Safety_Agent/docker-compose && docker-compose -f docker-compose.production.yml logs -f"
echo "  Frontend: pm2 logs frontend"
echo ""
echo -e "${BLUE}🔄 Restart Services:${NC}"
echo "  Backend:  cd ~/Safety_Agent/docker-compose && docker-compose -f docker-compose.production.yml restart"
echo "  Frontend: pm2 restart frontend"
echo "  Nginx:    sudo systemctl restart nginx"
echo ""
echo -e "${BLUE}📈 Service Status:${NC}"
echo "  Backend:  cd ~/Safety_Agent/docker-compose && docker-compose -f docker-compose.production.yml ps"
echo "  Frontend: pm2 status"
echo "  Nginx:    sudo systemctl status nginx"
echo ""
