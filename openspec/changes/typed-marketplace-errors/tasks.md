## 1. Add new exception classes

- [ ] 1.1 Add `ResourceInUseException(AWSException)` to `awsmp/errors.py`, accepting the raw AWS error message and using it as the exception's string representation.
- [ ] 1.2 Add `ServiceQuotaExceededException(AWSException)` to `awsmp/errors.py`, accepting the raw AWS error message and using it as the exception's string representation.
- [ ] 1.3 Add `MarketplaceAPIException(AWSException)` to `awsmp/errors.py`, accepting the raw AWS error `code` and `message`, exposing both as attributes (e.g. `.code`, and the message via `str(exception)`).

## 2. Wire up dispatch in `_raise_client_error`

- [ ] 2.1 In `awsmp/_driver.py::_raise_client_error`, add an `elif exception_code == "ResourceInUseException":` branch that logs the error and raises `ResourceInUseException(error_msg)`.
- [ ] 2.2 Add an `elif exception_code == "ServiceQuotaExceededException":` branch that logs the error and raises `ServiceQuotaExceededException(error_msg)`.
- [ ] 2.3 Replace the final `else: logger.exception(error_msg); raise Exception` fallback with `raise MarketplaceAPIException(exception_code, error_msg)`, preserving the existing `logger.exception(error_msg)` call before raising.
- [ ] 2.4 Update the imports in `awsmp/_driver.py` to include the three new exception classes from `.errors`.

## 3. Tests

- [ ] 3.1 In `tests/test_driver.py`, add a test that mocks `get_client().start_change_set` (or another `_raise_client_error` call site) to raise a `ClientError` with `Error.Code == "ResourceInUseException"` and asserts `awsmp.errors.ResourceInUseException` is raised with the original message preserved.
- [ ] 3.2 Add a test for `Error.Code == "ServiceQuotaExceededException"` asserting `awsmp.errors.ServiceQuotaExceededException` is raised with the original message preserved.
- [ ] 3.3 Add a test for an unmapped `Error.Code` (e.g. `"ThrottlingException"`) asserting `awsmp.errors.MarketplaceAPIException` is raised, with `.code` equal to the raw AWS error code and the message preserved.
- [ ] 3.4 Add a test asserting all three new exceptions are instances of `awsmp.errors.AWSException`.
- [ ] 3.5 Run the existing `tests/test_driver.py` suite and confirm no existing tests (e.g. the `AccessDeniedException`/`ResourceNotFoundException` dispatch tests) regress.

## 4. Documentation

- [ ] 4.1 Check `docs/` for any existing documentation of `awsmp` exception types or error-handling behavior; update if present to mention the new exception types and the `MarketplaceAPIException` fallback behavior change.
