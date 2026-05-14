"""
Clear all tool-job history for a single user.

Wipes:
  - tool_jobs documents (jobs of all tools)
  - subprocess artifacts on disk (uploads + outputs + work folders)
  - GridFS files attached to those jobs (transcripts are inline in docs,
    so nothing else to clean)

Does NOT touch:
  - the user account itself
  - tool_settings (api key, plan, render counter)
  - audit / activity logs

Usage (from saurabh-tools/api):
    python scripts/clear_user_history.py saurabhbhayana1996@gmail.com

Add --dry-run to preview without deleting.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

# Allow this script to import from the api/ root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from pymongo import MongoClient


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("email", help="Email of the user to wipe")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the interactive confirmation prompt",
    )
    args = parser.parse_args()

    uri = os.environ["MONGODB_URI"]
    db_name = os.environ.get("MONGODB_DB", "saurabh")
    upload_dir = Path(os.environ.get("UPLOAD_DIR", "./uploads")).resolve()
    output_dir = Path(os.environ.get("OUTPUT_DIR", "./outputs")).resolve()

    client = MongoClient(uri)
    db = client[db_name]

    user = db.user.find_one({"email": args.email})
    if not user:
        print(f"[err] No user found with email {args.email!r}.")
        return 1
    user_id = str(user["_id"])
    print(f"User: {args.email}  (id={user_id})")

    jobs = list(db.tool_jobs.find({"userId": user_id}))
    print(f"Jobs to delete: {len(jobs)}")
    for j in jobs:
        print(f"  - {j.get('tool', '?'):<22} {j.get('status', '?'):<10}"
              f" {str(j['_id'])}")

    if not jobs:
        print("Nothing to do.")
        return 0

    if args.dry_run:
        print("\n--dry-run — nothing actually deleted.")
        return 0

    if not args.yes:
        confirm = input(
            f"\nDelete {len(jobs)} jobs + their output files? "
            f"This is irreversible. [y/N]: "
        )
        if confirm.strip().lower() != "y":
            print("Cancelled.")
            return 0
    else:
        print(f"\n--yes — deleting {len(jobs)} jobs + their output files…")

    # 1) Delete output files referenced by each job
    files_removed = 0
    for j in jobs:
        for key in ("outputPath", "srtPath"):
            p = j.get(key)
            if p:
                fp = Path(p)
                if fp.exists() and fp.is_file():
                    try:
                        fp.unlink()
                        files_removed += 1
                    except OSError as e:
                        print(f"   could not delete {fp}: {e}")
        # Audio/video uploads tracked under params
        params = j.get("params") or {}
        for key in ("audioPath", "videoPath"):
            p = params.get(key)
            if p:
                fp = Path(p)
                if fp.exists() and fp.is_file():
                    try:
                        fp.unlink()
                        files_removed += 1
                    except OSError as e:
                        print(f"   could not delete {fp}: {e}")

    # 2) Wipe per-user upload + output sub-folders if they exist.
    #    The api stores per-user under uploads/<userId>/ and outputs/<userId>/.
    folders_removed = 0
    for base in (upload_dir, output_dir):
        user_folder = base / user_id
        if user_folder.exists() and user_folder.is_dir():
            try:
                shutil.rmtree(user_folder)
                folders_removed += 1
                print(f"   removed folder {user_folder}")
            except OSError as e:
                print(f"   could not remove {user_folder}: {e}")

    # 3) Drop tool_jobs documents
    res = db.tool_jobs.delete_many({"userId": user_id})

    print()
    print(f"[ok] Deleted {res.deleted_count} job documents")
    print(f"[ok] Removed {files_removed} output / source files")
    print(f"[ok] Removed {folders_removed} per-user folders")
    print()
    print("User account, settings, and API key untouched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
