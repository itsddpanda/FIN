# File: tests/test_main.py
# A sample test file using pytest and FastAPI's TestClient.
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_register_and_login():
    # Test user registration
    register_response = client.post(
        "/auth/register",
        json={"email": "test@example.com", "password": "testpassword"}
    )
    assert register_response.status_code == 200, register_response.text
    user_data = register_response.json()
    assert "email" in user_data

    # Test user login
    login_response = client.post(
        "/auth/login",
        data={"username": "test@example.com", "password": "testpassword"}
    )
    assert login_response.status_code == 200, login_response.text
    token_data = login_response.json()
    assert "access_token" in token_data
