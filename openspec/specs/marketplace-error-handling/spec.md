# Marketplace Error Handling

## Purpose
Define the typed exception behavior for AWS Marketplace API errors.

## Requirements

### Requirement: Resource lock errors are raised as a distinct exception type
When the AWS Marketplace Catalog API rejects a `StartChangeSet` (or other)
request with a `ClientError` whose `Error.Code` is
`ResourceInUseException`, `awsmp` SHALL raise a `ResourceInUseException`
Python exception (defined in `awsmp.errors`) instead of a generic
`Exception`.

#### Scenario: StartChangeSet fails because an entity is locked by another change set
- **WHEN** `get_response` calls `start_change_set` and AWS responds with a
  `ClientError` whose `Error.Code` is `ResourceInUseException`
- **THEN** `awsmp` raises `awsmp.errors.ResourceInUseException` and the
  original AWS error message is preserved as the exception's string
  representation

### Requirement: Service quota errors are raised as a distinct exception type
When the AWS Marketplace Catalog API rejects a request with a `ClientError`
whose `Error.Code` is `ServiceQuotaExceededException`, `awsmp` SHALL raise a
`ServiceQuotaExceededException` Python exception (defined in `awsmp.errors`)
instead of a generic `Exception`.

#### Scenario: StartChangeSet fails because the concurrent entity update quota is reached
- **WHEN** `get_response` calls `start_change_set` and AWS responds with a
  `ClientError` whose `Error.Code` is `ServiceQuotaExceededException`
- **THEN** `awsmp` raises `awsmp.errors.ServiceQuotaExceededException` and
  the original AWS error message is preserved as the exception's string
  representation

### Requirement: Unmapped AWS error codes raise a generic typed exception
When the AWS Marketplace Catalog API rejects a request with a `ClientError`
whose `Error.Code` does not match any explicitly-handled code (currently
`AccessDeniedException`, `UnrecognizedClientException`,
`ResourceNotFoundException`, `ValidationException`,
`ResourceInUseException`, `ServiceQuotaExceededException`,
`ThrottlingException`), `awsmp` SHALL raise a `MarketplaceAPIException`
(defined in `awsmp.errors`) carrying the original AWS error code and
message as attributes, instead of raising a bare `Exception` with no
attached data.

#### Scenario: An unmapped AWS error code is returned
- **WHEN** `get_response` calls `start_change_set` and AWS responds with a
  `ClientError` whose `Error.Code` is not one of the explicitly-handled
  codes (e.g. `InternalServiceException`)
- **THEN** `awsmp` raises `awsmp.errors.MarketplaceAPIException` with the
  raw AWS error code accessible on the exception instance and the original
  AWS error message preserved as the exception's string representation

### Requirement: Throttling errors are raised as a distinct exception type
When the AWS Marketplace Catalog API rejects a request with a `ClientError`
whose `Error.Code` is `ThrottlingException`, `awsmp` SHALL raise a
`ThrottlingException` Python exception (defined in `awsmp.errors`) instead
of a generic `Exception` or `MarketplaceAPIException`.

#### Scenario: A request is rejected due to rate limiting
- **WHEN** `get_response` calls `start_change_set` and AWS responds with a
  `ClientError` whose `Error.Code` is `ThrottlingException`
- **THEN** `awsmp` raises `awsmp.errors.ThrottlingException` and the
  original AWS error message is preserved as the exception's string
  representation

### Requirement: New typed exceptions extend the existing AWSException base class
`ResourceInUseException`, `ServiceQuotaExceededException`,
`ThrottlingException`, and `MarketplaceAPIException` SHALL be subclasses of
`awsmp.errors.AWSException`, consistent with the existing typed exceptions
in `awsmp.errors`.

#### Scenario: Catching the shared base class still works
- **WHEN** a caller wraps an `awsmp` driver call in
  `except awsmp.errors.AWSException:`
- **THEN** `ResourceInUseException`, `ServiceQuotaExceededException`,
  `ThrottlingException`, and `MarketplaceAPIException` are all caught by
  that handler
