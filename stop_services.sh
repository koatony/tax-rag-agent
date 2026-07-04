#!/bin/bash
# stop_services.sh

echo "Stopping FastAPI Backend (app.py) and Streamlit Frontend (app_ui.py)..."
pkill -f "python app.py"
pkill -f "streamlit run app_ui.py"
echo "Services stopped."
