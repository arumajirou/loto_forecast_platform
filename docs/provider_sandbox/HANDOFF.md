# Handoff

## Current gate

The foundation is ready for review as an isolated Draft PR. It is not ready for provider migration or
production execution.

## Next target-host gate

1. select one disposable provider fixture with no project data;
2. verify exact Bubblewrap and rootless OCI binary identities;
3. execute CPU-only cases on a reviewed Linux host;
4. inspect namespaces, mounts, network, capabilities, privilege flags and resource limits from outside
   the child process;
5. verify timeout, process-tree termination and output bounds;
6. execute OCI GPU allowlist tests only after CPU controls pass;
7. retain complete host evidence, manifest and SHA-256;
8. integrate one provider in a separate PR without replacing Runtime Certification.

## Stop conditions

Stop on missing effective evidence, backend drift, mutable OCI image, unexpected mount, environment
leakage, socket access, home/credential exposure, unbounded resource, CPU fallback or unverifiable GPU
device isolation.
