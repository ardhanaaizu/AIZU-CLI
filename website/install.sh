#!/bin/bash
# AIZU-CLI Installer
# Install AIZU-CLI ke sistem kamu

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Banner
echo ""
echo -e "${CYAN}  █████╗ ██╗███████╗██╗   ██╗      ██████╗██╗     ██╗${NC}"
echo -e "${CYAN} ██╔══██╗██║╚══███╔╝██║   ██║     ██╔════╝██║     ██║${NC}"
echo -e "${CYAN} ███████║██║  ███╔╝ ██║   ██║     ██║     ██║     ██║${NC}"
echo -e "${CYAN} ██╔══██║██║ ███╔╝  ██║   ██║     ██║     ██║     ██║${NC}"
echo -e "${CYAN} ██║  ██║██║███████╗╚██████╔╝     ╚██████╗███████╗██║${NC}"
echo -e "${CYAN} ╚═╝  ╚═╝╚═╝╚══════╝ ╚═════╝       ╚═════╝╚══════╝╚═╝${NC}"
echo ""
echo -e "${GREEN}  AI Agent CLI untuk Terminal${NC}"
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python3 tidak ditemukan!${NC}"
    echo "Install Python3 terlebih dahulu:"
    echo "  Ubuntu/Debian: sudo apt install python3"
    echo "  macOS: brew install python3"
    exit 1
fi

# Check if git is installed
if ! command -v git &> /dev/null; then
    echo -e "${RED}Error: Git tidak ditemukan!${NC}"
    echo "Install Git terlebih dahulu:"
    echo "  Ubuntu/Debian: sudo apt install git"
    echo "  macOS: brew install git"
    exit 1
fi

# Define installation directory
INSTALL_DIR="$HOME/AIZU-CLI"
BIN_DIR="$HOME/bin"

echo -e "${YELLOW}📦 Menginstall AIZU-CLI...${NC}"

# Create bin directory if it doesn't exist
mkdir -p "$BIN_DIR"

# Check if AIZU-CLI already exists
if [ -d "$INSTALL_DIR" ]; then
    echo -e "${YELLOW}⚠️  AIZU-CLI sudah terinstall di $INSTALL_DIR${NC}"
    read -p "Update? [y/N]: " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}📦 Updating AIZU-CLI...${NC}"
        cd "$INSTALL_DIR"
        git pull
    else
        echo -e "${GREEN}✅ Menggunakan install yang sudah ada${NC}"
    fi
else
    echo -e "${YELLOW}📦 Cloning AIZU-CLI...${NC}"
    git clone https://github.com/ardhanaaizu/AIZU-CLI.git "$INSTALL_DIR"
fi

# Create aizu wrapper script
echo -e "${YELLOW}📝 Membuat aizu command...${NC}"
cat > "$BIN_DIR/aizu" << 'EOF'
#!/bin/bash
# AIZU-CLI Wrapper

AIZU_DIR="$HOME/AIZU-CLI"

if [ ! -d "$AIZU_DIR" ]; then
    echo "Error: AIZU-CLI tidak ditemukan di $AIZU_DIR"
    exit 1
fi

if [ ! -f "$AIZU_DIR/agent.py" ]; then
    echo "Error: agent.py tidak ditemukan"
    exit 1
fi

cd "$AIZU_DIR"
exec python3 agent.py "$@"
EOF

chmod +x "$BIN_DIR/aizu"

# Add to PATH if not already in PATH
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo -e "${YELLOW}📝 Menambahkan $BIN_DIR ke PATH...${NC}"

    # Detect shell
    SHELL_NAME=$(basename "$SHELL")

    case $SHELL_NAME in
        bash)
            RC_FILE="$HOME/.bashrc"
            ;;
        zsh)
            RC_FILE="$HOME/.zshrc"
            ;;
        fish)
            RC_FILE="$HOME/.config/fish/config.fish"
            ;;
        *)
            RC_FILE="$HOME/.profile"
            ;;
    esac

    # Add to PATH
    if [[ "$SHELL_NAME" == "fish" ]]; then
        echo "set -gx PATH $BIN_DIR \$PATH" >> "$RC_FILE"
    else
        echo "export PATH=\"\$HOME/bin:\$PATH\"" >> "$RC_FILE"
    fi

    echo -e "${GREEN}✅ PATH sudah ditambahkan ke $RC_FILE${NC}"
    echo -e "${YELLOW}💡 Restart terminal atau jalankan: source $RC_FILE${NC}"
fi

# Create default config if not exists
CONFIG_FILE="$INSTALL_DIR/config.json"
if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${YELLOW}📝 Membuat config default...${NC}"
    cat > "$CONFIG_FILE" << 'EOF'
{
  "backend": "groq",
  "api_key": "",
  "model": "llama-3.3-70b-versatile",
  "base_url": "https://api.groq.com/openai/v1",
  "mode": "chat",
  "saved_providers": {}
}
EOF
fi

echo ""
echo -e "${GREEN}✅ AIZU-CLI berhasil diinstall!${NC}"
echo ""
echo -e "${CYAN}Cara pakai:${NC}"
echo "  1. Buka terminal baru atau jalankan: source $RC_FILE"
echo "  2. Ketik: aizu"
echo "  3. Ikuti setup pertama kali (pilih backend & API key)"
echo ""
echo -e "${CYAN}Quick start:${NC}"
echo "  export AGENT_BACKEND=groq"
echo "  export AGENT_API_KEY='gsk_xxxxxxxx'  # dari console.groq.com"
echo "  aizu"
echo ""
echo -e "${CYAN}Dokumentasi:${NC}"
echo "  https://cli.aaizu.id"
echo ""
