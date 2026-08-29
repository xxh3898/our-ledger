package io.github.xxh3898.ourledger.ops;

import io.github.xxh3898.ourledger.recurring.RecurringScheduler;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;
import org.springframework.web.context.WebApplicationContext;

@Component
@Profile("migration")
public final class MigrationRuntimeGuard implements ApplicationRunner {

    private static final String BOOTSTRAP_RUNNER = "householdBootstrapRunner";
    private static final String SCHEDULING_PROCESSOR =
            "org.springframework.context.annotation.internalScheduledAnnotationProcessor";

    private final ConfigurableApplicationContext context;

    public MigrationRuntimeGuard(ConfigurableApplicationContext context) {
        this.context = context;
    }

    @Override
    public void run(ApplicationArguments arguments) {
        require(!(context instanceof WebApplicationContext),
                "migration mode에서 Web application context를 사용할 수 없습니다.");
        require(!context.containsBean(BOOTSTRAP_RUNNER),
                "migration mode에서 bootstrap runner를 실행할 수 없습니다.");
        require(context.getBeansOfType(RecurringScheduler.class).isEmpty(),
                "migration mode에서 recurring scheduler를 실행할 수 없습니다.");
        require(!context.containsBean(SCHEDULING_PROCESSOR),
                "migration mode에서 scheduling processor를 활성화할 수 없습니다.");
    }

    private void require(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }
}
