package io.github.xxh3898.ourledger.export;

import java.nio.charset.StandardCharsets;
import java.util.List;

final class Rfc4180CsvWriter {

    private static final byte[] UTF_8_BOM = {
            (byte) 0xEF,
            (byte) 0xBB,
            (byte) 0xBF
    };

    private Rfc4180CsvWriter() {
    }

    static byte[] write(List<List<String>> rows) {
        StringBuilder csv = new StringBuilder();
        for (List<String> row : rows) {
            for (int index = 0; index < row.size(); index++) {
                if (index > 0) {
                    csv.append(',');
                }
                csv.append(escape(row.get(index)));
            }
            csv.append("\r\n");
        }
        byte[] content = csv.toString().getBytes(StandardCharsets.UTF_8);
        byte[] result = new byte[UTF_8_BOM.length + content.length];
        System.arraycopy(UTF_8_BOM, 0, result, 0, UTF_8_BOM.length);
        System.arraycopy(content, 0, result, UTF_8_BOM.length, content.length);
        return result;
    }

    static String protectSpreadsheetText(String value) {
        if (value == null) {
            return "";
        }
        String stripped = value.strip();
        if (startsWithFormulaPrefix(value) || startsWithFormulaPrefix(stripped)) {
            return "'" + value;
        }
        return value;
    }

    private static boolean startsWithFormulaPrefix(String value) {
        if (value.isEmpty()) {
            return false;
        }
        return switch (value.charAt(0)) {
            case '=', '+', '-', '@', '\t', '\r' -> true;
            default -> false;
        };
    }

    private static String escape(String value) {
        if (value.indexOf(',') < 0
                && value.indexOf('"') < 0
                && value.indexOf('\r') < 0
                && value.indexOf('\n') < 0) {
            return value;
        }
        return '"' + value.replace("\"", "\"\"") + '"';
    }
}
