package io.github.xxh3898.ourledger;

import io.github.xxh3898.ourledger.security.LocalIdentityProfileGuard;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class LocalIdentityProfileGuardTest {

    @Test
    void should_failStartup_when_productionAndLocalProfilesAreCombined() {
        new ApplicationContextRunner()
                .withUserConfiguration(LocalIdentityProfileGuard.class)
                .withInitializer(context ->
                        context.getEnvironment().setActiveProfiles("production", "local"))
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure())
                            .hasRootCauseMessage(
                                    "production profile과 local/test identity profile을 함께 활성화할 수 없습니다."
                            );
                });
    }
}
