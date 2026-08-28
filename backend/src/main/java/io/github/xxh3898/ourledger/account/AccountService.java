package io.github.xxh3898.ourledger.account;

import io.github.xxh3898.ourledger.api.ApiErrorCode;
import io.github.xxh3898.ourledger.api.ApiException;
import io.github.xxh3898.ourledger.api.RequestValidator;
import io.github.xxh3898.ourledger.household.HouseholdMember;
import io.github.xxh3898.ourledger.household.HouseholdMemberResolver;
import io.github.xxh3898.ourledger.recurring.RecurringReferenceGuard;
import io.github.xxh3898.ourledger.security.CurrentHousehold;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
public class AccountService {

    private static final String KRW = "KRW";

    private final AccountRepository accountRepository;
    private final HouseholdMemberResolver householdMemberResolver;
    private final RecurringReferenceGuard recurringReferenceGuard;

    public AccountService(
            AccountRepository accountRepository,
            HouseholdMemberResolver householdMemberResolver,
            RecurringReferenceGuard recurringReferenceGuard
    ) {
        this.accountRepository = accountRepository;
        this.householdMemberResolver = householdMemberResolver;
        this.recurringReferenceGuard = recurringReferenceGuard;
    }

    @Transactional(readOnly = true)
    public List<AccountResponse> findAll(CurrentHousehold currentHousehold, boolean includeArchived) {
        List<Account> accounts = includeArchived
                ? accountRepository.findAllByHouseholdIdOrderBySortOrderAscIdAsc(
                        currentHousehold.householdId())
                : accountRepository.findAllByHouseholdIdAndArchivedAtIsNullOrderBySortOrderAscIdAsc(
                        currentHousehold.householdId());
        return accounts.stream().map(this::toResponse).toList();
    }

    @Transactional
    public AccountResponse create(CurrentHousehold currentHousehold, AccountCreateRequest request) {
        validate(
                request.name(),
                request.institution(),
                request.type(),
                request.nature(),
                request.ownership(),
                request.ownerMemberId(),
                request.openingBalance(),
                request.openingBalanceAsOf(),
                request.currency(),
                request.lastFour(),
                request.savingsEnabled(),
                request.sortOrder()
        );
        requireOwner(currentHousehold.householdId(), request.ownership(), request.ownerMemberId());
        Account account = accountRepository.saveAndFlush(Account.create(
                currentHousehold.householdId(),
                request.name(),
                request.institution(),
                request.type(),
                request.nature(),
                request.ownership(),
                request.ownerMemberId(),
                request.openingBalance(),
                request.openingBalanceAsOf(),
                request.currency(),
                request.lastFour(),
                request.savingsEnabled(),
                request.sortOrder()
        ));
        return toResponse(account);
    }

    @Transactional
    public AccountResponse update(
            CurrentHousehold currentHousehold,
            Long accountId,
            AccountUpdateRequest request
    ) {
        validate(
                request.name(),
                request.institution(),
                request.type(),
                request.nature(),
                request.ownership(),
                request.ownerMemberId(),
                request.openingBalance(),
                request.openingBalanceAsOf(),
                request.currency(),
                request.lastFour(),
                request.savingsEnabled(),
                request.sortOrder()
        );
        new RequestValidator().required(request.archived(), "archived").throwIfInvalid();
        requireOwner(currentHousehold.householdId(), request.ownership(), request.ownerMemberId());
        Account account = requireAccountForPosting(currentHousehold.householdId(), accountId);
        recurringReferenceGuard.rejectAccountChange(
                account.getHouseholdId(), account.getId(), request.type(), request.nature(),
                request.archived());
        rejectPostingClassificationChange(account, request.type(), request.nature());
        account.update(
                request.name(),
                request.institution(),
                request.type(),
                request.nature(),
                request.ownership(),
                request.ownerMemberId(),
                request.openingBalance(),
                request.openingBalanceAsOf(),
                request.currency(),
                request.lastFour(),
                request.savingsEnabled(),
                request.sortOrder(),
                request.archived()
        );
        accountRepository.flush();
        return toResponse(account);
    }

    @Transactional(readOnly = true)
    public Account requireAccount(Long householdId, Long accountId) {
        return accountRepository.findByIdAndHouseholdId(accountId, householdId)
                .orElseThrow(() -> new ApiException(
                        HttpStatus.NOT_FOUND,
                        ApiErrorCode.RESOURCE_NOT_FOUND
                ));
    }

    @Transactional
    public Account requireAccountForPosting(Long householdId, Long accountId) {
        return accountRepository.findByIdAndHouseholdIdForUpdate(accountId, householdId)
                .orElseThrow(() -> new ApiException(
                        HttpStatus.NOT_FOUND,
                        ApiErrorCode.RESOURCE_NOT_FOUND
                ));
    }

    private void rejectPostingClassificationChange(
            Account account,
            AccountType requestedType,
            AccountNature requestedNature
    ) {
        boolean classificationChanged = account.getNature() != requestedNature
                || (account.getType() == AccountType.CREDIT_CARD)
                != (requestedType == AccountType.CREDIT_CARD);
        if (classificationChanged && accountRepository.hasLedgerEntries(
                account.getHouseholdId(), account.getId())) {
            throw new ApiException(
                    HttpStatus.CONFLICT,
                    ApiErrorCode.ACCOUNT_POSTING_CLASSIFICATION_IMMUTABLE
            );
        }
    }

    private void validate(
            String name,
            String institution,
            AccountType type,
            AccountNature nature,
            AccountOwnership ownership,
            Long ownerMemberId,
            Long openingBalance,
            java.time.LocalDate openingBalanceAsOf,
            String currency,
            String lastFour,
            Boolean savingsEnabled,
            Integer sortOrder
    ) {
        RequestValidator validator = new RequestValidator()
                .requiredText(name, "name")
                .required(type, "type")
                .required(nature, "nature")
                .required(ownership, "ownership")
                .required(openingBalance, "openingBalance")
                .required(openingBalanceAsOf, "openingBalanceAsOf")
                .requiredText(currency, "currency")
                .required(savingsEnabled, "savingsEnabled")
                .required(sortOrder, "sortOrder");
        if (name != null) {
            validator.check(name.strip().length() <= 100, "name", "size", "100자 이하여야 합니다.");
        }
        if (institution != null) {
            validator.check(!institution.isBlank() && institution.strip().length() <= 100,
                    "institution", "size", "빈 문자열이 아닌 100자 이하여야 합니다.");
        }
        if (currency != null) {
            validator.check(KRW.equals(currency), "currency", "supported", "KRW만 지원합니다.");
        }
        if (lastFour != null) {
            validator.check(lastFour.matches("[0-9]{4}"), "lastFour", "pattern", "숫자 네 자리여야 합니다.");
        }
        if (sortOrder != null) {
            validator.check(sortOrder >= 0, "sortOrder", "minimum", "0 이상이어야 합니다.");
        }
        if (ownership == AccountOwnership.PERSONAL) {
            validator.required(ownerMemberId, "ownerMemberId");
        } else if (ownership == AccountOwnership.SHARED) {
            validator.check(ownerMemberId == null, "ownerMemberId", "mustBeNull", "SHARED Account에는 owner를 지정하지 않습니다.");
        }
        if (Boolean.TRUE.equals(savingsEnabled)) {
            validator.check(nature == AccountNature.ASSET, "savingsEnabled", "assetOnly", "ASSET Account에만 설정할 수 있습니다.");
        }
        validator.throwIfInvalid();
        if (type == AccountType.CREDIT_CARD && nature != AccountNature.LIABILITY) {
            throw new ApiException(
                    HttpStatus.UNPROCESSABLE_ENTITY,
                    ApiErrorCode.CREDIT_CARD_NATURE_REQUIRED
            );
        }
    }

    private void requireOwner(
            Long householdId,
            AccountOwnership ownership,
            Long ownerMemberId
    ) {
        if (ownership == AccountOwnership.PERSONAL) {
            householdMemberResolver.require(householdId, ownerMemberId);
        }
    }

    private AccountResponse toResponse(Account account) {
        AccountResponse.Owner owner = null;
        if (account.getOwnerMemberId() != null) {
            HouseholdMember member = householdMemberResolver.require(
                    account.getHouseholdId(), account.getOwnerMemberId());
            owner = new AccountResponse.Owner(
                    member.getId(),
                    member.getUser().getId(),
                    member.getUser().getDisplayName()
            );
        }
        long delta = accountRepository.sumActiveBalanceDelta(
                account.getHouseholdId(), account.getId());
        long currentBalance = Math.addExact(account.getOpeningBalance(), delta);
        return new AccountResponse(
                account.getId(),
                account.getName(),
                account.getInstitution(),
                account.getType(),
                account.getNature(),
                account.getOwnership(),
                owner,
                account.getOpeningBalance(),
                account.getOpeningBalanceAsOf(),
                currentBalance,
                account.getCurrency(),
                account.getLastFour(),
                account.isSavingsEnabled(),
                account.getSortOrder(),
                account.isArchived(),
                account.getCreatedAt(),
                account.getUpdatedAt()
        );
    }
}
