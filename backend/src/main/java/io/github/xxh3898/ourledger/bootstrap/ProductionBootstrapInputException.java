package io.github.xxh3898.ourledger.bootstrap;

public final class ProductionBootstrapInputException extends IllegalArgumentException {

    private static final String MESSAGE = "bootstrap stdin 계약이 유효하지 않습니다.";

    public ProductionBootstrapInputException() {
        super(MESSAGE);
    }
}
