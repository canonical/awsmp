# EC2 Image Builder Component Support for awsmp

Copilot driven specification. High degree of verbosity allows an implementation 
to resume from plan.

## CAPI Support

The AWS Marketplace Catalog API (CAPI) supports EC2 Image Builder component products
via the **`AmiProduct@1.0`** entity type. Image Builder delivery is not a separate entity type;
it is a delivery option variant (`Ec2ImageBuilderComponentDeliveryOptionDetails`). See [documentation](https://docs.aws.amazon.com/marketplace/latest/APIReference/work-with-ec2-image-builder-products.html#adding-new-ec2-ib-version-existing-product)

### Supported pricing models
- Free
- Hourly rate
- Hourly rate with initial free trial period
- BYOL is **not** supported

### Relevant ChangeTypes (all use `AmiProduct@1.0`)
| ChangeType | Purpose |
|---|---|
| `AddDeliveryOptions` | Add a new version with an Image Builder component ARN |
| `UpdateDeliveryOptions` | Update usage instructions or release notes for an existing version |
| `RestrictDeliveryOptions` | Restrict (hide) a version |
| `AddInstanceTypes` | Add supported instance types |
| `RestrictInstanceTypes` | Remove supported instance types |
| `UpdatePricingTerms` | Set/update hourly and annual pricing per instance type |

---

## Implementation Plan

We start from a schema example as it provides the right overview of the system. The implementation
details feed directly from common patterns that are already established.

#### Full schema example

```yaml
ec2_image_builder:
  description:
    product_title: "My Component"
    logourl: "https://awsmp-logos.s3.amazonaws.com/my-logo"
    short_description: "Installs and configures my-package."
    long_description: |
      A longer description of the component.
    highlights:
      - "Key feature 1"
      - "Key feature 2"
    search_keywords:
      - "component"
      - "linux"
    categories:
      - "Operating Systems"
    support_description: "Contact support@example.com for assistance."

  region:
    commercial_regions:
      - us-east-1
      - eu-west-1
    future_region_support: true

  offer:
    instance_types:
      - name: m5.large
        hourly: "0.05"
        yearly: "400.00"
      - name: m5.xlarge
        hourly: "0.10"
        yearly: "800.00"
    eula_document:
      - type: CustomEula
        url: "https://s3.amazonaws.com/my-bucket/eula.txt"
    refund_policy: |
      Your refund policy.

  version:
    version_title: "1.0.0"
    release_notes: "Initial release."
    access_role_arn: "arn:aws:iam::123456789012:role/MPEC2IBIngestion"
    delivery_options:
      - title: "My Component – Install"
        usage_instructions: "Add this component to your EC2 Image Builder pipeline."
        component:
          name: "my-component-install"
          semantic_version: "1.0.0"
          platform: Linux
          supported_os_versions:
            - "Ubuntu 22"
          description: "Installs my-package."
          # Verbatim EC2 Image Builder component document (YAML).
          # All parameters MUST have default values — Marketplace runs a headless
          # ingestion test pipeline that cannot accept interactive input.
          document: |
            schemaVersion: 1.0
            description: Installs my-package
            parameters:
              - region:
                  type: string
                  default: us-east-1
                  description: AWS region (default used by Marketplace test pipeline)
            phases:
              - name: build
                steps:
                  - name: Install
                    action: ExecuteBash
                    inputs:
                      commands:
                        - sudo apt-get install -y my-package
              - name: validate
                steps:
                  - name: Verify
                    action: ExecuteBash
                    inputs:
                      commands:
                        - my-package --version

      - title: "My Component – Configure"
        usage_instructions: "Add this component after the Install component to apply default configuration."
        component:
          name: "my-component-configure"
          semantic_version: "1.0.0"
          platform: Linux
          supported_os_versions:
            - "Ubuntu 22"
          description: "Applies default configuration for my-package."
          # Alternative: reference a pre-existing component ARN instead of an inline document.
          # Mutually exclusive with document + name + semantic_version + platform, etc.
          arn: "arn:aws:imagebuilder:us-east-1:123456789012:component/my-component-configure/1.0.0/1"
```

**Key constraints from the API docs:**
- The component and all dependencies (S3, Secrets Manager, Parameter Store) must be in
  `us-east-1`.
- All component parameters must have `default` values — AWS Marketplace runs a headless
  ingestion test pipeline.
- Component ARN build version must be `1`.
- Max 5 unique component names per product (across all versions).

### Overview

Add Image Builder component product support to `awsmp` by following the same layered
pattern: `models.py` → `changesets.py` → `_driver.py` → `cli.py`. The component script
(EC2 Image Builder component document YAML) is embedded in the config file. `awsmp` creates
the component via boto3 `imagebuilder` (obtaining the ARN), then submits the CAPI changeset.

### Two-phase workflow

```
listing_configuration.yaml
        │
        ▼
1. boto3 imagebuilder.create_component(data=<script>)  ──► component ARN
                                                               │
                                                               ▼
2. marketplace-catalog.start_change_set(
     AddDeliveryOptions{Ec2ImageBuilderComponentDeliveryOptionDetails}
     + UpdatePricingTerms
   )
```

### New config schema

All fields are nested under a single top-level `ec2_image_builder:` key. The config loader
reads this key and validates it against `IBProduct`, which has `description`, `region`,
`offer`, and `version` as sub-keys. This makes `ec2_image_builder:` a self-contained
namespace in the config file.

Multiple delivery options per version are supported — the CAPI `AddDeliveryOptions`
`DeliveryOptions` field is an array. Up to 5 unique component names are allowed per
product across all versions.

The `IBProduct` Pydantic model:

```
IBProduct                          # loaded from ec2_image_builder: key
  description:  Description        # reuses existing Description model
  region:       Region             # reuses existing Region model
  offer:        Offer              # reuses existing Offer model
  version:      IBVersion          # IB-specific; analogous to AmiVersion
```

### Changes by file

#### `models.py`

Add new Pydantic models:

- `IBComponent` — inline component creation fields: `name`, `semantic_version`,
  `platform` (`Literal["Linux", "Windows"]`), `supported_os_versions`, `description`,
  and either `document` (raw YAML string passed as `data` to `imagebuilder.create_component`)
  or `arn` (pre-existing ARN, no Image Builder call made). A `model_validator` enforces
  that exactly one of `document` / `arn` is set; when `arn` is provided, the other inline
  fields (`name`, `semantic_version`, etc.) are not required.
- `IBDeliveryOption` — `title: str`, `usage_instructions: str`, `component: IBComponent`
- `IBVersion` — mirrors `AmiVersion` structure but holds the IB-specific delivery fields:
  `version_title`, `release_notes`, `access_role_arn`,
  `delivery_options: list[IBDeliveryOption]` (min 1). No `ami_id`, OS scan, or network
  fields. Validated via `field_validator` that `access_role_arn` matches `arn:aws:iam::`.
  A `model_validator` checks that the number of unique component names across all delivery
  options does not exceed 5.
- `IBProduct` — top-level model loaded from the `ec2_image_builder:` config key:
  `description: Description`, `region: Region`, `offer: Offer`, `version: IBVersion`.

#### `changesets.py`

Add:

- `_changeset_add_ib_delivery_options(product_id, ib_version, component_arns)`
  — constructs `AddDeliveryOptions` with a `DeliveryOptions` array, one entry per
  `IBDeliveryOption` in `ib_version.delivery_options`, using each option's `title`,
  `usage_instructions`, the corresponding resolved `component_arns[i]`, and
  `ib_version.access_role_arn`
- `_changeset_restrict_ib_delivery_options(product_id, delivery_option_ids)`
  — constructs `RestrictDeliveryOptions`
- `get_ib_listing_add_version_changesets(product_id, offer_id, ib_product)`
  — accepts an `IBProduct`; calls `publish_component` for each delivery option to collect
  a list of ARNs, then returns `[AddDeliveryOptions, UpdatePricingTerms]`
  (pricing reuses existing `_changeset_update_pricing_terms` with `ib_product.offer.instance_types`)
- `get_ib_listing_restrict_version_changesets(product_id, delivery_option_ids)`
  — returns `[RestrictDeliveryOptions]`

#### `_driver.py`

Add `IbProduct` class (mirrors `AmiProduct`):

```python
class IbProduct:
    def __init__(self, product_id: str, dry_run: bool = False): ...

    def publish_component(self, ib_product: models.IBProduct) -> str:
        """Creates the component via imagebuilder.create_component(data=document)
        and returns the ARN. If ib_product.ec2_image_builder.component.arn is set,
        returns it directly without making an API call.
        In dry-run mode, prints the would-be payload and returns a placeholder ARN."""

    def publish_components(self, ib_product: models.IBProduct) -> list[str]:
        """Calls publish_component for each delivery option in
        ib_product.ec2_image_builder.delivery_options and returns the list of ARNs
        in the same order."""

    def add_version(self, ib_product: models.IBProduct, allow_price_change: bool) -> ChangeSetReturnType:
        """Calls publish_components to obtain ARNs for all delivery options, then submits
        AddDeliveryOptions + UpdatePricingTerms in one start_change_set call."""

    def restrict_version(self, delivery_option_ids: list[str]) -> ChangeSetReturnType:
        """Submits RestrictDeliveryOptions changeset."""
```

Add `get_ib_client()` — returns a boto3 `imagebuilder` client pinned to `us-east-1`.

#### `cli.py`

Add a new `image-builder` command group:

| Command | Description |
|---|---|
| `image-builder add-version` | Create IB component(s) then submit `AddDeliveryOptions` + `UpdatePricingTerms` |
| `image-builder restrict-version` | Submit `RestrictDeliveryOptions` for given delivery option IDs |

Example:
```
awsmp image-builder add-version \
    --product-id prod-xxxxx \
    --config listing_configuration.yaml \
    [--allow-price-change] \
    [--dry-run]

awsmp image-builder restrict-version \
    --product-id prod-xxxxx \
    --delivery-option-id do-xxxxx \
    [--dry-run]
```

Config loading follows the existing `_load_configuration` pattern, requiring
`[["ec2_image_builder"]]` as the single top-level key. All sub-keys (`description`,
`region`, `offer`, `version`) are validated as part of `IBProduct`.

---

### Key implementation notes

1. **Component ARN or inline document** — for each `IBDeliveryOption`, if
   `component.arn` is set, `publish_component` is a no-op (returns the ARN directly). If
   `component.document` is set, awsmp calls `imagebuilder.create_component(data=document)`
   and returns the ARN. These paths are enforced mutually exclusive by `IBComponent`'s
   `model_validator`. `publish_components` collects results across all delivery options.

2. **`AddDeliveryOptions` + `UpdatePricingTerms` in one changeset** — required on first
   publish and when adding previously unsupported instance types. Reuse existing
   `_changeset_update_pricing_terms` (already handles hourly + annual terms).
   When `offer.instance_types` is empty (free product), omit `UpdatePricingTerms`.

3. **Dry-run** — `publish_component` prints the would-be `create_component` payload and
   returns a placeholder ARN; `get_response` already handles `dry_run` for the CAPI call.

4. **`access_role_arn`** lives at `ec2_image_builder.version.access_role_arn` (same field
   name as in `AmiVersion`); injected into every `Ec2ImageBuilderComponentDeliveryOptionDetails`
   entry at submission time (all delivery options in a version share the same ingestion role).

5. **Pricing diff guard** — reuse `_get_pricing_diff` / `allow_price_change` logic from
   `_get_instance_type_changeset_and_pricing_diff` to prevent accidental price changes.

6. **Config loading** — `_load_configuration` requires `[["ec2_image_builder"]]`; the entire
   config is parsed as `IBProduct` from that key.

---

### Todos

1. Add `IBComponent`, `IBDeliveryOption`, `IBVersion`, `IBProduct` Pydantic models in
   `models.py` (`IBProduct` mirrors `AmiProduct`: `description`, `region`, `offer`,
   `ec2_image_builder`; `IBVersion.delivery_options` is a list; `IBVersion` validates
   max 5 unique component names)
2. Add `_changeset_add_ib_delivery_options` and `_changeset_restrict_ib_delivery_options` in
   `changesets.py`
3. Add `get_ib_listing_add_version_changesets` and `get_ib_listing_restrict_version_changesets`
   in `changesets.py`
4. Add `get_ib_client()` and `IbProduct` class in `_driver.py`
5. Implement `IbProduct.publish_component` (boto3 `imagebuilder.create_component` or direct
   ARN pass-through, dry-run aware) and `IbProduct.publish_components` (iterates delivery
   options)
6. Implement `IbProduct.add_version` (full pipeline)
7. Implement `IbProduct.restrict_version`
8. Add `image-builder` CLI group with `add-version` and `restrict-version` commands in
   `cli.py`
9. Add unit tests for new models (validation, `IBComponent` mutual exclusivity,
   `access_role_arn` format, max-5-component-names enforcement)
10. Add unit tests for new changeset builders
11. Add unit tests for `publish_component` ARN pass-through and dry-run paths
12. Update `README.rst` with new commands and config schema
