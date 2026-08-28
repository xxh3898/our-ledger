ALTER TABLE accounts
    ADD CONSTRAINT ck_accounts_credit_card_liability
        CHECK (type <> 'CREDIT_CARD' OR nature = 'LIABILITY');
