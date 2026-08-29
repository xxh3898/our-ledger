#!/usr/bin/env python3

from __future__ import annotations

import json
import sys


EXPECTED_COUNTS = {
    "users": 2,
    "households": 1,
    "householdMembers": 2,
    "accounts": 3,
    "categoryGroups": 2,
    "categories": 2,
    "transactions": 5,
    "transactionAccountEntries": 6,
    "budgets": 1,
    "recurringTransactions": 1,
    "recurringTransactionAccounts": 1,
    "goals": 1,
    "goalAccounts": 1,
}

EXPECTED = {
    "flywayVersions": "1,2,3,4,5,6,7,8",
    "checkingBalance": 105000,
    "savingsBalance": 230000,
    "liabilityBalance": 15000,
    "totalAssets": 335000,
    "totalLiabilities": 15000,
    "netWorth": 320000,
    "refundLineageCount": 1,
    "transferEntryCount": 2,
    "goalStartingBalance": 230000,
    "transactionEvidence": (
        "5001:INCOME:100000:NORMAL:null,"
        "5002:EXPENSE:20000:NORMAL:null,"
        "5003:EXPENSE:15000:NORMAL:null,"
        "5004:TRANSFER:30000:NORMAL:null,"
        "5005:EXPENSE:5000:REFUND:5002"
    ),
    "entryEvidence": (
        "5001:4101:PRIMARY:100000,"
        "5002:4101:PRIMARY:-20000,"
        "5003:4103:PRIMARY:15000,"
        "5004:4101:SOURCE:-30000,"
        "5004:4102:DESTINATION:30000,"
        "5005:4101:PRIMARY:5000"
    ),
}


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


try:
    state = json.load(sys.stdin)
except json.JSONDecodeError:
    fail("fixture state fingerprint가 valid JSON이 아닙니다.")

if not isinstance(state, dict):
    fail("fixture state fingerprint는 JSON object여야 합니다.")
if state.get("rowCounts") != EXPECTED_COUNTS:
    fail("fixture core table row count가 expected contract와 다릅니다.")
for field, expected in EXPECTED.items():
    if state.get(field) != expected:
        fail(f"fixture financial/state field가 expected contract와 다릅니다: {field}")

print("Synthetic fixture state 검산을 통과했습니다.")
