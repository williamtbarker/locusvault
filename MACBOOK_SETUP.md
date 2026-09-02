# macOS setup and GitHub release

These commands assume this directory is `~/Documents/locusvault`.

## Verify locally

```bash
cd ~/Documents/locusvault
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
python -m ruff format .
./scripts/verify.sh
```

`ruff format .` may make harmless whitespace-only edits. Run the verifier again afterward and
review the final diff with `git diff`.

## Publish a public repository

```bash
git init
git add .
git commit -m "Initial release: transactional sequence warehouse"
git branch -M main
gh repo create locusvault --public --source=. --remote=origin --push
```

After GitHub Actions passes, add a short repository description and these topics:

```text
python sqlite data-engineering bioinformatics fasta provenance cli
```

Then pin `locusvault` from the **Customize your pins** control on your GitHub profile.

## Optional tagged release

```bash
git tag -a v0.1.0 -m "LocusVault v0.1.0"
git push origin v0.1.0
gh release create v0.1.0 --generate-notes
```
