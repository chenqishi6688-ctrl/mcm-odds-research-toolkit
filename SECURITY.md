# Security policy

## Supported version

Security fixes are applied to the latest public release.

## Sensitive data

Never commit API keys, bearer tokens, cookies, account identifiers, personal bankroll information, encrypted credential stores, or raw provider exports with uncertain redistribution rights.

Use environment variables or an external secret manager for local connectors. Synthetic fixtures should be used for public bug reports whenever possible.

## Reporting a vulnerability

Open a private security advisory in the GitHub repository. Do not include live credentials or personal data in a public issue. If a secret was committed, revoke it first; deleting a file does not remove it from Git history.


