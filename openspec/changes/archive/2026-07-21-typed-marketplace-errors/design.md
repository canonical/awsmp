## Context

`awsmp/_driver.py::_raise_client_error` is the single choke point where every
`botocore.exceptions.ClientError` raised by the AWS Marketplace Catalog API
(via `get_response`, `get_entity_details`, `IbProduct.publish_component`,
etc.) gets translated. Today it dispatches on `exception.response["Error"]["Code"]`
and maps 4 codes to typed exceptions defined in `awsmp/errors.py`. Any other
code - including `ResourceInUseException` (entity locked by an in-flight
change set) and `ServiceQuotaExceededException` (concurrent entity update
quota reached, hardcoded at 20 by the AWS service) - falls into an `else`
branch that does `raise Exception` with no code or message attached to the
exception object (the message is only logged via `logger.exception`).

This repo is being positioned as the dependency for a separate orchestration
wrapper package that will manage dozens of listings concurrently, needing to
retry on transient/lock/quota errors and fail fast on permanent ones. That
wrapper cannot be built cleanly without `awsmp` exposing distinct, catchable
exception types for these cases.

## Goals / Non-Goals

**Goals:**
- Add `ResourceInUseException`, `ServiceQuotaExceededException`, and
  `ThrottlingException` as new typed exceptions in `awsmp/errors.py`,
  dispatched from `_raise_client_error` by AWS error code.
- Add `MarketplaceAPIException` as the new fallback exception for any
  `ClientError` code not explicitly mapped, carrying the raw AWS error code
  and message as attributes so callers always have something structured to
  inspect, even for codes not yet explicitly modeled.
- Preserve existing logging behavior (`logger.exception(...)` calls stay in
  place) so operators don't lose visibility into raw AWS error details.

**Non-Goals:**
- No structured parsing of error messages (e.g. no extraction of locked
  entity IDs or change set IDs from `ResourceInUseException` messages, no
  extraction of entity type from `ServiceQuotaExceededException` messages).
  Only exception *type* distinction is in scope for this change.
- No retry, backoff, or circuit-breaker logic added to `awsmp`.
- No quota-checking or active-change-set-counting API added to `awsmp`
  (e.g. no `ListChangeSets`-backed helper). Concurrency/quota awareness is
  entirely the responsibility of the external wrapper package, implemented
  reactively by catching the typed exceptions this change introduces.
- No change to public method signatures on `AmiProduct`, `IbProduct`, or
  module-level functions in `_driver.py`.

## Decisions

### Exception type only, no structured message parsing
Considered parsing `ResourceInUseException` messages into a
`locked_entities: dict[str, list[str]]` attribute and
`ServiceQuotaExceededException` messages into an `entity_type: str`
attribute. Rejected for this change: message parsing is regex-based and
brittle against AWS wording changes, and the consumer (an external wrapper)
does not need per-entity detail to implement quota-aware retry - it only
needs to distinguish "retry this" from "don't retry this" from "unknown."
Keeping exceptions type-only keeps this change small and avoids coupling
`awsmp` to AWS's exact message format. Structured parsing can be added later
as a additive, backward-compatible change if a real consumer need emerges.

### Generic `MarketplaceAPIException` fallback instead of bare `Exception`
The current fallback is `raise Exception` with no attached data - this is a
**BREAKING** change for anyone catching generic `Exception` around `awsmp`
calls expecting to inspect `str(e)` for the AWS-formatted message (that
behavior is preserved, `MarketplaceAPIException`'s message is the original
`error_msg`), but now also exposes `.code` as a structured attribute for any
current or future unmapped AWS error code (e.g. `InternalServiceException`).
This means new AWS error codes automatically get a typed, inspectable
exception without requiring an `awsmp` code change to add support for every
possible code up front.

### `MarketplaceAPIException` extends `AWSException`
`ResourceInUseException`, `ServiceQuotaExceededException`,
`ThrottlingException`, and `MarketplaceAPIException` all extend the existing
`AWSException` base class (already used by `AccessDeniedException`,
`ResourceNotFoundException`, `UnrecognizedClientException`,
`ValidationException`), so existing code that catches `AWSException`
broadly continues to work unchanged, while new code can catch the more
specific new types.

### `ThrottlingException` gets a dedicated type
Unlike other unmapped codes, `ThrottlingException` is common enough under
concurrent/high-volume usage (the exact scenario this change is motivated
by) that requiring wrapper code to fall back to `MarketplaceAPIException`
and check `.code == "ThrottlingException"` string-matching defeats the
purpose of this change. It is mapped to its own `ThrottlingException` type
alongside `ResourceInUseException` and `ServiceQuotaExceededException`.

### No new public API surface beyond exception classes
`count_active_entities`, `is_entity_locked`, and similar quota/lock-checking
helpers were considered during exploration and explicitly rejected for this
change per stakeholder decision - the wrapper package will implement
retry/backoff/concurrency limiting entirely by catching
`ResourceInUseException` / `ServiceQuotaExceededException` /
`ThrottlingException` reactively on `StartChangeSet` failures, not by
pre-checking state.

## Risks / Trade-offs

- [Risk] Callers currently catching bare `Exception` around `awsmp` calls
  and doing `type(e) == Exception` identity checks (unlikely but possible)
  would break. → Mitigation: this is called out as **BREAKING** in the
  proposal; `isinstance(e, Exception)` checks continue to work since
  `MarketplaceAPIException` is still an `Exception` subclass.
- [Risk] Without structured message parsing, a wrapper package still has to
  do its own regex/string parsing if it ever needs entity-level lock detail
  (e.g. to retry only the specific locked entity rather than the whole
  batch). → Mitigation: accepted trade-off per stakeholder decision; can be
  added later as an additive change if needed.
- [Risk] Other transient AWS error codes (e.g. `InternalServiceException`)
  are not explicitly named as top-level exceptions in this change, so they
  will be raised as `MarketplaceAPIException` rather than a
  distinctly-named exception, requiring wrapper code to check `.code`
  rather than `isinstance`. → Mitigation: acceptable for this change's
  scope; `.code` is available for that check, and dedicated exception
  types can be added later without breaking changes if they prove
  valuable. `ThrottlingException` is common enough to warrant its own type
  now (added below); other codes are deferred.

## Migration Plan

- This is a library-level change with no data migration. Deploy as a normal
  version bump of `awsmp`.
- Callers (including the planned external wrapper package) should update
  any `except Exception` handling around `awsmp` driver calls to catch the
  new typed exceptions (`ResourceInUseException`,
  `ServiceQuotaExceededException`, `MarketplaceAPIException`) or the existing
  `AWSException` base class where broad handling is desired.
- No rollback complexity beyond a normal version revert, since no schema or
  state changes are involved.

## Open Questions

- None blocking. Whether additional dedicated exception types beyond
  `ThrottlingException` are worth adding can be revisited once the wrapper
  package is built and exercised against real AWS error behavior.
