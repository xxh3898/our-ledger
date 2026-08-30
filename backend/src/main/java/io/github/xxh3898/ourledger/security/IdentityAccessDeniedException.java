package io.github.xxh3898.ourledger.security;

import io.github.xxh3898.ourledger.api.ApiErrorCode;

public class IdentityAccessDeniedException extends RuntimeException {

    private final ApiErrorCode errorCode;

    public IdentityAccessDeniedException(ApiErrorCode errorCode) {
        super(errorCode.message());
        this.errorCode = errorCode;
    }

    public ApiErrorCode getErrorCode() {
        return errorCode;
    }
}
