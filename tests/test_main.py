# File: tests/test_main.py
# A sample test file using pytest and FastAPI's TestClient.
import os

# Ensure ALLOWED_HOSTS includes testserver BEFORE importing main
os.environ["ALLOWED_HOSTS"] = "localhost,127.0.0.1,testserver"

from fastapi.testclient import TestClient
from main import app
from db import get_db
from unittest.mock import MagicMock
from models import User
from auth import get_password_hash

client = TestClient(app)

def test_register_and_login():
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db

    # --- Test Registration ---
    # Scenario: User does not exist
    # db.query(User).filter(...).first() should return None
    mock_db.query.return_value.filter.return_value.first.return_value = None

    # Mock refresh to simulate DB assigning ID (optional, but good)
    def mock_refresh(instance):
        instance.user_id = "test-uuid"
    mock_db.refresh.side_effect = mock_refresh

    register_response = client.post(
        "/auth/register",
        json={"email": "test@example.com", "password": "testpassword"}
    )
    assert register_response.status_code == 200, register_response.text
    user_data = register_response.json()
    assert "email" in user_data
    assert user_data["email"] == "test@example.com"

    # Verify DB interactions
    assert mock_db.add.called
    assert mock_db.commit.called

    # --- Test Login ---
    # Scenario: User exists and password matches
    hashed_pw = get_password_hash("testpassword")
    mock_user = User(email="test@example.com", hashed_password=hashed_pw, is_active=True)

    # Reset mock to return this user
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user

    login_response = client.post(
        "/auth/login",
        data={"username": "test@example.com", "password": "testpassword"}
    )
    assert login_response.status_code == 200, login_response.text
    token_data = login_response.json()
    assert "access_token" in token_data
