#!/bin/bash
set -e

echo "🔧 Setting up MCP development environment..."

# Install uv
echo "📦 Installing uv..."
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.cargo/env

# Add to PATH permanently
echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> ~/.bashrc

# Install Python packages
echo "🐍 Installing Python packages..."
pip install --upgrade pip
pip install gradio google-generativeai mcp mcp-server-git

# Ensure npx is available
echo "📦 Ensuring npx is available..."
npm install -g npx@latest

echo "✅ Setup complete!"