#!/bin/bash
# start_services.sh

echo "Starting FastAPI Backend (app.py) on port 8088..."
nohup .venv/bin/python app.py > backend.log 2>&1 &
BACKEND_PID=$!
echo "Backend started with PID: $BACKEND_PID"

# Wait a few seconds for backend to start up
sleep 3

echo "Starting Streamlit Frontend (app_ui.py) on port 8501..."
nohup .venv/bin/streamlit run app_ui.py --server.port 8501 > frontend.log 2>&1 &
FRONTEND_PID=$!
echo "Frontend started with PID: $FRONTEND_PID"

echo "Services initialized."
echo "Backend logs: tail -f backend.log"
echo "Frontend logs: tail -f frontend.log"
