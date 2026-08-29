package io.github.xxh3898.ourledger.account;

import org.springframework.stereotype.Service;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
public class AccountBalanceService {

    private final AccountRepository accountRepository;

    public AccountBalanceService(AccountRepository accountRepository) {
        this.accountRepository = accountRepository;
    }

    public long currentBalance(Account account) {
        long delta = accountRepository.sumActiveBalanceDelta(
                account.getHouseholdId(), account.getId());
        return Math.addExact(account.getOpeningBalance(), delta);
    }

    public Map<Long, AccountBalance> currentBalances(List<Account> accounts) {
        if (accounts.isEmpty()) {
            return Map.of();
        }
        Long householdId = accounts.getFirst().getHouseholdId();
        if (accounts.stream().anyMatch(account -> !householdId.equals(account.getHouseholdId()))) {
            throw new IllegalArgumentException("같은 Household의 Account만 함께 계산할 수 있습니다.");
        }
        Map<Long, Long> deltas = new LinkedHashMap<>();
        for (AccountRepository.AccountBalanceDelta item
                : accountRepository.sumActiveBalanceDeltas(householdId)) {
            deltas.put(item.getAccountId(), item.getLedgerDelta());
        }
        Map<Long, AccountBalance> balances = new LinkedHashMap<>();
        for (Account account : accounts) {
            long ledgerDelta = deltas.getOrDefault(account.getId(), 0L);
            balances.put(
                    account.getId(),
                    new AccountBalance(
                            ledgerDelta,
                            Math.addExact(account.getOpeningBalance(), ledgerDelta)
                    )
            );
        }
        return Map.copyOf(balances);
    }

    public record AccountBalance(long ledgerDelta, long currentBalance) {
    }
}
