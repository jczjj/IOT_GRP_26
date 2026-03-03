#!/bin/bash
# Helper script to run the Flask server with the virtual environment

cd "/home/yztan120/Application Server"
source venv/bin/activate

# Initialize database if it doesn't exist
if [ ! -f "elderly_monitoring.db" ]; then
    echo "Database not found. Initializing..."
    python init_db.py
    echo ""
fi

# Start the server
python app.py
