# binsentinel-watcher

Minimal private repository for running the BinSentinel watcher on GitHub Actions.

## Files

- `.github/workflows/watch.yml`
- `watcher/`
- `scripts/init_meta.py`

## Required Secrets

- `META_REPO_TOKEN`
- `META_REPO`
- `SCOOP_GITHUB_TOKEN`

## Local Run

```powershell
$env:GITHUB_TOKEN='<token>'
python -m pip install -r watcher/requirements.txt
python scripts/init_meta.py <meta-repo-path>
python -m watcher.check_updates <meta-repo-path>
```

