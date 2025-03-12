from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import time
import os
from collections import defaultdict
from starlette.middleware.base import BaseHTTPMiddleware
from jose import JWTError, jwt
from auth import SECRET_KEY, ALGORITHM  
import uvicorn
import importlib
import pkgutil
from routes import __name__ as routes_pkg_name
# from routes.dash import get_user_dashboard
from db import init_db
from routes import auth, users
from logging_config import logger  # Import the configured logger

app = FastAPI(title="Full Stack FastAPI App") # for dev
init_db()
# app = FastAPI(docs_url=None, redoc_url=None)  # Disable docs in production

logger.info("Application started")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Configure Jinja2 templates
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
def read_index(request: Request):
    logger.info("Rending index")
    return templates.TemplateResponse("index.html", {"request": request})


for _, module_name, _ in pkgutil.iter_modules(['routes']):
    module = importlib.import_module(f"routes.{module_name}")
    if hasattr(module, "router"):  # Only add modules that define 'router'
        app.include_router(module.router)


class AuthLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        token = request.headers.get("Authorization")
        user_email = "Anonymous"

        if token and token.startswith("Bearer "):
            token = token.split(" ")[1]
            try:
                payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
                # logger.info(f"Token payload: {payload}")
                user_email = payload.get("sub", "Unknown User")
            except JWTError:
                logger.warning(f"Invalid token detected for request: {request.url}")

        # Redirect unauthenticated users (API gets JSON, frontend gets redirect)
        if user_email == "Anonymous" and request.url.path.startswith("/users"):
            logger.info(f"Unauthenticated access attempt to {request.url}")
            
            # if "text/html" in request.headers.get("accept", ""):    
                # return RedirectResponse(url="/auth/login")
            process_time = time.time() - start_time
            logger.info(f"Response: ERROR | Time taken: {process_time:.4f} sec")
            return JSONResponse(
                content={"detail": "Unauthorized. Please log in", "status" : "Error"},
                status_code=401
            )

        logger.info(f"User: {user_email} | Request: {request.method} {request.url}")
        request.state.user_email = user_email
        response = await call_next(request)
        process_time = time.time() - start_time
        logger.info(f"Response: {response.status_code} | Time taken: {process_time:.4f} sec")
        return response

RATE_LIMIT = 5  
TIME_WINDOW = 60  # 1 minute instead of 5 minutes

request_counts = defaultdict(list)  # Safer way to handle missing keys

class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host
        current_time = time.time()

        # Remove outdated requests
        request_counts[client_ip] = [t for t in request_counts[client_ip] if current_time - t < TIME_WINDOW]

        if len(request_counts[client_ip]) >= RATE_LIMIT:
            logger.warning(f"Rate limit exceeded for IP: {client_ip}")
            return JSONResponse(
                content={"detail": "Too many requests. Try again later.", "status":"Error"},
                status_code=429
            )

        request_counts[client_ip].append(current_time)
        return await call_next(request)

app.add_middleware(AuthLoggingMiddleware)  
app.add_middleware(RateLimitMiddleware)  

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False, server_header=False) #true for dev env
