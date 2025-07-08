#!/bin/bash

echo "🚀 Starting MCP-Powered Gemini Chat..."
echo "📦 Installing any missing dependencies..."

# Install Python packages if needed
pip install gradio google-generativeai mcp mcp-server-git

# Install uv if not already installed
if ! command -v uv &> /dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    source $HOME/.cargo/env
fi

# Install uvx is included with uv, no separate installation needed

# Make sure npx is available
npm install -g npx

echo "✅ Dependencies ready!"
echo "🌐 Starting Gradio interface..."

python app.py