package io.github.xxh3898.ourledger;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.DockerImageName;

@TestConfiguration(proxyBeanMethods = false)
class TestcontainersConfiguration {

    @Bean
    @ServiceConnection
    @ConditionalOnProperty(
            prefix = "our-ledger.test",
            name = "database",
            havingValue = "testcontainers",
            matchIfMissing = true
    )
    PostgreSQLContainer postgresContainer() {
        return new PostgreSQLContainer(DockerImageName.parse("postgres:18.6-alpine3.23"))
                .withDatabaseName("our_ledger_test")
                .withUsername("our_ledger_test")
                .withPassword("local-test-only");
    }
}
