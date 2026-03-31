"""MongoDB persistence for connection profiles."""

from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorDatabase

from src.modules.profiles.domain.models import ConnectionProfile

_COL_PROFILES = "connection_profiles"


def _to_mongo(doc: dict[str, object]) -> dict[str, object]:
    d = dict(doc)
    d["_id"] = d.pop("id")
    return d


def _from_mongo(doc: dict[str, object] | None) -> dict[str, object] | None:
    if doc is None:
        return None
    d = dict(doc)
    d["id"] = str(d.pop("_id"))
    return d


async def insert_profile(db: AsyncIOMotorDatabase, profile: ConnectionProfile) -> None:
    raw: dict[str, object] = dict(profile.model_dump(mode="json"))
    await db[_COL_PROFILES].insert_one(_to_mongo(raw))


async def get_profile(db: AsyncIOMotorDatabase, profile_id: str) -> ConnectionProfile | None:
    doc = await db[_COL_PROFILES].find_one({"_id": profile_id})
    raw = _from_mongo(doc)
    return ConnectionProfile.model_validate(raw) if raw else None


async def list_profiles(db: AsyncIOMotorDatabase) -> list[ConnectionProfile]:
    cursor = db[_COL_PROFILES].find().sort("created_at", 1)
    docs = await cursor.to_list(length=None)
    return [ConnectionProfile.model_validate(_from_mongo(d)) for d in docs]


async def update_profile_doc(db: AsyncIOMotorDatabase, profile: ConnectionProfile) -> None:
    raw: dict[str, object] = dict(profile.model_dump(mode="json"))
    await db[_COL_PROFILES].replace_one({"_id": profile.id}, _to_mongo(raw))


async def delete_profile_doc(db: AsyncIOMotorDatabase, profile_id: str) -> bool:
    result = await db[_COL_PROFILES].delete_one({"_id": profile_id})
    return result.deleted_count > 0


async def find_active_profile(db: AsyncIOMotorDatabase) -> ConnectionProfile | None:
    doc = await db[_COL_PROFILES].find_one({"is_active": True})
    raw = _from_mongo(doc)
    return ConnectionProfile.model_validate(raw) if raw else None


async def set_all_profiles_inactive(db: AsyncIOMotorDatabase) -> None:
    await db[_COL_PROFILES].update_many({}, {"$set": {"is_active": False}})


async def count_profiles(db: AsyncIOMotorDatabase) -> int:
    return await db[_COL_PROFILES].count_documents({})


async def activate_profile_by_id(db: AsyncIOMotorDatabase, profile_id: str) -> None:
    """Mark all profiles inactive, then set the given profile active."""
    await set_all_profiles_inactive(db)
    await db[_COL_PROFILES].update_one({"_id": profile_id}, {"$set": {"is_active": True}})
