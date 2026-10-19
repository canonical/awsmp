# AGENTS.md

Instructions for AI coding agents working in this repository.

## Project overview

`awsmp` is a Python module and CLI tool developed by Canonical to automate interactions with the **AWS Marketplace Catalog API (CAPI)** and the **AWS EC2 Image Builder API**. Given local YAML configurations or CSV pricing files, it:

- Inspects live Marketplace entities (`AmiProduct@1.0`, `Offer@1.0`) across visibility states (`Public`, `Limited`, `Restricted`)
- Creates and updates AMI public product listings (descriptions, regions, versions, support terms, and legal terms)
- Manages instance types and rate cards with strict dimension preservation rules enforced by AWS CAPI
- Generates and publishes targeted private offers for buyer AWS accounts with custom validity and duration
- Creates, manages, and attaches EC2 Image Builder component delivery options to Marketplace products
- Diffs local YAML configurations against live AWS Marketplace entity details and downloads live entity definitions

It is installed as the `awsmp` / `awsmpcli` CLI (entry points defined in `pyproject.toml`, implemented in `awsmp/cli/`).

## Tech stack

- **Python**: `>= 3.10, < 3.14` (tested against 3.10–3.13)
- **AWS SDK**: `boto3` (`marketplace-catalog`, `ec2`, `imagebuilder`), `botocore`
- **Validation & Models**: `pydantic` (v2)
- **CLI & Output**: `click`, `prettytable`
- **Serialization**: `pyyaml` with custom block scalar dumper
- **Package & Environment Management**: [uv](https://github.com/astral-sh/uv), [tox](https://tox.wiki/) (`tox-uv`)
- **Documentation**: Sphinx, MyST parser, Read the Docs

## Repository layout

- `awsmp/` — main Python package
  - `cli/` — Click CLI commands (`inspect`, `public-offer`, `private-offer` in `__init__.py`; `image-builder` in `ib_cli.py`)
  - `_driver.py` — core AWS service orchestration (`AmiProduct`, `IbProduct`), error mapping, rate card preservation, entity diffing
  - `changesets.py` — CAPI ChangeSet payload builders (`CreateProduct`, `CreateOffer`, `UpdatePricingTerms`, `AddDeliveryOptions`, etc.)
  - `models.py` — Pydantic v2 data models, validation rules, and bidirectional YAML <-> AWS entity mapping
  - `errors.py` — custom domain exceptions mapping boto3 `ClientError` codes
  - `constants.py` — Marketplace categories and fixed enumeration values
  - `types.py` — `TypedDict` definitions for changeset payloads and dimensions
  - `yaml_utils.py` — PyYAML custom dumper preserving 2-space indented lists and literal block scalars (`|`)
- `tests/` — pytest suite (`test_driver.py`, `test_changesets.py`, `test_cli.py`, `test_models.py`) and fixtures (`local_config/`, `*.yaml`, `*.csv`)
- `docs/` — Sphinx documentation (guides, command references, MyST/RST)
- `openspec/` — OpenSpec specs and change proposals
- `specifications/` — domain specifications (e.g. `COMPONENTS.md` for EC2 Image Builder)
- `snap/` — Snapcraft packaging definition (`snapcraft.yaml`)
- `pyproject.toml` — project metadata, script entry points, and dependencies managed with `uv`
- `tox.ini` — test, lint, and formatting environment configurations

## Setup

Dependencies are managed with [uv](https://github.com/astral-sh/uv) and tasks are orchestrated through [tox](https://tox.wiki/) using `tox-uv`. Do not install ad-hoc tooling; use what `tox` and `uv` provide.

```bash
uv sync --all-groups
```

## Build, test, and lint

Always prefer running checks through `tox` (matches CI):

```bash
tox                  # run full matrix: lint, py310-py313, test
tox -e test          # run unit tests with coverage (pytest --cov=awsmp)
tox -e lint          # run linters: isort --check, black --check, mypy --check-untyped-defs
tox -e fix           # run formatters: isort and black
```

Or run targeted commands directly via `uv`:

```bash
uv run pytest tests/test_driver.py -k test_name
uv run pytest --cov=awsmp
uv run mypy . --check-untyped-defs
```

- Line length limit is **120** characters (`black`).
- Import sorting follows the `black` profile via `isort`.
- Type checking is enforced with `mypy` (excluding `docs/`).

## Key Conventions & Invariants

1. **AWS Marketplace Rate Card Integrity**:
   - In `awsmp/_driver.py` and `awsmp/changesets.py`, rate cards must not drop existing dimensions that are already restricted or untouched. AWS Marketplace rejects changesets if previously-existing dimensions disappear from `UsageBasedPricingTerm` ("Rates can't be removed from UsageBasedPricingTerm").
   - Always preserve untouched dimensions via `preserved_rate_card_hourly` / `preserved_rate_card_annual`.
   - Newly removed instance types in the current batch must be restricted in dimensions (`RestrictDimensions`) and instance types (`RestrictInstanceTypes`), and excluded from active rate cards. Already-restricted dimensions must not be resubmitted to `RestrictInstanceTypes`.

2. **EC2 Image Builder Ingestion**:
   - All component documents (YAML) must provide default values for all parameters because AWS Marketplace runs automated headless ingestion tests that reject interactive prompts.
   - The Image Builder client is pinned to `us-east-1` (`get_ib_client()`).

3. **Pydantic Models & Pricing Rules**:
   - Built on Pydantic v2 syntax (`model_validator(mode="after")`, `field_validator`, `populate_by_name = True`).
   - Prices must be non-negative (`>= 0.00`) and have at most 3 decimal places. Hourly pricing must not exceed annual pricing when an annual price is provided.

4. **Configuration Schemas & Validation Nuances**:
   - Empty values in configuration YAML should use `~` for string types (`None`) and `[]` for lists.
   - `support_description` and `long_description` must not have leading or trailing whitespace.
   - `commercial_regions` requires explicit region names (GovCloud regions e.g. `us-gov-east-1` can be included).
   - In version configuration, `ami_id` must start with `ami-`, `access_role_arn` must start with `arn:aws:iam::`, `os_system_name` is automatically uppercased, and `ip_ranges` can have up to 5 CIDR blocks.
   - `eula_document` supports either a single `CustomEula` (requires `url`) or `StandardEula` (requires `version`), but never both fields on the same document item.
   - Private-offer pricing CSVs must be headerless and contain exactly three columns in this order: `name` (dimension / instance type), `price_hourly`, and `price_annual`.
   - Ensure pricing CSV entries cover all required product dimensions.
   - Preserve existing CSV parsing and validation behavior when modifying pricing logic.

5. **Service & CLI Boundaries**:
   - Keep AWS API interactions and boto3 calls isolated within `awsmp/_driver.py`. CLI entry points in `awsmp/cli/` handle CLI argument parsing, input validation, delegating to driver methods, and formatting output (via `prettytable` or Click).
   - ChangeSet definitions must stay modular inside `awsmp/changesets.py`.
   - AWS Marketplace Catalog API operations require the `us-east-1` region (default in the CLI).
   - Use `yaml_utils.dump` when serializing local YAML configurations to maintain clean formatting with 2-space indented lists and literal scalar blocks (`|`).

## Documentation

Documentation lives under `docs/` and is built with Sphinx (see `.readthedocs.yaml` and `docs/conf.py`). Update relevant command documentation (`docs/inspect/`, `docs/public-offer/`, `docs/private-offer/`) whenever adding or modifying CLI parameters or configuration schema.

## Safety and AWS Operations

- Never expose AWS credentials, secrets, or sensitive account information.
- Prefer mocked AWS clients (`moto` or custom fixtures) for unit tests.
- Do not perform live Marketplace mutations during development or testing unless explicitly requested and authorized.
- Treat product publication, pricing updates, and private-offer creation as consequential operations.
- Always review generated ChangeSet payloads before submitting them to AWS, and ensure `--dry-run` is available, exercised, and thoroughly tested in unit tests.

## Boundaries

- **Always**:
  - Run targeted tests while developing.
  - Before submitting code changes, run the relevant lint and test checks (`tox -e lint`, `tox -e test`).
  - Run the full test suite (`tox`) for changes affecting shared models, pricing, rate-card handling, or AWS API payloads.
  - Report checks that could not be run; never claim they passed without executing them.
  - Maintain rate card preservation invariants whenever touching pricing or instance type logic.
- **Ask first**:
  - Changing public CLI commands or argument semantics in `awsmp/cli/`.
  - Adding new dependencies to `pyproject.toml`.
  - Altering the schema of the YAML configuration files.
  - Introducing new Marketplace entity types or mutating default AWS regions (`us-east-1`).
- **Never**:
  - Commit credentials, AWS access keys, or secrets.
  - Submit live AWS Marketplace changesets without supporting `--dry-run`.
  - Drop historical dimensions from Marketplace rate cards without restriction handling.
  - Commit artifacts such as `.coverage`, `.mypy_cache`, `.pytest_cache`, `.tox`, or `.venv`.

## Before committing

1. `tox -e fix` (or `uv run isort .` && `uv run black .`) to format, then inspect the resulting diff to avoid including unrelated formatting changes.
2. `tox -e lint` and `tox -e test` must pass cleanly.
3. Check `git status` to ensure no temporary test fixtures or build caches are staged.