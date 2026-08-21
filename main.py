import uvicorn
from api.main import app, WEBAPP_HOST, WEBAPP_PORT

if __name__ == "__main__":
    uvicorn.run("api.main:app", host=WEBAPP_HOST, port=WEBAPP_PORT, reload=False)
