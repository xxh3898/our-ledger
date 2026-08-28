package io.github.xxh3898.ourledger.account;

import org.springframework.stereotype.Service;

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
}
