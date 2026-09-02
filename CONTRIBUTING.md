# Contributing

Issues and focused pull requests are welcome.

1. Create a virtual environment and install `.[dev]`.
2. Add tests for behavior changes and failure cases.
3. Run `python -m ruff format .`.
4. Run `./scripts/verify.sh`.
5. Explain schema or input-contract changes in the pull request.

Schema changes must use a new entry in `MIGRATIONS`; do not modify a released migration in
place. Keep runtime dependencies at zero unless a dependency provides a clear, measured benefit.

By contributing, you agree that your contribution may be distributed under the MIT License.
