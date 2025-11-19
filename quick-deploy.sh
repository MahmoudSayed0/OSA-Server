#!/bin/bash

# Quick Deploy Script for Hostinger VPS
# Run this on your VPS at 31.97.35.144

echo "🚀 Safety Agent - Quick Deployment Script"
echo "=========================================="

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}Starting deployment process...${NC}\n"

# Step 1: Update system
echo -e "${YELLOW}[1/10] Updating system...${NC}"
sudo apt update && sudo apt upgrade -y

# Step 2: Install Docker
echo -e "${YELLOW}[2/10] Installing Docker...${NC}"
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
echo -e "${YELLOW}[3/10] Installing Docker Compose...${NC}"
if ! command -v docker-compose &> /dev/null; then
    sudo apt install docker-compose -y
    echo -e "${GREEN}✓ Docker Compose installed${NC}"
else
    echo -e "${GREEN}✓ Docker Compose already installed${NC}"
fi

# Step 4: Install Nginx
echo -e "${YELLOW}[4/10] Installing Nginx...${NC}"
sudo apt install nginx -y
echo -e "${GREEN}✓ Nginx installed${NC}"

# Step 5: Install Git
echo -e "${YELLOW}[5/10] Installing Git...${NC}"
sudo apt install git -y
echo -e "${GREEN}✓ Git installed${NC}"

# Step 6: Install Certbot (for SSL)
echo -e "${YELLOW}[6/10] Installing Certbot...${NC}"
sudo apt install certbot python3-certbot-nginx -y
echo -e "${GREEN}✓ Certbot installed${NC}"

# Step 7: Clone repository
echo -e "${YELLOW}[7/10] Cloning repository...${NC}"
read -p "Enter your Git repository URL: " REPO_URL
cd ~
if [ -d "Safety_Agent" ]; then
    echo -e "${YELLOW}Directory exists, pulling latest changes...${NC}"
    cd Safety_Agent
    git pull
else
    git clone $REPO_URL Safety_Agent
    cd Safety_Agent
fi
echo -e "${GREEN}✓ Repository ready${NC}"

# Step 8: Create environment file
echo -e "${YELLOW}[8/10] Setting up environment variables...${NC}"
read -p "Enter Google API Key: " GOOGLE_KEY
read -p "Enter database password: " DB_PASS

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
echo -e "${GREEN}✓ Environment configured${NC}"

# Step 9: Build and start containers
echo -e "${YELLOW}[9/10] Building and starting Docker containers...${NC}"
docker-compose -f docker-compose.production.yml build
docker-compose -f docker-compose.production.yml up -d

echo -e "${YELLOW}Waiting for services to start...${NC}"
sleep 10

# Run migrations
echo -e "${YELLOW}Running database migrations...${NC}"
docker-compose -f docker-compose.production.yml exec -T web python manage.py migrate

echo -e "${GREEN}✓ Backend deployed${NC}"

# Step 10: Configure Nginx
echo -e "${YELLOW}[10/10] Configuring Nginx...${NC}"

VPS_IP=$(hostname -I | awk '{print $1}')

sudo tee /etc/nginx/sites-available/safety-agent-backend > /dev/null <<EOF
server {
    listen 80;
    server_name $VPS_IP;

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }

    location /media/ {
        alias /home/$USER/Safety_Agent/media/;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/safety-agent-backend /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
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
echo -e "${GREEN}✓ Deployment Complete! 🎉${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}Your backend is now running at:${NC}"
echo -e "  http://$VPS_IP"
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo "  1. Create Django superuser:"
echo "     cd ~/Safety_Agent/docker-compose"
echo "     docker-compose -f docker-compose.production.yml exec web python manage.py createsuperuser"
echo ""
echo "  2. Test the API:"
echo "     curl http://$VPS_IP/chatlog/get-all-users/"
echo ""
echo "  3. Access Django admin:"
echo "     http://$VPS_IP/admin/"
echo ""
echo -e "${BLUE}View logs:${NC}"
echo "  docker-compose -f docker-compose.production.yml logs -f"
echo ""
echo -e "${BLUE}Restart backend:${NC}"
echo "  docker-compose -f docker-compose.production.yml restart web"
echo ""
echo -e "${YELLOW}⚠️  Remember to:${NC}"
echo "  - Change your root password: passwd"
echo "  - Setup SSL if you have a domain"
echo "  - Configure regular backups"
echo ""
