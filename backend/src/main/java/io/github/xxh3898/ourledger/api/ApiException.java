package io.github.xxh3898.ourledger.api;

import org.springframework.http.HttpStatus;

import java.util.List;

public class ApiException extends RuntimeException {

    private final HttpStatus status;
    private final ApiErrorCode code;
    private final List<ApiErrorResponse.FieldError> fieldErrors;

    public ApiException(HttpStatus status, ApiErrorCode code) {
        this(status, code, List.of());
    }

    public ApiException(
            HttpStatus status,
            ApiErrorCode code,
            List<ApiErrorResponse.FieldError> fieldErrors
    ) {
        super(code.message());
        this.status = status;
        this.code = code;
        this.fieldErrors = List.copyOf(fieldErrors);
    }

    public HttpStatus status() {
        return status;
    }

    public ApiErrorCode code() {
        return code;
    }

    public List<ApiErrorResponse.FieldError> fieldErrors() {
        return fieldErrors;
    }
}
