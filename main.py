import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import time
from models import User, StatementPeriod, AMC, Folio, Scheme, Valuation, Transaction, SchemeNavHistory, SchemeMaster
from fastapi.exceptions import RequestValidationError
from collections import defaultdict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError, jwt
from auth import SECRET_KEY, ALGORITHM, create_access_token
import uvicorn
import importlib
import pkgutil
from routes import __name__ as routes_pkg_name
from db import redis_client, init_redis, init_db
# from routes.dash import get_user_dashboard
# from routes import auth, users
from logging_config import logger  # Import the configured logger

app = FastAPI(title="Full Stack FastAPI App") # for dev
# app = FastAPI(docs_url=None, redoc_url=None)  # Disable docs in production

init_db()
init_redis()
logger.info("Application started")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


for _, module_name, _ in pkgutil.iter_modules(['routes']):
    module = importlib.import_module(f"routes.{module_name}")
    if hasattr(module, "router"):  # Only add modules that define 'router'
        app.include_router(module.router)


class AuthLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        logger = logging.getLogger("ALM")
        start_time = time.time()
        token = request.headers.get("Authorization")
        user_email = "Anonymous"

        if token and token.startswith("Bearer "):
            token = token.split(" ")[1]
            if redis_client.exists(f"blacklist:{token}"):  # Check if token is revoked
                logger.warning(f"Revoked token used by {request.client.host}")
                return JSONResponse(
                    content={"detail": "Token has been revoked. Please log in again.", "status": "Error"},
                    status_code=401
                )
            try:
                payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
                # logger.info(f"Token payload: {payload}")
                user_email = payload.get("sub", "Unknown User")
            except JWTError:
                logger.warning(f"Invalid token detected for request: {request.url}")

        # Redirect unauthenticated users (API gets JSON, frontend gets redirect)
        if user_email == "Anonymous" and request.url.path.startswith("/users"):
            logger.info(f"Unauthenticated access attempt to {request.url}")
            process_time = time.time() - start_time
            logger.info(f"Response: Time taken: {process_time:.4f} sec")
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
        logger = logging.getLogger("RLM")
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

class ExtendTokenMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        logger = logging.getLogger("ETM")
        token = request.headers.get("Authorization")
        if token and token.startswith("Bearer "):
            token = token.split(" ")[1]
            try:
                if redis_client.exists(f"blacklist:{token}"):
                    logger.warning(f"Attempted to extend revoked token for {request.client.host}")
                    return await call_next(request)
                payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
                exp_time = payload.get("exp")
                current_time = int(time.time())

                # Extend token only if it's about to expire (within 5 minutes)
                if exp_time - current_time < 180:
                    user_email = payload.get("sub", "Unknown User")
                    logger.info(f"Extending Token Time for {request.client.host} user:{user_email}")
                    new_token = create_access_token(data={"sub": payload["sub"]})
                    request.state.new_token = new_token  # Store new token in request state

            except JWTError:
                pass  # Ignore invalid tokens
        response = await call_next(request)
        if hasattr(request.state, "new_token"):
            response.headers["X-New-Token"] = request.state.new_token  # Send new token
        return response


app.add_middleware(AuthLoggingMiddleware)  
app.add_middleware(RateLimitMiddleware)
app.add_middleware(ExtendTokenMiddleware)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["yourdomain.com", "sub.yourdomain.com", "localhost", "127.0.0.1", "*"],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://yourfrontend.com", "https://localhost", "https://localhost:3000"],  # Adjust for your frontend
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods (GET, POST, etc.)
    allow_headers=["*"],  # Allow all headers
)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, server_header=False) #true for dev env
