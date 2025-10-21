#!/usr/bin/env bash
# Debug script to check environment

echo "=== Environment Debug ==="
echo "Current directory: $(pwd)"
echo "PATH: $PATH"
echo ""

echo "=== Python Detection ==="
for cmd in python python3 py; do
    if command -v "$cmd" >/dev/null 2>&1; then
        echo "✅ Found: $cmd at $(which $cmd)"
        $cmd --version
    else
        echo "❌ Not found: $cmd"
    fi
done
echo ""

echo "=== Other Dependencies ==="
for cmd in aws jq curl; do
    if command -v "$cmd" >/dev/null 2>&1; then
        echo "✅ Found: $cmd at $(which $cmd)"
    else
        echo "❌ Not found: $cmd"
    fi
done
echo ""

echo "=== Test Python Execution ==="
python -c "import sys; print('Python works:', sys.version)" 2>/dev/null || echo "❌ python command failed"
python3 -c "import sys; print('Python3 works:', sys.version)" 2>/dev/null || echo "❌ python3 command failed"
py -c "import sys; print('py works:', sys.version)" 2>/dev/null || echo "❌ py command failed"
