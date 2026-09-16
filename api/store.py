"""SQLite jobs and created-at-based expiry."""
import hashlib
from contextlib import contextmanager
import json
import logging
import re
import shutil
import sqlite3
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class JobStore:
    """Keep results for 24 hours and submissions for one hour."""
    def __init__(self, database, work_root, cleanup_fallback=None):
        self.database = Path(database)
        self.work_root = Path(work_root)
        self.cleanup_fallback = cleanup_fallback
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.work_root.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, demo_id TEXT NOT NULL,
                    status TEXT NOT NULL, created_at REAL NOT NULL, result_json TEXT
                );
                CREATE INDEX IF NOT EXISTS jobs_created ON jobs(created_at);
                CREATE TABLE IF NOT EXISTS submissions (ip_hash TEXT, created_at REAL);
                CREATE INDEX IF NOT EXISTS submissions_ip_time ON submissions(ip_hash, created_at);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA secure_delete = ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def reserve(self, job_id, demo_id, ip, limit, now=None):
        """Atomically charge a submission and insert its job."""
        now = time.time() if now is None else now
        ip_hash = hashlib.sha256(ip.encode()).hexdigest()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM submissions WHERE created_at <= ?", (now - 3600,))
            count = db.execute("SELECT COUNT(*) FROM submissions WHERE ip_hash = ?", (ip_hash,)).fetchone()[0]
            if count >= limit:
                return False
            db.execute("INSERT INTO submissions VALUES (?, ?)", (ip_hash, now))
            db.execute("INSERT INTO jobs VALUES (?, ?, 'queued', ?, NULL)", (job_id, demo_id, now))
        return True

    def get(self, job_id, now=None):
        now = time.time() if now is None else now
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id = ? AND created_at >= ?",
                             (job_id, now - 86400)).fetchone()
        return dict(row) if row else None

    def update(self, job_id, status, result=None):
        with self.connect() as db:
            db.execute("UPDATE jobs SET status = ?, result_json = ? WHERE id = ?",
                       (status, json.dumps(result) if result is not None else None, job_id))

    def mark_interrupted(self):
        """BackgroundTasks do not survive an API restart."""
        with self.connect() as db:
            db.execute("UPDATE jobs SET status = 'error', result_json = ? WHERE status IN ('queued', 'running')",
                       (json.dumps({"message": "The demo was interrupted. Please run it again."}),))

    def cleanup_expired(self, now=None):
        """Delete expired directories first, then their rows; retry failed deletions later."""
        now = time.time() if now is None else now
        cutoff = now - 86400
        deleted = 0
        with self.connect() as db:
            rows = db.execute("SELECT id FROM jobs WHERE created_at < ?", (cutoff,)).fetchall()
            for row in rows:
                job_id = row["id"]
                if not re.fullmatch(r"[0-9a-f]{32}", job_id):
                    logger.error("Invalid stored job ID; refusing filesystem cleanup")
                    db.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
                    deleted += 1
                    continue
                directory = self.work_root / job_id
                try:
                    if directory.is_symlink():
                        directory.unlink()
                    elif directory.exists():
                        self.remove_directory(directory)
                    db.execute("DELETE FROM jobs WHERE id = ? AND created_at < ?", (job_id, cutoff))
                    deleted += 1
                except OSError:
                    logger.exception("Could not clean expired job %s", job_id)
            db.execute("DELETE FROM submissions WHERE created_at <= ?", (now - 3600,))
            live_ids = {row[0] for row in db.execute("SELECT id FROM jobs")}
        # A crash between copying files and inserting a row must not leave an orphan forever.
        for directory in self.work_root.iterdir():
            if (re.fullmatch(r"[0-9a-f]{32}", directory.name)
                    and directory.name not in live_ids and directory.lstat().st_mtime < cutoff):
                try:
                    if directory.is_symlink():
                        directory.unlink()
                    elif directory.is_dir():
                        self.remove_directory(directory)
                except OSError:
                    logger.exception("Could not clean orphaned job directory")
        return deleted

    def remove_directory(self, directory):
        """Use the fixed helper if sandbox-owned permissions prevent ordinary deletion."""
        try:
            shutil.rmtree(directory)
        except PermissionError:
            if self.cleanup_fallback is None:
                raise
            self.cleanup_fallback(directory.name)
