package io.github.xxh3898.ourledger.ops;

import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;

import java.util.Set;

public final class MigrationEnvironmentValidator
        implements ApplicationListener<ApplicationEnvironmentPreparedEvent> {

    private static final Profiles PRODUCTION = Profiles.of("production");
    private static final Profiles MIGRATION = Profiles.of("migration");
    private static final Profiles BOOTSTRAP = Profiles.of("bootstrap");
    private static final Profiles LOCAL_OR_TEST = Profiles.of("local", "test");
    private static final Set<String> PRODUCTION_BOOTSTRAP_PROFILES =
            Set.of("production", "bootstrap");

    @Override
    public void onApplicationEvent(ApplicationEnvironmentPreparedEvent event) {
        validate(event.getEnvironment());
    }

    public static boolean isMigrationMode(Environment environment) {
        return environment.acceptsProfiles(MIGRATION);
    }

    public static boolean isBootstrapMode(Environment environment) {
        return environment.acceptsProfiles(BOOTSTRAP);
    }

    static void validate(ConfigurableEnvironment environment) {
        boolean production = environment.acceptsProfiles(PRODUCTION);
        boolean migration = isMigrationMode(environment);
        boolean bootstrap = isBootstrapMode(environment);
        if (!production && !migration && !bootstrap) {
            return;
        }

        requireValue(environment, "spring.jpa.hibernate.ddl-auto", "validate");

        if (bootstrap) {
            validateBootstrapMode(environment, production, migration);
            return;
        }

        requireBoolean(environment, "our-ledger.bootstrap.enabled", false);

        if (!migration) {
            requireBoolean(environment, "spring.flyway.enabled", false);
            requireBoolean(environment, "our-ledger.recurring.scheduler.enabled", true);
            return;
        }

        require(production, "migration mode에는 production profile이 필요합니다.");
        require(
                !environment.acceptsProfiles(LOCAL_OR_TEST),
                "migration mode는 local/test profile과 함께 실행할 수 없습니다."
        );
        requireBoolean(environment, "spring.flyway.enabled", true);
        requireValue(environment, "spring.main.web-application-type", "none");
        requireBoolean(environment, "our-ledger.recurring.scheduler.enabled", false);
        requireText(environment, "spring.datasource.url");
        requireText(environment, "spring.datasource.username");
        requireText(environment, "spring.datasource.password");
    }

    private static void validateBootstrapMode(
            ConfigurableEnvironment environment,
            boolean production,
            boolean migration
    ) {
        require(production, "bootstrap mode에는 production profile이 필요합니다.");
        require(!migration, "bootstrap mode는 migration profile과 함께 실행할 수 없습니다.");
        require(
                !environment.acceptsProfiles(LOCAL_OR_TEST),
                "bootstrap mode는 local/test profile과 함께 실행할 수 없습니다."
        );
        require(
                Set.of(environment.getActiveProfiles()).equals(PRODUCTION_BOOTSTRAP_PROFILES),
                "bootstrap mode는 production,bootstrap profile만 허용합니다."
        );
        requireBoolean(environment, "spring.flyway.enabled", false);
        requireValue(environment, "spring.main.web-application-type", "none");
        requireBoolean(environment, "our-ledger.bootstrap.enabled", true);
        requireBoolean(environment, "our-ledger.recurring.scheduler.enabled", false);
        requireText(environment, "spring.datasource.url");
        requireText(environment, "spring.datasource.username");
        requireText(environment, "spring.datasource.password");
    }

    private static void requireBoolean(
            Environment environment,
            String property,
            boolean expected
    ) {
        Boolean actual = environment.getProperty(property, Boolean.class);
        require(
                actual != null && actual == expected,
                property + " 설정이 migration/bootstrap/production 계약과 다릅니다."
        );
    }

    private static void requireValue(
            Environment environment,
            String property,
            String expected
    ) {
        String actual = environment.getProperty(property);
        require(
                actual != null && actual.equalsIgnoreCase(expected),
                property + " 설정이 migration/bootstrap/production 계약과 다릅니다."
        );
    }

    private static void requireText(Environment environment, String property) {
        String value = environment.getProperty(property);
        require(value != null && !value.isBlank(), property + " 설정이 필요합니다.");
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }
}
