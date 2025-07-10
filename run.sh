#!/bin/bash

echo "🚀 Starting MCP-Powered Gemini Chat..."
echo "======================================"

# Check if running in Codespace
if [ -n "$CODESPACES" ]; then
    echo "✅ Running in GitHub Codespace"
fi

# Source the cargo environment for uv/uvx
if [ -f "$HOME/.cargo/env" ]; then
    source $HOME/.cargo/env
fi

# Add local bin to PATH
export PATH="$HOME/.local/bin:$PATH"

echo "📦 Checking dependencies..."

# Check for uv/uvx
if ! command -v uvx &> /dev/null; then
    echo "⚠️  uvx not found in PATH. Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    source $HOME/.cargo/env
fi

# Install Python packages if needed
echo "🐍 Ensuring Python packages are installed..."
pip install --quiet --upgrade gradio google-generativeai mcp mcp-server-git

# Check for npx
if ! command -v npx &> /dev/null; then
    echo "📦 Installing npx..."
    npm install -g npx
fi

echo "✅ All dependencies ready!"
echo ""
echo "🌐 Starting Gradio interface..."
echo "======================================"

# Run with explicit Python to avoid any PATH issues
python3 app.py