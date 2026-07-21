## 1. Add new exception classes

- [x] 1.1 Add `ResourceInUseException(AWSException)` to `awsmp/errors.py`, accepting the raw AWS error message and using it as the exception's string representation.
- [x] 1.2 Add `ServiceQuotaExceededException(AWSException)` to `awsmp/errors.py`, accepting the raw AWS error message and using it as the exception's string representation.
- [x] 1.3 Add `ThrottlingException(AWSException)` to `awsmp/errors.py`, accepting the raw AWS error message and using it as the exception's string representation.
- [x] 1.4 Add `MarketplaceAPIException(AWSException)` to `awsmp/errors.py`, accepting the raw AWS error `code` and `message`, exposing both as attributes (e.g. `.code`, and the message via `str(exception)`).

## 2. Wire up dispatch in `_raise_client_error`

- [x] 2.1 In `awsmp/_driver.py::_raise_client_error`, add an `elif exception_code == "ResourceInUseException":` branch that logs the error and raises `ResourceInUseException(error_msg)`.
- [x] 2.2 Add an `elif exception_code == "ServiceQuotaExceededException":` branch that logs the error and raises `ServiceQuotaExceededException(error_msg)`.
- [x] 2.3 Add an `elif exception_code == "ThrottlingException":` branch that logs the error and raises `ThrottlingException(error_msg)`.
- [x] 2.4 Replace the final `else: logger.exception(error_msg); raise Exception` fallback with `raise MarketplaceAPIException(exception_code, error_msg)`, preserving the existing `logger.exception(error_msg)` call before raising.
- [x] 2.5 Update the imports in `awsmp/_driver.py` to include the four new exception classes from `.errors`.

## 3. Tests

- [x] 3.1 In `tests/test_driver.py`, add a test that mocks `get_client().start_change_set` (or another `_raise_client_error` call site) to raise a `ClientError` with `Error.Code == "ResourceInUseException"` and asserts `awsmp.errors.ResourceInUseException` is raised with the original message preserved.
- [x] 3.2 Add a test for `Error.Code == "ServiceQuotaExceededException"` asserting `awsmp.errors.ServiceQuotaExceededException` is raised with the original message preserved.
- [x] 3.3 Add a test for `Error.Code == "ThrottlingException"` asserting `awsmp.errors.ThrottlingException` is raised with the original message preserved.
- [x] 3.4 Add a test for an unmapped `Error.Code` (e.g. `"InternalServiceException"`) asserting `awsmp.errors.MarketplaceAPIException` is raised, with `.code` equal to the raw AWS error code and the message preserved.
- [x] 3.5 Add a test asserting all four new exceptions are instances of `awsmp.errors.AWSException`.
- [x] 3.6 Run the existing `tests/test_driver.py` suite and confirm no existing tests (e.g. the `AccessDeniedException`/`ResourceNotFoundException` dispatch tests) regress.

## 4. Documentation

- [x] 4.1 Check `docs/` for any existing documentation of `awsmp` exception types or error-handling behavior; update if present to mention the new exception types and the `MarketplaceAPIException` fallback behavior change.
