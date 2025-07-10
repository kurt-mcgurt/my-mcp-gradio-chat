#!/usr/bin/env bash
set -euo pipefail

echo "🔧 Setting up MCP development environment..."

# 1) Install uv only if it’s not already on PATH (feature image or cached)
if ! command -v uv &>/dev/null; then
  echo "📦 Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# 2) Install Python deps with uv for speed & lock-file caching
echo "🐍 Installing Python packages..."
uv pip install --upgrade pip
uv pip install gradio google-genai mcp mcp-server-git

# 3) Nothing else to do: Node 20 already includes npx
echo "✅ Setup complete!"