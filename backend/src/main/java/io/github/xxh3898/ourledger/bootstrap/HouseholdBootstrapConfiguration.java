package io.github.xxh3898.ourledger.bootstrap;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(HouseholdBootstrapProperties.class)
public class HouseholdBootstrapConfiguration {

    @Bean("householdBootstrapRunner")
    @Profile("!migration")
    @ConditionalOnProperty(
            prefix = "our-ledger.bootstrap",
            name = "enabled",
            havingValue = "true"
    )
    ApplicationRunner householdBootstrapRunner(
            HouseholdBootstrapProperties properties,
            HouseholdBootstrapService service
    ) {
        return arguments -> service.provision(properties.toRequest());
    }
}
