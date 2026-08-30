package io.github.xxh3898.ourledger.export;

public record TransactionCsvDocument(byte[] content, String filename) {

    public TransactionCsvDocument {
        content = content.clone();
    }

    @Override
    public byte[] content() {
        return content.clone();
    }
}
