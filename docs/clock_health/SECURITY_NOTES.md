# Security Notes

- The core evaluator performs no shell, network, database, or filesystem discovery.
- The adapter uses only fixed argv and `shell=False`.
- Source names are hashed before persistence.
- Raw stderr is retained as bytes for audit but is never interpreted as a health pass.
- Structured failures expose bounded error codes, not raw exception strings.
- No token, secret, DSN, authorization header, or environment inventory is required.
- Local clock health cannot produce third-party time or signature status.
