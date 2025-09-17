from __future__ import annotations

from .storage import load_users_from_disk

user_profiles = load_users_from_disk()
drafts: dict = {}
driver_onboarding: dict = {}
orders: dict = {}
driver_links: dict = {}
pending_invites: dict = {}
subscriptions: dict = {}
trial_members: dict[int, dict] = {}

__all__ = [
    "user_profiles",
    "drafts",
    "driver_onboarding",
    "orders",
    "driver_links",
    "pending_invites",
    "subscriptions",
    "trial_members",
]
