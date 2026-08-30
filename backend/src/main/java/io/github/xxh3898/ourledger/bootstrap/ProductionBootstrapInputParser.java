package io.github.xxh3898.ourledger.bootstrap;

import tools.jackson.core.StreamReadFeature;
import tools.jackson.databind.DeserializationFeature;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public final class ProductionBootstrapInputParser {

    public static final int MAX_INPUT_BYTES = 8 * 1024;

    private static final JsonMapper JSON_MAPPER = JsonMapper.builder()
            .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
            .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
            .build();

    public HouseholdBootstrapRequest parse(InputStream input) {
        try {
            byte[] bytes = input.readNBytes(MAX_INPUT_BYTES + 1);
            require(bytes.length > 0 && bytes.length <= MAX_INPUT_BYTES);

            String json = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(bytes))
                    .toString();
            JsonNode root = JSON_MAPPER.readTree(json);
            require(root != null && root.isObject() && root.size() == 4);
            requireFormatVersion(root.get("formatVersion"));
            String householdName = requireText(root.get("householdName"));
            JsonNode owner = requirePerson(root.get("owner"));
            JsonNode member = requirePerson(root.get("member"));

            return new HouseholdBootstrapRequest(
                    householdName,
                    requireText(owner.get("email")),
                    requireText(owner.get("displayName")),
                    requireText(member.get("email")),
                    requireText(member.get("displayName"))
            );
        } catch (ProductionBootstrapInputException exception) {
            throw exception;
        } catch (IOException | RuntimeException exception) {
            throw new ProductionBootstrapInputException();
        }
    }

    private void requireFormatVersion(JsonNode node) {
        require(node != null && node.isIntegralNumber() && node.canConvertToInt());
        require(node.intValue() == 1);
    }

    private JsonNode requirePerson(JsonNode node) {
        require(node != null && node.isObject() && node.size() == 2);
        requireText(node.get("email"));
        requireText(node.get("displayName"));
        return node;
    }

    private String requireText(JsonNode node) {
        require(node != null && node.isTextual());
        return node.textValue();
    }

    private void require(boolean condition) {
        if (!condition) {
            throw new ProductionBootstrapInputException();
        }
    }
}
