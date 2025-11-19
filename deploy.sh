#!/bin/bash

# Safety Agent Deployment Script
# Run this on your VPS to deploy the backend

set -e  # Exit on error

echo "🚀 Safety Agent Backend Deployment Script"
echo "=========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo -e "${RED}Please do not run as root. Use a regular user with sudo access.${NC}"
    exit 1
fi

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${YELLOW}Docker not found. Installing Docker...${NC}"
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    rm get-docker.sh
    echo -e "${GREEN}Docker installed successfully!${NC}"
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo -e "${YELLOW}Docker Compose not found. Installing...${NC}"
    sudo apt install docker-compose -y
    echo -e "${GREEN}Docker Compose installed successfully!${NC}"
fi

# Get deployment directory
read -p "Enter deployment directory (default: /home/$USER/Safety_Agent): " DEPLOY_DIR
DEPLOY_DIR=${DEPLOY_DIR:-/home/$USER/Safety_Agent}

# Check if directory exists
if [ ! -d "$DEPLOY_DIR" ]; then
    echo -e "${YELLOW}Directory not found. Cloning repository...${NC}"
    read -p "Enter Git repository URL: " REPO_URL
    git clone $REPO_URL $DEPLOY_DIR
fi

cd $DEPLOY_DIR

# Create production environment file
echo -e "${YELLOW}Creating production environment file...${NC}"
read -p "Enter database name (default: oinride_production): " DB_NAME
DB_NAME=${DB_NAME:-oinride_production}

read -p "Enter database user (default: oinride_user): " DB_USER
DB_USER=${DB_USER:-oinride_user}

read -s -p "Enter database password: " DB_PASSWORD
echo

read -p "Enter Google API Key: " GOOGLE_API_KEY

# Create .postgres.production file
cat > docker-compose/.postgres.production <<EOF
POSTGRES_DB=$DB_NAME
POSTGRES_USER=$DB_USER
POSTGRES_PASSWORD=$DB_PASSWORD
POSTGRES_PASSWORD_FLAT=$DB_PASSWORD
POSTGRES_HOST=db
POSTGRES_PORT=5432
GOOGLE_API_KEY=$GOOGLE_API_KEY
EOF

echo -e "${GREEN}Environment file created!${NC}"

# Update Django settings
echo -e "${YELLOW}Updating Django settings...${NC}"
read -p "Enter your domain (e.g., api.yourdomain.com): " DOMAIN

# Backup original settings
cp Safety_agent_Django/settings.py Safety_agent_Django/settings.py.backup

# Update ALLOWED_HOSTS (simplified - you should do this more carefully)
echo -e "${YELLOW}Please manually update ALLOWED_HOSTS in Safety_agent_Django/settings.py${NC}"
echo "Add: '$DOMAIN' to ALLOWED_HOSTS"

# Build and start Docker containers
echo -e "${YELLOW}Building Docker containers...${NC}"
cd docker-compose
docker-compose -f docker-compose.production.yml build

echo -e "${YELLOW}Starting services...${NC}"
docker-compose -f docker-compose.production.yml up -d

# Wait for services to start
echo -e "${YELLOW}Waiting for services to start...${NC}"
sleep 10

# Run migrations
echo -e "${YELLOW}Running database migrations...${NC}"
docker-compose -f docker-compose.production.yml exec -T web python manage.py migrate

# Create superuser
echo -e "${YELLOW}Creating Django superuser...${NC}"
echo "Please enter superuser details:"
docker-compose -f docker-compose.production.yml exec web python manage.py createsuperuser

# Collect static files
echo -e "${YELLOW}Collecting static files...${NC}"
docker-compose -f docker-compose.production.yml exec -T web python manage.py collectstatic --noinput

# Check status
echo -e "${YELLOW}Checking service status...${NC}"
docker-compose -f docker-compose.production.yml ps

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Deployment completed successfully! 🎉${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Next steps:"
echo "1. Configure Nginx (see DEPLOYMENT_GUIDE.md)"
echo "2. Setup SSL certificates with Certbot"
echo "3. Update DNS records to point to this server"
echo "4. Test the API at http://$DOMAIN"
echo ""
echo "View logs:"
echo "  docker-compose -f docker-compose.production.yml logs -f"
echo ""
echo "Stop services:"
echo "  docker-compose -f docker-compose.production.yml down"
echo ""
