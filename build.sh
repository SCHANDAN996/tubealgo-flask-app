#!/usr/bin/env bash
# exit on error
set -o errexit

echo "=== TubeAlgo Build Process Started ==="

# Step 1: Install Node.js dependencies
echo "📦 Installing Node.js dependencies..."
npm install

# Step 2: Build Tailwind CSS and JavaScript
echo "🎨 Building assets..."
npm run build

# Step 3: Install Python dependencies
echo "🐍 Installing Python dependencies..."
pip install -r requirements.txt

# Step 4 (Removed): Database migration is no longer needed here.

echo "🎉 Build process completed successfully!"