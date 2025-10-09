#!/usr/bin/env bash
# exit on error
set -o errexit

echo "=== TubeAlgo Build Process Started ==="

# Step 1: Install Node.js dependencies
echo "📦 Installing Node.js dependencies..."
npm install

# Step 2: Build Tailwind CSS
echo "🎨 Building Tailwind CSS..."
npx tailwindcss -i ./static/css/main.css -o ./static/css/output.css --minify

# Step 3: Install Python dependencies
echo "🐍 Installing Python dependencies..."
pip install -r requirements.txt

# Step 4: Run database migrations
echo "🔄 Running database migrations..."
flask db upgrade

echo "🎉 Build process completed successfully!"