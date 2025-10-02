# Filepath: build.sh

#!/usr/bin/env bash
# exit on error
set -o errexit

echo "=== TubeAlgo Build Process Started ==="

# स्टेप 1: Node.js निर्भरताएँ इंस्टॉल करें
echo "📦 Installing Node.js dependencies..."
npm install

# स्टेप 2: Tailwind CSS को चलाकर output.css बनाएँ
echo "🎨 Building Tailwind CSS..."
npx tailwindcss -i ./static/css/main.css -o ./static/css/output.css --minify

# स्टेप 3: CSS फाइल का existence check
if [ -f "./static/css/output.css" ]; then
    echo "✅ Tailwind CSS built successfully!"
else
    echo "❌ ERROR: Tailwind CSS build failed - output.css not found!"
    exit 1
fi

# स्टेप 4: Python निर्भरताएँ इंस्टॉल करें
echo "🐍 Installing Python dependencies..."
pip install -r requirements.txt

echo "🎉 Build process completed successfully!"

