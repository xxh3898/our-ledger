package io.github.xxh3898.ourledger.security;

import io.github.xxh3898.ourledger.api.ApiErrorCode;
import io.github.xxh3898.ourledger.api.ApiErrorResponse;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.MediaType;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

final class SecurityJsonResponseWriter {

    private SecurityJsonResponseWriter() {
    }

    static void write(HttpServletResponse response, int status, ApiErrorCode code) throws IOException {
        ApiErrorResponse error = ApiErrorResponse.of(code);
        response.setStatus(status);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.getWriter().write("{\"code\":\"" + error.code()
                + "\",\"message\":\"" + error.message()
                + "\",\"fieldErrors\":[]}");
    }
}
