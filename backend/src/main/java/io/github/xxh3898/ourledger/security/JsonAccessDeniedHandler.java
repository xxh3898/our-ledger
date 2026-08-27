package io.github.xxh3898.ourledger.security;

import io.github.xxh3898.ourledger.api.ApiErrorCode;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.security.web.csrf.CsrfException;

import java.io.IOException;

public class JsonAccessDeniedHandler implements AccessDeniedHandler {

    @Override
    public void handle(
            HttpServletRequest request,
            HttpServletResponse response,
            AccessDeniedException accessDeniedException
    ) throws IOException, ServletException {
        ApiErrorCode code = accessDeniedException instanceof CsrfException
                ? ApiErrorCode.CSRF_TOKEN_INVALID
                : ApiErrorCode.ACCESS_DENIED;
        SecurityJsonResponseWriter.write(response, HttpServletResponse.SC_FORBIDDEN, code);
    }
}
