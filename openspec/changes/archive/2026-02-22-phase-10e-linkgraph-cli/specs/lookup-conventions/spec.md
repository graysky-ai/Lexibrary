## MODIFIED Requirements

### Requirement: Lookup appends inherited Local Conventions
The `lexi lookup <file>` command SHALL, after displaying the design file content, walk upward from the file's parent directory to `scope_root` (inclusive), parsing each `.aindex` file for `local_conventions`. If any conventions are found, an `## Applicable Conventions` section SHALL be appended to the output. After conventions, if a link graph index is available, reverse link sections SHALL be appended.

#### Scenario: File in directory with conventions
- **WHEN** running `lexi lookup src/payments/processor.py` and `src/payments/.aindex` has Local Conventions ["All monetary values use Decimal"]
- **THEN** the output includes an "## Applicable Conventions" section with "From `src/payments/`:" and the convention text

#### Scenario: File inherits conventions from multiple parent directories
- **WHEN** running `lexi lookup src/payments/stripe/charge.py` and both `src/.aindex` has conventions ["Use UTC everywhere"] and `src/payments/.aindex` has conventions ["Use Decimal for money"]
- **THEN** the output shows conventions from both directories, with closest directory first

#### Scenario: File with no applicable conventions
- **WHEN** running `lexi lookup src/utils/helpers.py` and no parent `.aindex` files have Local Conventions
- **THEN** no "## Applicable Conventions" section is appended (reverse link sections may still appear if index is available)

#### Scenario: Conventions appear before reverse links
- **WHEN** running `lexi lookup src/payments/processor.py` and both conventions and reverse links are available
- **THEN** the `## Applicable Conventions` section appears before any `## Dependents` or `## Also Referenced By` sections
