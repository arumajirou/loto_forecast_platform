# PR #370 Ruff format baseline evidence

Source main:

`b6575da744d9261d86b7ce9594b267498a0bb22c`

Audited PR head:

`1b64f067537776b1fc2e640f70fcd4b70f3c4d06`

Locked Ruff:

`0.16.3`

Observed:

- main unformatted: 16
- PR unformatted: 16
- inherited: 16
- resolved by PR: 0
- introduced by PR: 0
- PR adds format debt: false

Local audit SHA-256:

- `d1345584b7b97446b2032fd10e3190172bcb247095511042bb42553f4a500693  FORMAT_BASELINE.json`
- `7a5e8b97c0c4160915e52ca2bef92adbbe0acb928a7b9f06e4b185ec16627f06  main-format.log`
- `f8da99e3b7913f366cc678775c7954eb2d41b49005f8c1542364bb05dff602e3  pr-format.log`

Classification:

`CI_FAILURE=INHERITED_MAIN_RUFF_FORMAT_DEBT`

`PR370_NEW_FORMAT_DEBT=0`

Scientific boundary:

- Holdout: CLOSED
- Prospective: CLOSED
- Promotion: CLOSED
