#!/bin/bash

# SQL-Chat Installation Script
# This script sets up the SQL-Chat environment

set -e  # Exit on any error

echo "🚀 SQL-Chat Installation Script"
echo "================================"

# Check Python version
echo "📋 Checking Python version..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
required_version="3.8.0"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" = "$required_version" ]; then
    echo "✅ Python $python_version is compatible"
else
    echo "❌ Python $python_version is not compatible. Please install Python >= 3.8"
    exit 1
fi

# Create virtual environment
echo "🐍 Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✅ Virtual environment created"
else
    echo "📁 Virtual environment already exists"
fi

# Activate virtual environment
echo "🔄 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "⬆️ Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "📦 Installing dependencies..."
if [ "$1" = "--gpu" ]; then
    echo "🖥️ Installing with GPU support..."
    pip install -e ".[gpu,dev]"
elif [ "$1" = "--dev" ]; then
    echo "🔧 Installing development version..."
    pip install -e ".[dev]"
else
    echo "💾 Installing basic version..."
    pip install -r requirements.txt
fi

# Create .env file if it doesn't exist
echo "⚙️ Setting up environment configuration..."
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "✅ .env file created from template"
        echo "⚠️  Please edit .env file with your actual credentials"
    else
        echo "⚠️  .env.example not found. Please create .env manually"
    fi
else
    echo "📁 .env file already exists"
fi

# Create necessary directories
echo "📁 Creating necessary directories..."
mkdir -p logs
mkdir -p rag_file
mkdir -p model
echo "✅ Directories created"

# Installation complete
echo ""
echo "🎉 Installation completed successfully!"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your credentials:"
echo "   vim .env"
echo ""
echo "2. Initialize DataHub sync:"
echo "   python datahub_sync.py --mode cold"
echo ""
echo "3. Start the server:"
echo "   python llm_rest_api.py --port 54292"
echo ""
echo "4. Test the API:"
echo "   curl -X POST http://localhost:54292/query \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"query\": \"Show me all tables\", \"chatId\": 1}'"
echo ""
echo "For development, activate the virtual environment:"
echo "   source venv/bin/activate"
echo ""
echo "Happy coding! 🚀" 