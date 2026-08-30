package io.github.xxh3898.ourledger;

import io.github.xxh3898.ourledger.bootstrap.HouseholdBootstrapConfiguration;
import io.github.xxh3898.ourledger.bootstrap.HouseholdBootstrapRequest;
import io.github.xxh3898.ourledger.bootstrap.HouseholdBootstrapService;
import org.junit.jupiter.api.Test;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.DefaultApplicationArguments;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

class HouseholdBootstrapConfigurationTest {

    private final HouseholdBootstrapService bootstrapService = mock(HouseholdBootstrapService.class);

    private final ApplicationContextRunner contextRunner = new ApplicationContextRunner()
            .withUserConfiguration(HouseholdBootstrapConfiguration.class)
            .withBean(HouseholdBootstrapService.class, () -> bootstrapService);

    @Test
    void should_notRegisterRunner_when_bootstrapPropertyIsDisabled() {
        contextRunner
                .withPropertyValues("our-ledger.bootstrap.enabled=false")
                .run(context -> {
                    assertThat(context.containsBean("householdBootstrapRunner")).isFalse();
                    verifyNoInteractions(bootstrapService);
                });
    }

    @Test
    void should_provisionConfiguredUsers_when_bootstrapPropertyIsExplicitlyEnabled() {
        contextRunner
                .withPropertyValues(
                        "our-ledger.bootstrap.enabled=true",
                        "our-ledger.bootstrap.household-name=테스트 Household",
                        "our-ledger.bootstrap.owner.email=owner@example.test",
                        "our-ledger.bootstrap.owner.display-name=Owner",
                        "our-ledger.bootstrap.member.email=member@example.test",
                        "our-ledger.bootstrap.member.display-name=Member"
                )
                .run(context -> {
                    ApplicationRunner runner = context.getBean(
                            "householdBootstrapRunner",
                            ApplicationRunner.class
                    );
                    runner.run(new DefaultApplicationArguments(new String[0]));

                    verify(bootstrapService).provision(new HouseholdBootstrapRequest(
                            "테스트 Household",
                            "owner@example.test",
                            "Owner",
                            "member@example.test",
                            "Member"
                    ));
                });
    }
}
