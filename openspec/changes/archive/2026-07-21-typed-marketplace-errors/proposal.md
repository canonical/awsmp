## Why

`awsmp`'s marketplace API error handling collapses most AWS Marketplace Catalog
`ClientError`s into a bare `raise Exception` with no attached error code or
context (see `awsmp/_driver.py::_raise_client_error`). Only 4 error codes
(`AccessDeniedException`, `UnrecognizedClientException`,
`ResourceNotFoundException`, `ValidationException`) are mapped to typed
exceptions today. Notably, `ResourceInUseException` (entity locked by another
in-flight change set) and `ServiceQuotaExceededException` (concurrent entity
update quota reached) are NOT mapped, so callers building automation on top of
`awsmp` cannot distinguish these transient, retryable failures from any other
error without parsing log output or exception tracebacks. This blocks building
resilient, quota-aware orchestration on top of `awsmp` for managing many
listings at once.

## What Changes

- Add `ResourceInUseException` typed exception (raised for AWS error code
  `ResourceInUseException`, e.g. entity locked by another change set).
- Add `ServiceQuotaExceededException` typed exception (raised for AWS error
  code `ServiceQuotaExceededException`, e.g. concurrent entity update quota
  reached).
- Add `ThrottlingException` typed exception (raised for AWS error code
  `ThrottlingException`, a common transient rate-limiting error).
- Add `MarketplaceAPIException` typed exception used as the fallback for any
  `ClientError` code not otherwise explicitly mapped, carrying the raw AWS
  error code and message. **BREAKING**: replaces the current bare
  `raise Exception` fallback in `_raise_client_error`, so code catching
  generic `Exception` around `awsmp` driver calls will now receive a more
  specific (but still broadly-typed) exception instance instead.
- No structured parsing of error messages (e.g. no per-entity lock lists) -
  only exception type distinction is in scope.
- No retry, backoff, or concurrency/quota-checking logic is added to `awsmp`
  itself - that responsibility is left to callers/wrapper packages built on
  top of these typed exceptions.

## Capabilities

### New Capabilities
- `marketplace-error-handling`: Typed exception hierarchy for AWS Marketplace
  Catalog API `ClientError` responses raised by `awsmp`'s driver layer,
  including a generic fallback exception that preserves the original AWS
  error code and message for any unmapped error code.

### Modified Capabilities
(none - no existing specs are being modified; this is the first tracked
capability for this repo)

## Impact

- Affected code: `awsmp/errors.py` (new exception classes),
  `awsmp/_driver.py::_raise_client_error` (dispatch logic).
- Affected APIs: none (internal error-handling change only; public function
  signatures are unchanged).
- Consumers: any external automation/wrapper code that calls into `awsmp`'s
  driver layer (e.g. `AmiProduct.update`, `get_response`) and catches
  exceptions should be updated to catch the new typed exceptions instead of
  bare `Exception` for `ResourceInUseException` /
  `ServiceQuotaExceededException` / other AWS error codes.
