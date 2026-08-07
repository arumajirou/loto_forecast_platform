# Handoff — GitHub Projects Governance v1

## Current state

The repository contains a validated governance specification and owner execution plan generator.
Live Project creation remains an explicit owner action because neither the connector nor the local
environment can perform Project mutations.

## Owner sequence

1. install and authenticate GitHub CLI;
2. refresh the `project` scope;
3. validate and review the generated owner plan;
4. create the private user-owned Project;
5. link the repository;
6. configure fields, views and built-in workflows;
7. export JSON and screenshots;
8. verify behavior with test Issue and PR items;
9. generate artifact manifest and SHA-256;
10. update the verification report in a follow-up PR.

## Stop conditions

Stop when ownership, visibility, scope, field identity, view API permission or workflow
behavior does not match the specification. Do not delete populated fields or the Project to hide a
mismatch.
