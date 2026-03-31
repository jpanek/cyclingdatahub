#!/bin/bash
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🚀 Starting Jupyter Lab in $PROJECT_DIR..."

source "$PROJECT_DIR/venv/bin/activate"

export PYTHONPATH="$PROJECT_DIR:$PYTHONPATH"

jupyter-lab --ServerApp.root_dir="$PROJECT_DIR"