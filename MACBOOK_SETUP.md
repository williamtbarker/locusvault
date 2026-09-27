# macOS development setup

Clone the repository into a directory of your choice:

```bash
git clone https://github.com/williamtbarker/locusvault.git
cd locusvault
```

## Verify locally

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
./scripts/verify.sh
```

The verifier checks formatting, lint, types, tests, the example warehouse, and wheel creation.
To apply formatting fixes while developing, use `python -m ruff format .` and review the diff
before rerunning verification.

## Contributing changes

See [CONTRIBUTING.md](CONTRIBUTING.md) for review expectations. Create a branch for
your changes, rerun verification, and submit a pull request. Release tags should
refer to commits that have passed the repository CI matrix.
