package io.github.xxh3898.ourledger.ops;

import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class MigrationEnvironmentValidatorTest {

    @Test
    void should_acceptNormalProductionMode_when_schemaMutationIsDisabled() {
        MockEnvironment environment = normalProductionEnvironment();

        assertThatCode(() -> MigrationEnvironmentValidator.validate(environment))
                .doesNotThrowAnyException();
    }

    @Test
    void should_rejectNormalProductionMode_when_flywayIsEnabled() {
        MockEnvironment environment = normalProductionEnvironment()
                .withProperty("spring.flyway.enabled", "true");

        assertThatThrownBy(() -> MigrationEnvironmentValidator.validate(environment))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("spring.flyway.enabled 설정이 migration/bootstrap/production 계약과 다릅니다.");
    }

    @Test
    void should_acceptMigrationMode_when_productionContractIsComplete() {
        MockEnvironment environment = migrationEnvironment();

        assertThatCode(() -> MigrationEnvironmentValidator.validate(environment))
                .doesNotThrowAnyException();
    }

    @Test
    void should_rejectMigrationMode_when_productionProfileIsMissing() {
        MockEnvironment environment = migrationEnvironment();
        environment.setActiveProfiles("migration");

        assertThatThrownBy(() -> MigrationEnvironmentValidator.validate(environment))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("migration mode에는 production profile이 필요합니다.");
    }

    @Test
    void should_rejectMigrationMode_when_localOrTestProfileIsCombined() {
        for (String forbiddenProfile : new String[]{"local", "test"}) {
            MockEnvironment environment = migrationEnvironment();
            environment.setActiveProfiles("production", "migration", forbiddenProfile);

            assertThatThrownBy(() -> MigrationEnvironmentValidator.validate(environment))
                    .isInstanceOf(IllegalStateException.class)
                    .hasMessage("migration mode는 local/test profile과 함께 실행할 수 없습니다.");
        }
    }

    @Test
    void should_rejectMigrationMode_when_effectiveRuntimeContractIsOverridden() {
        String[][] invalidProperties = {
                {"spring.flyway.enabled", "false"},
                {"spring.jpa.hibernate.ddl-auto", "update"},
                {"spring.main.web-application-type", "servlet"},
                {"our-ledger.bootstrap.enabled", "true"},
                {"our-ledger.recurring.scheduler.enabled", "true"}
        };

        for (String[] invalidProperty : invalidProperties) {
            MockEnvironment environment = migrationEnvironment()
                    .withProperty(invalidProperty[0], invalidProperty[1]);

            assertThatThrownBy(() -> MigrationEnvironmentValidator.validate(environment))
                    .isInstanceOf(IllegalStateException.class)
                    .hasMessageContaining(invalidProperty[0]);
        }
    }

    @Test
    void should_rejectMigrationMode_when_productionDatasourceIsIncomplete() {
        MockEnvironment environment = migrationEnvironment()
                .withProperty("spring.datasource.password", "");

        assertThatThrownBy(() -> MigrationEnvironmentValidator.validate(environment))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("spring.datasource.password 설정이 필요합니다.");
    }

    @Test
    void should_rejectNormalProductionMode_when_bootstrapOverrideIsEnabled() {
        MockEnvironment environment = normalProductionEnvironment()
                .withProperty("our-ledger.bootstrap.enabled", "true");

        assertThatThrownBy(() -> MigrationEnvironmentValidator.validate(environment))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("our-ledger.bootstrap.enabled");
    }

    @Test
    void should_acceptBootstrapMode_when_exactProductionContractIsComplete() {
        MockEnvironment environment = bootstrapEnvironment();

        assertThatCode(() -> MigrationEnvironmentValidator.validate(environment))
                .doesNotThrowAnyException();
    }

    @Test
    void should_rejectBootstrapMode_when_productionAuthorityIsMissing() {
        MockEnvironment environment = bootstrapEnvironment();
        environment.setActiveProfiles("bootstrap");

        assertThatThrownBy(() -> MigrationEnvironmentValidator.validate(environment))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("bootstrap mode에는 production profile이 필요합니다.");
    }

    @Test
    void should_rejectBootstrapMode_when_forbiddenProfileIsCombined() {
        String[][] invalidProfiles = {
                {"production", "bootstrap", "migration"},
                {"production", "bootstrap", "local"},
                {"production", "bootstrap", "test"},
                {"production", "bootstrap", "unexpected"}
        };

        for (String[] profiles : invalidProfiles) {
            MockEnvironment environment = bootstrapEnvironment();
            environment.setActiveProfiles(profiles);

            assertThatThrownBy(() -> MigrationEnvironmentValidator.validate(environment))
                    .isInstanceOf(IllegalStateException.class);
        }
    }

    @Test
    void should_rejectBootstrapMode_when_effectiveRuntimeContractIsOverridden() {
        String[][] invalidProperties = {
                {"spring.flyway.enabled", "true"},
                {"spring.jpa.hibernate.ddl-auto", "update"},
                {"spring.main.web-application-type", "servlet"},
                {"our-ledger.bootstrap.enabled", "false"},
                {"our-ledger.recurring.scheduler.enabled", "true"}
        };

        for (String[] invalidProperty : invalidProperties) {
            MockEnvironment environment = bootstrapEnvironment()
                    .withProperty(invalidProperty[0], invalidProperty[1]);

            assertThatThrownBy(() -> MigrationEnvironmentValidator.validate(environment))
                    .isInstanceOf(IllegalStateException.class)
                    .hasMessageContaining(invalidProperty[0]);
        }
    }

    @Test
    void should_identifyBootstrapMode_when_bootstrapProfileIsActive() {
        assertThatCode(() -> {
            if (!MigrationEnvironmentValidator.isBootstrapMode(bootstrapEnvironment())) {
                throw new AssertionError("bootstrap mode를 식별하지 못했습니다.");
            }
        }).doesNotThrowAnyException();
    }

    private MockEnvironment normalProductionEnvironment() {
        MockEnvironment environment = new MockEnvironment();
        environment.setActiveProfiles("production");
        return environment
                .withProperty("spring.flyway.enabled", "false")
                .withProperty("spring.jpa.hibernate.ddl-auto", "validate")
                .withProperty("our-ledger.bootstrap.enabled", "false")
                .withProperty("our-ledger.recurring.scheduler.enabled", "true");
    }

    private MockEnvironment migrationEnvironment() {
        MockEnvironment environment = new MockEnvironment();
        environment.setActiveProfiles("production", "migration");
        return environment
                .withProperty("spring.flyway.enabled", "true")
                .withProperty("spring.jpa.hibernate.ddl-auto", "validate")
                .withProperty("spring.main.web-application-type", "none")
                .withProperty("our-ledger.bootstrap.enabled", "false")
                .withProperty("our-ledger.recurring.scheduler.enabled", "false")
                .withProperty("spring.datasource.url", "jdbc:postgresql://postgres:5432/our_ledger")
                .withProperty("spring.datasource.username", "our_ledger")
                .withProperty("spring.datasource.password", "synthetic-password");
    }

    private MockEnvironment bootstrapEnvironment() {
        MockEnvironment environment = new MockEnvironment();
        environment.setActiveProfiles("production", "bootstrap");
        return environment
                .withProperty("spring.flyway.enabled", "false")
                .withProperty("spring.jpa.hibernate.ddl-auto", "validate")
                .withProperty("spring.main.web-application-type", "none")
                .withProperty("our-ledger.bootstrap.enabled", "true")
                .withProperty("our-ledger.recurring.scheduler.enabled", "false")
                .withProperty("spring.datasource.url", "jdbc:postgresql://postgres:5432/our_ledger")
                .withProperty("spring.datasource.username", "our_ledger")
                .withProperty("spring.datasource.password", "synthetic-password");
    }
}
