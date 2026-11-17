"""Restore/commit durable state without checking out or modifying the source branch."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

BRANCH = "refs/heads/digest-state"
DATA = Path(".digest-data")


def git(*args, input=None, env=None, allowed=(0,)):
    result = subprocess.run(["git", *args], input=input, text=True, capture_output=True, env=env)
    if result.returncode not in allowed:
        # Git errors can contain remote URLs with embedded credentials; keep logs generic.
        raise RuntimeError(f"Git {args[0]} failed (exit {result.returncode}). Check repository permissions and digest-state branch rules.")
    return result


def restore():
    DATA.mkdir(exist_ok=True)
    remote = git("ls-remote", "--exit-code", "origin", BRANCH, allowed=(0, 2))
    if remote.returncode == 2:
        (DATA / "base").write_text("")
        (DATA / "state.json").write_text('{"version":1,"seen":[],"pending":[],"history":[],"last_checked":null}\n')
        print("Starting a new digest-state branch")
        return
    git("fetch", "--no-tags", "origin", BRANCH)
    base = git("rev-parse", "FETCH_HEAD").stdout.strip()
    state = git("show", f"{base}:state.json").stdout
    # Missing/corrupt state fails later validation; it must never silently reset.
    (DATA / "state.json").write_text(state)
    (DATA / "base").write_text(base)
    print("Restored digest-state")


def save():
    base = (DATA / "base").read_text().strip()
    blob = git("hash-object", "-w", str(DATA / "state.json")).stdout.strip()
    with tempfile.TemporaryDirectory() as directory:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(directory) / "index"),
                   GIT_AUTHOR_NAME="github-actions[bot]", GIT_COMMITTER_NAME="github-actions[bot]",
                   GIT_AUTHOR_EMAIL="41898282+github-actions[bot]@users.noreply.github.com",
                   GIT_COMMITTER_EMAIL="41898282+github-actions[bot]@users.noreply.github.com")
        git("read-tree", "--empty", env=env)
        git("update-index", "--add", "--cacheinfo", "100644", blob, "state.json", env=env)
        tree = git("write-tree", env=env).stdout.strip()
        if base and tree == git("rev-parse", base + "^{tree}").stdout.strip():
            print("State unchanged")
            return
        parents = ["-p", base] if base else []
        commit = git("commit-tree", tree, *parents, input="Save daily digest state\n", env=env).stdout.strip()
        # Never force-push: a competing writer causes failure, not lost state.
        git("push", "origin", f"{commit}:{BRANCH}")
    print("Saved digest-state")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["restore", "save"])
    args = parser.parse_args()
    try:
        (restore if args.action == "restore" else save)()
        return 0
    except (RuntimeError, OSError) as error:
        print(str(error) if isinstance(error, RuntimeError) else "Cannot access local state files", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
