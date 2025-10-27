#!/usr/bin/env python3
"""
Find all imports in TubeAlgo project
Usage: python find_imports.py
"""

import os
import re
from pathlib import Path

def find_all_imports(directory):
    """Find all import statements in Python files"""
    imports = set()
    
    # Walk through all Python files
    for root, dirs, files in os.walk(directory):
        # Skip virtual environments and cache
        if 'venv' in root or '__pycache__' in root or '.venv' in root:
            continue
            
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                        
                        # Find all import statements
                        # Pattern 1: import module
                        pattern1 = r'^import\s+([a-zA-Z_][a-zA-Z0-9_]*)'
                        # Pattern 2: from module import something
                        pattern2 = r'^from\s+([a-zA-Z_][a-zA-Z0-9_]*)'
                        
                        for line in content.split('\n'):
                            line = line.strip()
                            
                            # Match import statements
                            match1 = re.match(pattern1, line)
                            match2 = re.match(pattern2, line)
                            
                            if match1:
                                imports.add(match1.group(1))
                            elif match2:
                                imports.add(match2.group(1))
                                
                except Exception as e:
                    print(f"Error reading {filepath}: {e}")
    
    return sorted(imports)

def get_package_name(module):
    """Convert module name to package name"""
    mapping = {
        'flask': 'Flask',
        'flask_sqlalchemy': 'Flask-SQLAlchemy',
        'flask_login': 'Flask-Login',
        'flask_wtf': 'Flask-WTF',
        'flask_migrate': 'Flask-Migrate',
        'flask_limiter': 'Flask-Limiter',
        'flask_cors': 'Flask-CORS',
        'wtforms': 'WTForms',
        'PIL': 'Pillow',
        'dateutil': 'python-dateutil',
        'dotenv': 'python-dotenv',
        'bs4': 'beautifulsoup4',
        'cv2': 'opencv-python',
    }
    
    return mapping.get(module, module)

if __name__ == '__main__':
    print("🔍 Finding all imports in TubeAlgo project...\n")
    
    # Get project directory (assuming script is in root)
    project_dir = os.getcwd()
    
    # Find all imports
    imports = find_all_imports(project_dir)
    
    # Standard library modules (don't need to be installed)
    stdlib = {
        'os', 'sys', 're', 'json', 'time', 'datetime', 'logging',
        'hashlib', 'uuid', 'random', 'threading', 'collections',
        'functools', 'itertools', 'pathlib', 'typing', 'base64',
        'urllib', 'http', 'email', 'socket', 'ssl', 'io', 'csv',
        'string', 'math', 'decimal', 'enum', 'abc', 'warnings',
    }
    
    # Filter out standard library
    external_imports = [imp for imp in imports if imp not in stdlib]
    
    print(f"📦 Found {len(external_imports)} external packages:\n")
    
    packages = []
    for imp in external_imports:
        package = get_package_name(imp)
        packages.append(package)
        print(f"   - {imp} → {package}")
    
    print("\n" + "="*50)
    print("\n📝 Suggested requirements.txt:\n")
    
    # Remove duplicates and sort
    unique_packages = sorted(set(packages))
    
    for package in unique_packages:
        print(package)
    
    print("\n✅ Done!")
