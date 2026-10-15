"""Inspect every changed blob in the publication range, without printing values."""
import argparse
import json
import re
import subprocess
from pathlib import PurePosixPath


PATTERNS = {
    "user_profile_path": re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+(?!Public\b|USER\b|<)[^\s`\"]+", re.I),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{25,}\b"),
    "openai_token": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{35,}\b"),
    "credential_url": re.compile(r"https?://[^\s/:]+:[^\s/@]+@"),
}


def findings_for(path, data):
    findings = []
    name = PurePosixPath(path)
    if (name.parts[0] in {"data", "external_data", "variable", ".venv", ".venv312"}
            or name.suffix in {".db", ".sqlite", ".sqlite3", ".bundle", ".zip", ".env"}
            or name.name == ".env"):
        findings.append({"kind": "private_local_file", "file": path})
    if b"\x00" in data:
        if not (path.startswith("docs/assets/") and path.endswith(("-synthetic.png", "-synthetic.jpg"))):
            findings.append({"kind": "unreviewed_binary", "file": path})
        return findings
    for line, text in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
        for kind, pattern in PATTERNS.items():
            if pattern.search(text):
                findings.append({"kind": kind, "file": path, "line": line})
    return findings


def audit(base, head):
    def git(*args):
        return subprocess.check_output(["git", *args])
    commits = git("rev-list", "--reverse", base+".."+head).decode().splitlines()
    findings, blobs = [], 0
    for commit in commits:
        paths = git("diff-tree", "--no-commit-id", "--diff-filter=AM", "--name-only", "-r", commit).decode().splitlines()
        for path in paths:
            blobs += 1
            findings.extend({"commit": commit, **f} for f in findings_for(path, git("show", commit+":"+path)))
    return {"status": "PASS" if not findings else "BLOCKED", "head": git("rev-parse", head).decode().strip(),
            "commits": len(commits), "blobs_reviewed": blobs, "findings": findings,
            "limitations": ["Heuristics supplement manual review; binary content requires visual review"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args()
    report = audit(args.base, args.head)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["status"] == "PASS" else 1)
