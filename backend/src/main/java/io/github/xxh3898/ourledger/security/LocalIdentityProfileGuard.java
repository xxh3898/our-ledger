package io.github.xxh3898.ourledger.security;

import org.springframework.beans.factory.InitializingBean;
import org.springframework.context.annotation.Profile;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

import java.util.Arrays;

@Component
@Profile({"local", "test"})
public class LocalIdentityProfileGuard implements InitializingBean {

    private final Environment environment;

    public LocalIdentityProfileGuard(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void afterPropertiesSet() {
        if (Arrays.asList(environment.getActiveProfiles()).contains("production")) {
            throw new IllegalStateException(
                    "production profile과 local/test identity profile을 함께 활성화할 수 없습니다."
            );
        }
    }
}
