package io.github.xxh3898.ourledger.api;

public enum ApiErrorCode {
    AUTHENTICATION_REQUIRED("인증이 필요합니다."),
    ACCESS_DENIED("접근 권한이 없습니다."),
    USER_NOT_REGISTERED("등록된 사용자가 아닙니다."),
    USER_DISABLED("비활성화된 사용자입니다."),
    HOUSEHOLD_MEMBERSHIP_REQUIRED("Household 멤버십이 필요합니다."),
    HOUSEHOLD_MEMBERSHIP_AMBIGUOUS("현재 Household를 하나로 결정할 수 없습니다."),
    CSRF_TOKEN_INVALID("요청 위조 방지 token이 없거나 유효하지 않습니다.");

    private final String message;

    ApiErrorCode(String message) {
        this.message = message;
    }

    public String message() {
        return message;
    }
}
