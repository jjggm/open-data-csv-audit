# Contributing

Thanks for helping make public data easier to validate.

1. Start with an issue describing a reproducible CSV edge case or useful check.
2. Add a small test using synthetic, non-sensitive data.
3. Implement the fix without adding a mandatory runtime dependency.
4. Run `python -m unittest discover -s tests -v` before opening a pull request.
5. Explain behavior changes in the pull request; keep schemas backward-compatible when possible.

Do not upload private, confidential, or copyrighted datasets without permission.
By contributing, you agree that your contribution may be distributed under MIT.
