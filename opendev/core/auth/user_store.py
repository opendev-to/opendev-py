"""File-based user store for authentication."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Dict, Optional

from opendev.models.user import User


class UserStore:
    """Simple JSON-backed store for user accounts."""

    def __init__(self, storage_dir: Path) -> None:
        self.storage_dir = storage_dir
        self.users_file = storage_dir / "users.json"
        self._lock = Lock()
        self._users: Dict[str, User] = {}
        self._load()

    def _load(self) -> None:
        if not self.users_file.exists():
            self.users_file.parent.mkdir(parents=True, exist_ok=True)
            self.users_file.write_text("{}", encoding="utf-8")
        data = json.loads(self.users_file.read_text(encoding="utf-8"))
        self._users = {username: User(**payload) for username, payload in data.items()}

    def _persist(self) -> None:
        serialized = {username: user.model_dump() for username, user in self._users.items()}
        with self.users_file.open("w", encoding="utf-8") as fh:
            json.dump(serialized, fh, indent=2, default=str)

    def get_by_username(self, username: str) -> Optional[User]:
        with self._lock:
            return self._users.get(username)

    def get_by_id(self, user_id: str) -> Optional[User]:
        with self._lock:
            for user in self._users.values():
                if str(user.id) == user_id:
                    return user
            return None

    def create_user(self, username: str, password_hash: str, *, email: Optional[str] = None) -> User:
        with self._lock:
            if username in self._users:
                raise ValueError("User already exists")
            user = User(username=username, password_hash=password_hash, email=email)
            self._users[username] = user
            self._persist()
            return user

    def update_user(self, user: User) -> None:
        with self._lock:
            self._users[user.username] = user
            self._persist()
