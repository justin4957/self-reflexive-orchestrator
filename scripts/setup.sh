#!/bin/bash
# Setup script for self-reflexive-orchestrator

set -e

echo "🤖 Self-Reflexive Coding Orchestrator - Setup"
echo "=============================================="
echo ""

# Check Python version
echo "Checking Python version..."
python_version=$(python3 --version 2>&1 | grep -oP '\d+\.\d+' | head -1)
required_version="3.9"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "❌ Error: Python $required_version or higher is required (found $python_version)"
    exit 1
fi
echo "✅ Python $python_version detected"
echo ""

# Create virtual environment
echo "Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✅ Virtual environment created"
else
    echo "⚠️  Virtual environment already exists"
fi
echo ""

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate
echo "✅ Virtual environment activated"
echo ""

# Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
echo "✅ Dependencies installed"
echo ""

# Create directories
echo "Creating directories..."
mkdir -p logs
mkdir -p workspace
mkdir -p config
echo "✅ Directories created"
echo ""

# Copy config if needed
if [ ! -f "config/orchestrator-config.yaml" ]; then
    echo "Creating configuration file..."
    cp config/orchestrator-config.yaml.example config/orchestrator-config.yaml
    echo "✅ Configuration file created at config/orchestrator-config.yaml"
    echo "⚠️  Please edit this file with your settings!"
else
    echo "⚠️  Configuration file already exists"
fi
echo ""

# Copy .env if needed
if [ ! -f ".env" ]; then
    echo "Creating .env file..."
    cp .env.example .env
    echo "✅ .env file created"
    echo "⚠️  Please edit .env with your API keys!"
else
    echo "⚠️  .env file already exists"
fi
echo ""

# Run tests
echo "Running tests..."
if pytest -q; then
    echo "✅ All tests passed"
else
    echo "⚠️  Some tests failed (this is normal if config is incomplete)"
fi
echo ""

# Final instructions
echo "=============================================="
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit config/orchestrator-config.yaml with your settings"
echo "2. Edit .env with your API keys (GITHUB_TOKEN and ANTHROPIC_API_KEY)"
echo "3. Validate config: python -m src.cli validate-config"
echo "4. Start orchestrator: python -m src.cli start --mode supervised"
echo ""
echo "For help: python -m src.cli --help"
echo "=============================================="
