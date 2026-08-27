package io.github.xxh3898.ourledger.api;

import org.springframework.http.HttpStatus;

import java.util.ArrayList;
import java.util.List;

public final class RequestValidator {

    private final List<ApiErrorResponse.FieldError> errors = new ArrayList<>();

    public RequestValidator required(Object value, String field) {
        if (value == null) {
            reject(field, "required", "필수값입니다.");
        }
        return this;
    }

    public RequestValidator requiredText(String value, String field) {
        if (value == null || value.isBlank()) {
            reject(field, "required", "빈 문자열이 아닌 값이 필요합니다.");
        }
        return this;
    }

    public RequestValidator check(boolean valid, String field, String code, String message) {
        if (!valid) {
            reject(field, code, message);
        }
        return this;
    }

    public void reject(String field, String code, String message) {
        errors.add(new ApiErrorResponse.FieldError(field, code, message));
    }

    public void throwIfInvalid() {
        if (!errors.isEmpty()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, ApiErrorCode.INVALID_REQUEST, errors);
        }
    }
}
