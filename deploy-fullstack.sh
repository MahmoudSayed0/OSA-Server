#!/bin/bash

# Full Stack VPS Deployment Script
# Deploys both Backend (Django) and Frontend (Next.js) to VPS

echo "🚀 Safety Agent - Full Stack Deployment"
echo "=========================================="

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}Starting deployment process...${NC}\n"

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
    sudo usermod -aG docker $USER
    rm get-docker.sh
    echo -e "${GREEN}✓ Docker installed${NC}"
else
    echo -e "${GREEN}✓ Docker already installed${NC}"
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
    echo -e "${GREEN}✓ Node.js installed${NC}"
else
    echo -e "${GREEN}✓ Node.js already installed${NC}"
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
echo -e "${GREEN}✓ Backend repository ready${NC}"

# Step 9: Configure Backend Environment
echo -e "${YELLOW}[9/12] Configuring Backend...${NC}"
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

# Build and start backend
docker-compose -f docker-compose.production.yml build
docker-compose -f docker-compose.production.yml up -d

echo -e "${YELLOW}Waiting for services to start...${NC}"
sleep 10

# Run migrations
docker-compose -f docker-compose.production.yml exec -T web python manage.py migrate

echo -e "${GREEN}✓ Backend deployed${NC}"

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
echo -e "${GREEN}✓ Frontend repository ready${NC}"

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

# Install dependencies and build
npm install
npm run build

# Stop existing PM2 process if running
pm2 delete frontend 2>/dev/null || true

# Start with PM2
pm2 start npm --name "frontend" -- start

# Save PM2 configuration
pm2 save

# Setup PM2 to start on boot
sudo env PATH=$PATH:/usr/bin pm2 startup systemd -u $USER --hp /home/$USER
pm2 save

echo -e "${GREEN}✓ Frontend deployed${NC}"

# Step 12: Configure Nginx
echo -e "${YELLOW}[12/12] Configuring Nginx...${NC}"

# Configure Backend
sudo tee /etc/nginx/sites-available/safety-agent-backend > /dev/null <<EOF
server {
    listen 80;
    server_name ${VPS_IP};

    client_max_body_size 10M;

    # Backend API
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

    # Media files
    location /media/ {
        alias /home/$USER/Safety_Agent/media/;
    }

    # Frontend (all other requests)
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
sudo ln -sf /etc/nginx/sites-available/safety-agent-backend /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# Test and restart Nginx
sudo nginx -t
sudo systemctl restart nginx

echo -e "${GREEN}✓ Nginx configured${NC}"

# Configure firewall
echo -e "${YELLOW}Configuring firewall...${NC}"
sudo ufw allow 22
sudo ufw allow 80
sudo ufw allow 443
echo "y" | sudo ufw enable

echo -e "${GREEN}✓ Firewall configured${NC}"

# Summary
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✓ Full Stack Deployment Complete! 🎉${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}Your application is now running at:${NC}"
echo -e "  Frontend: http://${VPS_IP}"
echo -e "  Backend API: http://${VPS_IP}/chatlog/"
echo -e "  Django Admin: http://${VPS_IP}/admin/"
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo "  1. Create Django superuser:"
echo "     cd ~/Safety_Agent/docker-compose"
echo "     docker-compose -f docker-compose.production.yml exec web python manage.py createsuperuser"
echo ""
echo "  2. Test the application:"
echo "     curl http://${VPS_IP}/chatlog/get-all-users/"
echo ""
echo -e "${BLUE}View logs:${NC}"
echo "  Backend: cd ~/Safety_Agent/docker-compose && docker-compose -f docker-compose.production.yml logs -f"
echo "  Frontend: pm2 logs frontend"
echo ""
echo -e "${BLUE}Restart services:${NC}"
echo "  Backend: cd ~/Safety_Agent/docker-compose && docker-compose -f docker-compose.production.yml restart web"
echo "  Frontend: pm2 restart frontend"
echo ""
