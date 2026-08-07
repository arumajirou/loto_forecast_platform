# Migration Notes

No provider is migrated in v1.

A later provider migration must:

- keep the provider's existing request/response and Runtime Certification semantics;
- map only reviewed runtime, repository, model, input and output paths;
- supply immutable backend and OCI image identity;
- preserve current offline and remote-code allowlist rules;
- retain requested and effective sandbox evidence beside Runtime Certification evidence;
- fail closed without changing existing prediction, registry or promotion artifacts;
- migrate one provider per PR and retain the legacy path until parity is proven.
