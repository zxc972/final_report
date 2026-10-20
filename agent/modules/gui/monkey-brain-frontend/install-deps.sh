#!/bin/bash

# 🧠 Monkey Brain Segmentation Frontend - Dependency Installation Script

set -e  # Exit immediately on error

echo "╔════════════════════════════════════════════════════════════╗"
echo "║                                                            ║"
echo "║        🧠 Monkey Brain Segmentation Frontend - Install     ║"
echo "║                                                            ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions: printing helpers
print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Check if we are in the correct directory
if [ ! -f "package.json" ]; then
    print_error "package.json not found. Please run this script in the monkey-brain-frontend directory."
    exit 1
fi

print_success "Found package.json"

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    print_error "Node.js is not installed."
    echo ""
    echo "Please install Node.js 18+ first:"
    echo ""
    echo "Ubuntu/Debian:"
    echo "  curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -"
    echo "  sudo apt-get install -y nodejs"
    echo ""
    echo "CentOS/RHEL:"
    echo "  curl -fsSL https://rpm.nodesource.com/setup_18.x | sudo bash -"
    echo "  sudo yum install -y nodejs"
    echo ""
    echo "macOS:"
    echo "  brew install node@18"
    echo ""
    exit 1
fi

NODE_VERSION=$(node --version)
print_success "Node.js installed: $NODE_VERSION"

# Check if npm is installed
if ! command -v npm &> /dev/null; then
    print_error "npm is not installed."
    exit 1
fi

NPM_VERSION=$(npm --version)
print_success "npm installed: $NPM_VERSION"

# Ask user to choose installation method
echo ""
print_info "Please choose an installation method:"
echo "  1) npm install (standard install)"
echo "  2) npm ci (fast install, recommended for CI/CD)"
echo "  3) npm install --production (production dependencies only)"
echo "  4) Use Taobao mirror for installation (recommended for users in China)"
echo "  5) Clean up and reinstall"
echo ""
read -p "Enter choice (1-5, default 1): " choice
choice=${choice:-1}

case $choice in
    1)
        print_info "Starting standard installation..."
        npm install
        ;;
        
    2)
        print_info "Starting fast installation (npm ci)..."
        npm ci
        ;;
        
    3)
        print_info "Installing production dependencies..."
        npm install --production
        ;;
        
    4)
        print_info "Installing using Taobao mirror..."
        npm install --registry=https://registry.npmmirror.com
        ;;
        
    5)
        print_warning "Cleaning existing dependencies..."
        rm -rf node_modules package-lock.json
        print_info "Reinstalling..."
        npm install
        ;;
        
    *)
        print_error "Invalid option, falling back to default installation."
        npm install
        ;;
esac

# Check whether installation succeeded
if [ $? -eq 0 ]; then
    echo ""
    print_success "Dependencies installed successfully!"
    echo ""
    echo "════════════════════════════════════════════════════════════"
    echo ""
    echo "📋 Next steps:"
    echo ""
    echo "  1. Start the server:"
    echo " Use singularity to run primx gui start "
    echo "════════════════════════════════════════════════════════════"
    echo ""
else
    print_error "Dependency installation failed."
    echo ""
    echo "Common fixes:"
    echo "  1. Clear cache: npm cache clean --force"
    echo "  2. Remove node_modules: rm -rf node_modules"
    echo "  3. Use Taobao mirror: npm install --registry=https://registry.npmmirror.com"
    echo "  4. View verbose log: npm install --verbose"
    echo ""
    exit 1
fi
