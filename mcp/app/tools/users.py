"""MCP tools for user management."""

import logging
from datetime import datetime, timezone

from fastmcp import FastMCP

from app.services.api_client import client
from app.services.exceptions import OpenWearablesError

logger = logging.getLogger(__name__)

# Create router for user-related tools
users_router = FastMCP(name="Users Tools")


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@users_router.tool
async def get_users(search: str | None = None, limit: int = 10) -> dict:
    """
    Get users accessible via the configured API key.

    Use this tool to discover available Open Wearables users before querying their health data.
    The API key determines which users are visible (personal, team, or enterprise scope).

    Args:
        search: Optional search term to filter users by first name, last name, or email.
                Example: "John" will match users with "John" in their name.
        limit: Maximum number of users to return (default: 10).
               Use the 'search' parameter to find specific users in large organizations
               rather than increasing this limit.

    Returns:
        A dictionary containing:
        - users: List of user objects with id, first_name, last_name, email (up to 'limit' users)
        - total: Total number of users matching the query (may be greater than returned users)

    Example response:
        {
            "users": [
                {"id": "uuid-1", "first_name": "John", "last_name": "Doe", "email": "john@example.com"},
                {"id": "uuid-2", "first_name": "Jane", "last_name": "Smith", "email": "jane@example.com"}
            ],
            "total": 2
        }

    Notes for LLMs:
        - Call this tool first if you don't know the user's ID
        - Use the 'search' parameter to filter by name if the user mentions a specific person
        - The 'id' field is a UUID that can be used with other tools like get_sleep_summary, get_workout_events
        - If only ONE user is returned: use that user automatically (this indicates a personal API key)
        - If MULTIPLE users are returned and user says "my/me": ask which user they mean
        - If MULTIPLE users are returned with a name hint: match by name or use 'search'
        - If 'total' exceeds the number of returned users, use 'search' to narrow results
    """
    try:
        response = await client.get_users(search=search, limit=limit)

        # Extract user data from paginated response
        users = response.get("items", [])

        return {
            "users": [
                {
                    "id": str(user.get("id")),
                    "first_name": user.get("first_name"),
                    "last_name": user.get("last_name"),
                    "email": user.get("email"),
                }
                for user in users
            ],
            "total": response.get("total", len(users)),
        }

    except OpenWearablesError as e:
        logger.error(f"API error in get_users: {e}")
        return {"error": str(e), "users": [], "total": 0}
    except Exception as e:
        logger.exception(f"Unexpected error in get_users: {e}")
        return {"error": f"Failed to fetch users: {e}", "users": [], "total": 0}


@users_router.tool
async def get_data_freshness(user_id: str, stale_after_hours: int = 6) -> dict:
    """Check source recency and whether a device-backed bridge is stale.

    Call this before making claims that depend on current-day data. In particular,
    Apple Health is bridged by an iPhone and can become stale when iOS has not
    woken the Bionic app. Cloud provider timestamps are returned for context but
    inactivity alone does not mark an event-driven cloud connection stale. A stale
    device bridge means the available health records may be incomplete; state that
    limitation instead of treating missing data as zero.

    Args:
        user_id: Open Wearables user UUID.
        stale_after_hours: Age at which an active source is considered stale (default 6).
    """
    try:
        connections = await client.get_connections(user_id)
        now = datetime.now(timezone.utc)
        sources: list[dict] = []
        for connection in connections:
            if connection.get("status") != "active":
                continue
            last_synced_at = _parse_timestamp(connection.get("last_synced_at"))
            age_hours = None if last_synced_at is None else (now - last_synced_at).total_seconds() / 3600
            is_device_bridge = connection.get("provider") in {"apple", "samsung", "google"}
            is_stale = is_device_bridge and (age_hours is None or age_hours > stale_after_hours)
            sources.append(
                {
                    "provider": connection.get("provider"),
                    "last_synced_at": connection.get("last_synced_at"),
                    "age_hours": None if age_hours is None else round(max(age_hours, 0), 2),
                    "is_stale": is_stale,
                    "delivery": "device_bridge" if is_device_bridge else "provider_connection",
                }
            )
        return {
            "checked_at": now.isoformat(),
            "stale_after_hours": stale_after_hours,
            "is_stale": any(source["is_stale"] for source in sources),
            "sources": sources,
        }
    except OpenWearablesError as exc:
        logger.error("API error in get_data_freshness: %s", exc)
        return {"error": str(exc), "sources": []}
