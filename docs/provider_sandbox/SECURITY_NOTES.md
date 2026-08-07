# Security Notes

- SHA-256 proves retained byte identity, not kernel isolation.
- `CUDA_VISIBLE_DEVICES` is not a security boundary and is not used to approve Bubblewrap GPU access.
- Bubblewrap argv construction does not prove cgroup, seccomp, AppArmor or SELinux enforcement.
- Rootless OCI flags do not prove that the runtime or kernel applied them; effective evidence is
  required.
- Raw child stdout/stderr is deliberately not retained because provider output may contain secrets.
- A repository subdirectory may be mounted read-only; the complete home directory, SSH/cloud
  credential directories and container sockets are forbidden.
- Runtime Certification remains a separate gate after sandbox execution.
