import uvicorn
import sys
import os

# Add current directory to path so app.main is findable
sys.path.append(os.path.join(os.getcwd(), 'backend'))

if __name__ == "__main__":
    print("Starting OCEAN 3D Backend on http://localhost:8000")
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, log_level="info")
