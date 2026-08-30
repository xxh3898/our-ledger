package io.github.xxh3898.ourledger.bootstrap;

import org.junit.jupiter.api.Test;

import java.io.ByteArrayInputStream;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class ProductionBootstrapInputParserTest {

    private static final String VALID_JSON = """
            {
              "formatVersion": 1,
              "householdName": "테스트 Household",
              "owner": {"email": " Owner@Example.Test ", "displayName": " Owner "},
              "member": {"email": "member@example.test", "displayName": "Member"}
            }
            """;

    private final ProductionBootstrapInputParser parser =
            new ProductionBootstrapInputParser();

    @Test
    void should_parseAndNormalizeRequest_when_exactProtocolIsProvided() {
        HouseholdBootstrapRequest request = parse(VALID_JSON);

        assertThat(request).isEqualTo(new HouseholdBootstrapRequest(
                "테스트 Household",
                "owner@example.test",
                "Owner",
                "member@example.test",
                "Member"
        ));
    }

    @Test
    void should_rejectInput_when_protocolShapeIsInvalid() {
        String[] invalidInputs = {
                "",
                "   ",
                "[]",
                "{}",
                "{\"formatVersion\":2,\"householdName\":\"H\",\"owner\":{\"email\":\"a\",\"displayName\":\"A\"},\"member\":{\"email\":\"b\",\"displayName\":\"B\"}}",
                "{\"formatVersion\":1,\"householdName\":\"H\",\"owner\":{\"email\":\"a\",\"displayName\":\"A\"},\"member\":{\"email\":\"b\",\"displayName\":\"B\"},\"unknown\":true}",
                "{\"formatVersion\":1,\"formatVersion\":1,\"householdName\":\"H\",\"owner\":{\"email\":\"a\",\"displayName\":\"A\"},\"member\":{\"email\":\"b\",\"displayName\":\"B\"}}",
                "{\"formatVersion\":1,\"owner\":{\"email\":\"a\",\"displayName\":\"A\"},\"member\":{\"email\":\"b\",\"displayName\":\"B\"}}",
                "{\"formatVersion\":1,\"householdName\":null,\"owner\":{\"email\":\"a\",\"displayName\":\"A\"},\"member\":{\"email\":\"b\",\"displayName\":\"B\"}}",
                "{\"formatVersion\":\"1\",\"householdName\":\"H\",\"owner\":{\"email\":\"a\",\"displayName\":\"A\"},\"member\":{\"email\":\"b\",\"displayName\":\"B\"}}",
                "{\"formatVersion\":1,\"householdName\":\"H\",\"owner\":{\"email\":\"a\",\"displayName\":\"A\",\"unknown\":true},\"member\":{\"email\":\"b\",\"displayName\":\"B\"}}",
                "{\"formatVersion\":1,\"householdName\":\"H\",\"owner\":{\"email\":\"same@example.test\",\"displayName\":\"A\"},\"member\":{\"email\":\"SAME@example.test\",\"displayName\":\"B\"}}",
                VALID_JSON + "{}"
        };

        for (String input : invalidInputs) {
            assertThatThrownBy(() -> parse(input))
                    .isExactlyInstanceOf(ProductionBootstrapInputException.class)
                    .hasMessage("bootstrap stdin 계약이 유효하지 않습니다.");
        }
    }

    @Test
    void should_rejectInput_when_byteBoundaryOrUtf8IsInvalid() {
        byte[] oversized = " ".repeat(ProductionBootstrapInputParser.MAX_INPUT_BYTES + 1)
                .getBytes(StandardCharsets.UTF_8);
        byte[] invalidUtf8 = {(byte) 0xC3, (byte) 0x28};

        for (byte[] input : new byte[][]{oversized, invalidUtf8}) {
            assertThatThrownBy(() -> parser.parse(new ByteArrayInputStream(input)))
                    .isExactlyInstanceOf(ProductionBootstrapInputException.class)
                    .hasMessage("bootstrap stdin 계약이 유효하지 않습니다.");
        }
    }

    @Test
    void should_rejectInput_when_validJsonUsesNonUtf8UnicodeEncoding() {
        String[] nonUtf8Encodings = {
                "UTF-16LE",
                "UTF-16BE",
                "UTF-32LE",
                "UTF-32BE"
        };

        for (String encoding : nonUtf8Encodings) {
            byte[] input = VALID_JSON.getBytes(Charset.forName(encoding));

            assertThatThrownBy(() -> parser.parse(new ByteArrayInputStream(input)))
                    .as("encoding=%s", encoding)
                    .isExactlyInstanceOf(ProductionBootstrapInputException.class)
                    .hasMessage("bootstrap stdin 계약이 유효하지 않습니다.");
        }
    }

    @Test
    void should_notExposeInputValues_when_parsingFails() {
        String privateValue = "private-owner@example.test";
        String malformed = "{\"formatVersion\":1,\"householdName\":\"Secret\","
                + "\"owner\":{\"email\":\"" + privateValue + "\"}}";

        assertThatThrownBy(() -> parse(malformed))
                .isExactlyInstanceOf(ProductionBootstrapInputException.class)
                .hasMessageNotContaining(privateValue)
                .hasMessageNotContaining("Secret");
    }

    private HouseholdBootstrapRequest parse(String input) {
        return parser.parse(new ByteArrayInputStream(input.getBytes(StandardCharsets.UTF_8)));
    }
}
