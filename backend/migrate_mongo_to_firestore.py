"""One-time copy of the old MongoDB data into Firestore.

    pip install pymongo                                    (migration-only dependency)
    python migrate_mongo_to_firestore.py --dry-run         # read MongoDB, write nothing
    python migrate_mongo_to_firestore.py --dry-run --limit 5
    python migrate_mongo_to_firestore.py                   # copy

Reads MONGO_URI / MONGO_DB (defaults mongodb://127.0.0.1:27017 and brandora, or
--mongo-uri / --mongo-db) and writes with the same Application Default
Credentials and project id as the app. A --limit applies independently to each
source collection. Safe to re-run: every record goes to a fixed document id,
so writes use set/upsert and a second run does not create duplicates.

What changes on the way:
  - An ObjectId becomes its hex string, and a record's _id becomes its document
    id, so the user ids in connected_accounts.json and every user_id field still match.
  - Dates become timezone-aware UTC.
  - Each user also gets a user_emails entry (one account per email).
  - usage_cycles, analysis_cache, brand_personas and responder_events move to
    the fixed ids the app now derives; notification links to events follow.
  - responder_events.raw and analysis_cache.payload are stored as JSON text;
    a held reply lock is dropped; events without a `simulated` flag get False.
  - TTL collections get expires_at.
  - password_resets and oauth_states are not copied: they expire within minutes.

Collections no current code uses (left by the earlier Mongoose version, such as
businesses, brandkits, competitors, marketingplans, posts, history) are only
copied with --include-legacy, as they are, under the same names.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

try:
    from bson import Decimal128, ObjectId
    from pymongo import MongoClient
except ImportError:
    sys.exit("This script reads the old database: run `pip install pymongo` first.")

import firebase_db  # noqa: E402

SKIPPED = ("password_resets", "oauth_states")


def plain(value):
    """BSON values as Firestore-storable Python values."""
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    if isinstance(value, Decimal128):
        return float(value.to_decimal())
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    return value


def as_json(value) -> str:
    return json.dumps(value, default=lambda o: o.isoformat() if hasattr(o, "isoformat") else str(o))


def no_nested_arrays(value, inside_array: bool = False):
    """Firestore can't hold an array directly inside an array: such inner arrays become JSON text."""
    if isinstance(value, dict):
        return {k: no_nested_arrays(v) for k, v in value.items()}
    if isinstance(value, list):
        return as_json(value) if inside_array else [no_nested_arrays(v, True) for v in value]
    return value


def with_ttl(data: dict, ttl: timedelta) -> dict:
    created = data.get("created_at")
    if isinstance(created, datetime) and "expires_at" not in data:
        data["expires_at"] = created + ttl
    return data


# Each converter takes a plain record (its _id still inside) and returns
# (document id, data), or None to leave the record out.
def keep_id(data):
    return data.pop("_id"), data


def usage_cycle(data):
    data.pop("_id")
    return firebase_db.cycle_doc_id(data["user_id"], data["cycle_start_date"]), data


def analysis_cache(data):
    data.pop("_id")
    if "payload" in data:
        data["payload_json"] = as_json(data.pop("payload"))
    return data["key"], data


def brand_persona(data):
    data.pop("_id")
    return data["user_id"], data


def responder_event(data):
    old_id = data.pop("_id")
    data.pop("reply_lock", None)
    data.setdefault("simulated", False)
    if data.get("raw") is not None and not isinstance(data["raw"], str):
        data["raw"] = as_json(data["raw"])[:8000]
    if data.get("user_id") and data.get("platform") and data.get("external_id") is not None:
        new_id = firebase_db.event_doc_id(data["user_id"], data["platform"], str(data["external_id"]))
    else:
        new_id = old_id
    EVENT_IDS[old_id] = new_id
    return new_id, data


def notification(data):
    if data.get("event_id") in EVENT_IDS:
        data["event_id"] = EVENT_IDS[data["event_id"]]
    return keep_id(with_ttl(data, firebase_db.NOTIFICATION_TTL))


EVENT_IDS: dict[str, str] = {}

# Order matters: events before notifications (their links are rewritten).
PLAN = [
    ("users", keep_id),
    ("activities", keep_id),
    ("calendar_notes", keep_id),
    ("usage_cycles", usage_cycle),
    ("cost_logs", keep_id),
    ("cost_alerts", lambda d: keep_id(with_ttl(d, firebase_db.COST_ALERT_TTL))),
    ("analysis_cache", analysis_cache),
    ("brand_personas", brand_persona),
    ("responder_events", responder_event),
    ("notifications", notification),
    ("meta_poll_seen", lambda d: keep_id(with_ttl(d, firebase_db.POLL_SEEN_TTL))),
    ("meta_poll_state", keep_id),
]


async def write_all(collection, docs: list[tuple[str, dict]], name: str, totals: dict) -> None:
    for i in range(0, len(docs), firebase_db.BATCH_SIZE):
        chunk = docs[i:i + firebase_db.BATCH_SIZE]
        try:
            batch = firebase_db.db.batch()
            for doc_id, data in chunk:
                batch.set(collection.document(doc_id), data)
            await batch.commit()
        except Exception as e:
            totals["failed"] += len(chunk)
            print(f"  ! {name} batch ({len(chunk)} document(s)): {type(e).__name__}: {e}")
        else:
            totals["written"] += len(chunk)


def positive_limit(value: str) -> int:
    limit = int(value)
    if limit < 1:
        raise argparse.ArgumentTypeError("--limit must be a positive integer")
    return limit


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mongo-uri", default=os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017"))
    parser.add_argument("--mongo-db", default=os.getenv("MONGO_DB", "brandora"))
    parser.add_argument("--dry-run", action="store_true", help="read and convert, write nothing")
    parser.add_argument("--limit", type=positive_limit,
                        help="read at most this many documents per source collection")
    parser.add_argument("--include-legacy", action="store_true",
                        help="also archive collections the app no longer uses, as they are")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if not args.dry_run:
        ok, why = await firebase_db.firestore_ok()
        if not ok:
            sys.exit(f"Firestore is not reachable: {why}")

    mongo = MongoClient(args.mongo_uri, serverSelectionTimeoutMS=5000)[args.mongo_db]
    present = set(mongo.list_collection_names())
    print(f"MongoDB {args.mongo_db}: {', '.join(sorted(present)) or 'no collections'}")
    print(f"Firestore: {'(dry run, nothing written)' if args.dry_run else firebase_db.db.project}\n")

    known = {name for name, _ in PLAN} | set(SKIPPED)
    legacy = sorted(n for n in present if n not in known and not n.startswith("system."))
    plan = PLAN + ([(n, lambda d: keep_id(no_nested_arrays(d))) for n in legacy] if args.include_legacy else [])

    totals = {"read": 0, "written": 0, "skipped": 0, "failed": 0}
    target_counts = {}
    for name, convert in plan:
        if name not in present:
            continue
        docs, invalid_ids = [], 0
        cursor = mongo[name].find()
        if args.limit is not None:
            cursor = cursor.limit(args.limit)
        for raw in cursor:
            totals["read"] += 1
            try:
                converted = convert(plain(raw))
            except Exception as e:
                totals["failed"] += 1
                print(f"  ! {name} {raw.get('_id')}: {type(e).__name__}: {e}")
                continue
            if converted and firebase_db.valid_id(converted[0]):
                docs.append(converted)
            else:
                totals["skipped"] += 1
                invalid_ids += 1
                print(f"  ! {name} {raw.get('_id')}: no usable document id")
        target_counts[name] = len(docs)
        if name == "users":
            emails = [
                (firebase_db.email_key(d["email"]), {"email": d["email"].strip().lower(), "user_id": doc_id,
                                                      "created_at": d.get("created_at")})
                for doc_id, d in docs if isinstance(d.get("email"), str) and d["email"].strip()
            ]
            target_counts["user_emails"] = len(emails)
        if not args.dry_run:
            await write_all(firebase_db.db.collection(name), docs, name, totals)
            if name == "users":
                await write_all(firebase_db.user_emails, emails, "user_emails", totals)
        suffix = "would write" if args.dry_run else "to write"
        note = f", {invalid_ids} invalid-id skipped" if invalid_ids else ""
        print(f"{name:18} {len(docs):6} document(s) {suffix}{note}")
        if name == "users":
            print(f"{'user_emails':18} {len(emails):6} document(s) {suffix}")

    for name in SKIPPED:
        if name in present:
            cursor = mongo[name].find()
            if args.limit is not None:
                cursor = cursor.limit(args.limit)
            skipped_count = 0
            for _ in cursor:
                totals["read"] += 1
                totals["skipped"] += 1
                skipped_count += 1
            print(f"{name:18} {skipped_count:6} skipped (short-lived)")
    if legacy and not args.include_legacy:
        counts = {n: mongo[n].estimated_document_count() for n in legacy}
        print(f"\nNot used by the app, not copied (add --include-legacy to archive them): "
              + ", ".join(f"{n} ({c})" for n, c in counts.items()))
    if args.dry_run:
        print("\nDocuments per Firestore collection that would be written:")
        for name, count in target_counts.items():
            print(f"  {name:18} {count:6}")
    print(
        "\nSummary: "
        f"documents read={totals['read']}, "
        f"written={totals['written']}, "
        f"skipped={totals['skipped']}, "
        f"failed={totals['failed']}"
    )
    if args.dry_run:
        print(f"Dry run: {sum(target_counts.values())} document(s) would be written; nothing was written.")
    if totals["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
