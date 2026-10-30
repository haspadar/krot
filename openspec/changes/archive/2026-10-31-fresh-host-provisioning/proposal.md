# Reliable fresh host provisioning

## Why

A fresh Ubuntu host must retain a working Docker daemon after provisioning and support
Ansible becoming an unprivileged service account. Docker rejects unknown daemon JSON keys;
without POSIX ACL tools Ansible cannot share temporary modules between unprivileged users.

## What changes

- Remove the unsupported Docker metadata key and validate rendered configuration with dockerd before replacement
- Install acl in the common base packages without changing existing filesystem ACLs
- Exercise fresh installation, daemon validation and rejection of invalid replacement configuration
- Verify ACL tools from the default common package list on an initially ACL-free host

## Scope

Host roles only; no application configuration, consumer inventory or production rollout.
