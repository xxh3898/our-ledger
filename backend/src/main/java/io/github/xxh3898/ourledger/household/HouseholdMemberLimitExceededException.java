package io.github.xxh3898.ourledger.household;

public class HouseholdMemberLimitExceededException extends RuntimeException {

    public HouseholdMemberLimitExceededException() {
        super("하나의 Household에는 최대 2명만 참여할 수 있습니다.");
    }
}
