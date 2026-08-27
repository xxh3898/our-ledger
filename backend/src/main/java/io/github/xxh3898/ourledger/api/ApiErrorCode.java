package io.github.xxh3898.ourledger.api;

public enum ApiErrorCode {
    AUTHENTICATION_REQUIRED("인증이 필요합니다."),
    ACCESS_DENIED("접근 권한이 없습니다."),
    USER_NOT_REGISTERED("등록된 사용자가 아닙니다."),
    USER_DISABLED("비활성화된 사용자입니다."),
    HOUSEHOLD_MEMBERSHIP_REQUIRED("Household 멤버십이 필요합니다."),
    HOUSEHOLD_MEMBERSHIP_AMBIGUOUS("현재 Household를 하나로 결정할 수 없습니다."),
    CSRF_TOKEN_INVALID("요청 위조 방지 token이 없거나 유효하지 않습니다."),
    INVALID_REQUEST("요청 형식을 확인해 주세요."),
    RESOURCE_NOT_FOUND("현재 Household에서 리소스를 찾을 수 없습니다."),
    RESOURCE_STATE_CONFLICT("현재 상태에서 요청을 처리할 수 없습니다."),
    CATEGORY_NAME_CONFLICT("같은 유형의 활성 Category 이름이 이미 존재합니다."),
    CATEGORY_GROUP_TYPE_MISMATCH("Category와 Group의 유형이 일치해야 합니다."),
    ARCHIVED_CATEGORY_GROUP_NOT_ALLOWED("보관된 Category Group을 새 Category에 사용할 수 없습니다."),
    CATEGORY_TYPE_MISMATCH("Transaction과 Category의 유형이 일치해야 합니다."),
    ARCHIVED_ACCOUNT_NOT_ALLOWED("보관된 Account는 새 거래에 사용할 수 없습니다."),
    ARCHIVED_CATEGORY_NOT_ALLOWED("보관된 Category는 새 거래에 사용할 수 없습니다."),
    TRANSACTION_INVALID_SCOPE("Transaction scope와 owner 조합이 올바르지 않습니다."),
    TRANSACTION_VERSION_CONFLICT("다른 변경이 먼저 반영되어 최신 거래를 다시 조회해야 합니다."),
    TRANSACTION_ENTRY_SET_INVALID("Transaction의 Account Entry 구성이 올바르지 않습니다."),
    TRANSFER_SAME_ACCOUNT_NOT_ALLOWED("이체 source와 destination은 달라야 합니다."),
    UNSUPPORTED_TRANSFER_SOURCE("LIABILITY Account에서는 이체를 시작할 수 없습니다."),
    CREDIT_CARD_NATURE_REQUIRED("CREDIT_CARD Account의 nature는 LIABILITY여야 합니다."),
    UNSUPPORTED_ADJUSTMENT_TYPE("현재 Slice에서 지원하지 않는 adjustment입니다."),
    UNSUPPORTED_ACCOUNT_POSTING("이 Transaction 유형에서 지원하지 않는 Account posting입니다.");

    private final String message;

    ApiErrorCode(String message) {
        this.message = message;
    }

    public String message() {
        return message;
    }
}
