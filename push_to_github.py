#!/usr/bin/env python3
"""Helper script to push Part-2 to GitHub repository using pure-Python dulwich.

Usage:
  python3 push_to_github.py --token <YOUR_GITHUB_TOKEN>
  or
  GITHUB_TOKEN=<token> python3 push_to_github.py
"""

from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import ssl
import sys
import tempfile

import certifi

# Configure SSL certificates
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()
ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())

import dulwich.porcelain as porcelain
from dulwich.repo import Repo

REPO_URL = "https://github.com/Abhi-502/LPDG-Innovation-Hub-2026.git"
SOURCE_DIR = pathlib.Path(__file__).resolve().parent

# Files and directories that MUST NEVER be copied or committed (confidential data & cache)
EXCLUDED_NAMES = {
    "data",
    "telemetry",
    "artifacts",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "venv",
    ".env",
    ".git",
    "predictions.csv",
    "gateway_master.csv",
    "meter_read_success.csv",
}
EXCLUDED_EXTENSIONS = {".parquet", ".csv", ".pyc", ".lock"}


def should_exclude(path: pathlib.Path) -> bool:
    for part in path.parts:
        if part in EXCLUDED_NAMES:
            return True
    if path.suffix in EXCLUDED_EXTENSIONS and path.name != "pyproject.toml":
        return True
    return False


def copy_part2_files(dest_part2_dir: pathlib.Path) -> list[str]:
    """Copy only non-confidential source files into target Part-2 folder."""
    dest_part2_dir.mkdir(parents=True, exist_ok=True)
    copied_files = []

    for item in SOURCE_DIR.rglob("*"):
        if item.is_dir():
            continue
        rel_path = item.relative_to(SOURCE_DIR)
        if should_exclude(rel_path):
            continue

        target_file = dest_part2_dir / rel_path
        target_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target_file)
        copied_files.append(str(rel_path))

    return copied_files


def main() -> int:
    parser = argparse.ArgumentParser(description="Push Part-2 to GitHub")
    parser.add_argument(
        "--token",
        type=str,
        default=os.getenv("GITHUB_TOKEN"),
        help="GitHub Personal Access Token (classic or fine-grained with repo write scope)",
    )
    parser.add_argument(
        "--branch",
        type=str,
        default="main",
        help="Target git branch (default: main)",
    )
    args = parser.parse_args()

    if not args.token:
        print("ERROR: GitHub token is required to push to private repository.", file=sys.stderr)
        print("Please provide via --token <TOKEN> or set GITHUB_TOKEN environment variable.", file=sys.stderr)
        print("Example: python3 push_to_github.py --token ghp_xxxxxxxxxxxxxxxx", file=sys.stderr)
        return 1

    # Form authenticated URL
    auth_url = REPO_URL.replace("https://", f"https://oauth2:{args.token}@")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = pathlib.Path(temp_dir)
        print(f"[*] Cloning repository from {REPO_URL}...")
        try:
            repo = porcelain.clone(auth_url, target=str(temp_path), ca_certs=certifi.where())
            print(f"[+] Cloned successfully.")
        except Exception as e:
            print(f"[-] Failed to clone repository: {e}", file=sys.stderr)
            return 1

        target_part2_dir = temp_path / "Part-2"
        print(f"[*] Copying sanitized Part-2 files to repository folder '{target_part2_dir.name}'...")
        copied = copy_part2_files(target_part2_dir)
        print(f"[+] Copied {len(copied)} sanitized source files (confidential data strictly excluded).")

        print("[*] Staging files for commit...")
        porcelain.add(repo, paths=[str(target_part2_dir.relative_to(temp_path))])

        print("[*] Creating commit...")
        porcelain.commit(
            repo,
            message=b"feat(part2): add Part-2 software development production API and tests",
            author=b"Abhi-502 <candidate@lpdg-challenge.local>",
        )

        print("[*] Pushing commit to remote repository...")
        try:
            porcelain.push(repo, auth_url, refspecs=[f"refs/heads/{args.branch}".encode()], ca_certs=certifi.where())
            print(f"[+] Successfully pushed Part-2 to {REPO_URL} on branch '{args.branch}'!")
        except Exception as e:
            print(f"[-] Failed to push to remote: {e}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
