import os
import pymongo

_MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
_MONGO_DB = os.getenv("MONGO_DB", "nanogaze_mlops")


def _col():
    client = pymongo.MongoClient(_MONGO_URI, serverSelectionTimeoutMS=5000)
    return client, client[_MONGO_DB]["config"]


def get(key: str, default: str = "") -> str:
    try:
        client, col = _col()
        doc = col.find_one({"key": key}, {"_id": 0, "value": 1})
        client.close()
        return doc["value"] if doc else default
    except Exception:
        return default


def save(key: str, value: str) -> None:
    client, col = _col()
    col.update_one({"key": key}, {"$set": {"value": value}}, upsert=True)
    client.close()
