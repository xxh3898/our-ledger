package io.github.xxh3898.ourledger.api;

import java.util.List;

public record ApiErrorResponse(
        String code,
        String message,
        List<FieldError> fieldErrors
) {

    public static ApiErrorResponse of(ApiErrorCode code) {
        return new ApiErrorResponse(code.name(), code.message(), List.of());
    }

    public record FieldError(String field, String code, String message) {
    }
}
