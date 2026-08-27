package io.github.xxh3898.ourledger.household;

import io.github.xxh3898.ourledger.api.ApiErrorCode;
import io.github.xxh3898.ourledger.api.ApiException;
import io.github.xxh3898.ourledger.security.CurrentHousehold;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class HouseholdMemberResolver {

    private final HouseholdMemberRepository householdMemberRepository;

    public HouseholdMemberResolver(HouseholdMemberRepository householdMemberRepository) {
        this.householdMemberRepository = householdMemberRepository;
    }

    @Transactional(readOnly = true)
    public HouseholdMember require(Long householdId, Long memberId) {
        if (memberId == null) {
            throw notFound();
        }
        return householdMemberRepository.findByIdAndHousehold_Id(memberId, householdId)
                .orElseThrow(this::notFound);
    }

    @Transactional(readOnly = true)
    public HouseholdMember requireCurrent(CurrentHousehold currentHousehold) {
        return householdMemberRepository.findByHousehold_IdAndUser_Id(
                        currentHousehold.householdId(),
                        currentHousehold.userId()
                )
                .orElseThrow(this::notFound);
    }

    private ApiException notFound() {
        return new ApiException(HttpStatus.NOT_FOUND, ApiErrorCode.RESOURCE_NOT_FOUND);
    }
}
