#!/bin/bash

# =====================================================================
# Launcher Script for macOS and Linux
# Author: Mudrikul Hikam
# Last Updated: January 10, 2026
# 
# This script performs the following tasks:
# 1. If Python folder exists, directly runs main.py
# 2. If Python folder doesn't exist:
#    - Downloads Python 3.12 (via pyenv or system package manager)
#    - Sets up virtual environment
#    - Installs required packages from requirements.txt
#    - Runs main.py
# =====================================================================

# =====================================================================
# The MIT License (MIT)

# Copyright (c) 2025 Mudrikul Hikam, Desainia Studio

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
# =====================================================================

set -e

# Get the directory where this script is located
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Detect OS
OS_TYPE="$(uname -s)"
case "$OS_TYPE" in
    Linux*)     PLATFORM="Linux";;
    Darwin*)    PLATFORM="macOS";;
    *)          PLATFORM="Unknown";;
esac

echo "=========================================="
echo "SotongHD Launcher - $PLATFORM"
echo "=========================================="

# Define paths based on platform
if [ "$PLATFORM" = "macOS" ]; then
    PYTHON_DIR="$BASE_DIR/python/macOS"
else
    PYTHON_DIR="$BASE_DIR/python/Linux"
fi

VENV_DIR="$PYTHON_DIR/venv"
MAIN_PY="$BASE_DIR/main.py"
REQUIREMENTS_FILE="$BASE_DIR/requirements.txt"

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to find Python 3.10+ executable
find_python() {
    # Try common Python 3 executables
    for py in python3.12 python3.11 python3.10 python3; do
        if command_exists "$py"; then
            # Check version is at least 3.10
            version=$("$py" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
            major=$(echo "$version" | cut -d. -f1)
            minor=$(echo "$version" | cut -d. -f2)
            if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
                echo "$py"
                return 0
            fi
        fi
    done
    return 1
}

# Function to install Python on macOS
install_python_macos() {
    echo "Python 3.10+ not found. Attempting to install..."
    
    # Check if Homebrew is installed
    if command_exists brew; then
        echo "Installing Python via Homebrew..."
        brew install python@3.12
        return 0
    fi
    
    echo ""
    echo "ERROR: Homebrew not found."
    echo "Please install Python 3.10+ manually:"
    echo "  1. Install Homebrew: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
    echo "  2. Then run: brew install python@3.12"
    echo ""
    echo "Or download Python directly from: https://www.python.org/downloads/"
    return 1
}

# Function to install Python on Linux
install_python_linux() {
    echo "Python 3.10+ not found. Attempting to install..."
    
    # Detect package manager
    if command_exists apt-get; then
        echo "Installing Python via apt..."
        sudo apt-get update
        sudo apt-get install -y python3 python3-pip python3-venv
        return 0
    elif command_exists dnf; then
        echo "Installing Python via dnf..."
        sudo dnf install -y python3 python3-pip
        return 0
    elif command_exists yum; then
        echo "Installing Python via yum..."
        sudo yum install -y python3 python3-pip
        return 0
    elif command_exists pacman; then
        echo "Installing Python via pacman..."
        sudo pacman -S --noconfirm python python-pip
        return 0
    fi
    
    echo ""
    echo "ERROR: Could not detect package manager."
    echo "Please install Python 3.10+ manually using your system's package manager."
    echo "Or download from: https://www.python.org/downloads/"
    return 1
}

# =====================================================================
# Check if virtual environment exists
# =====================================================================
if [ -d "$VENV_DIR" ]; then
    echo "Virtual environment found at: $VENV_DIR"
    echo "Activating virtual environment..."
    
    source "$VENV_DIR/bin/activate"
    
    # Check for requirements and install if needed
    if [ -f "$REQUIREMENTS_FILE" ]; then
        echo "Checking/installing requirements..."
        pip install -r "$REQUIREMENTS_FILE" --quiet
    fi
    
    echo "Running SotongHD..."
    python "$MAIN_PY"
    exit 0
fi

# =====================================================================
# Virtual environment doesn't exist - set up from scratch
# =====================================================================
echo "Virtual environment not found. Setting up environment..."

# Find or install Python
PYTHON_EXE=$(find_python)

if [ -z "$PYTHON_EXE" ]; then
    echo "Python 3.10+ not found on system."
    
    if [ "$PLATFORM" = "macOS" ]; then
        install_python_macos || exit 1
    else
        install_python_linux || exit 1
    fi
    
    # Try to find Python again after installation
    PYTHON_EXE=$(find_python)
    if [ -z "$PYTHON_EXE" ]; then
        echo "ERROR: Failed to find Python after installation. Please install manually."
        exit 1
    fi
fi

echo "Using Python: $PYTHON_EXE"
$PYTHON_EXE --version

# Create the python directory structure
echo "Creating Python directory structure..."
mkdir -p "$PYTHON_DIR"

# Create virtual environment
echo "Creating virtual environment..."
$PYTHON_EXE -m venv "$VENV_DIR"

# Activate virtual environment
echo "Activating virtual environment..."
source "$VENV_DIR/bin/activate"

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip --quiet

# Install requirements
if [ -f "$REQUIREMENTS_FILE" ]; then
    echo "Installing required packages from requirements.txt..."
    pip install -r "$REQUIREMENTS_FILE"
else
    echo "Warning: requirements.txt not found. Skipping package installation."
fi

# =====================================================================
# Launch the application
# =====================================================================
echo ""
echo "=========================================="
echo "Setup complete. Running SotongHD..."
echo "=========================================="
python "$MAIN_PY"
