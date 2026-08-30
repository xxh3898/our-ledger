package io.github.xxh3898.ourledger.ops;

import io.github.xxh3898.ourledger.bootstrap.ProductionHouseholdBootstrapRunner;
import io.github.xxh3898.ourledger.recurring.RecurringScheduler;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Profile;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.context.WebApplicationContext;

@Component
@Profile("bootstrap")
@Order(Ordered.HIGHEST_PRECEDENCE)
public final class BootstrapRuntimeGuard implements ApplicationRunner {

    private static final String GENERIC_BOOTSTRAP_RUNNER = "householdBootstrapRunner";
    private static final String SCHEDULING_PROCESSOR =
            "org.springframework.context.annotation.internalScheduledAnnotationProcessor";

    private final ConfigurableApplicationContext context;

    public BootstrapRuntimeGuard(ConfigurableApplicationContext context) {
        this.context = context;
    }

    @Override
    public void run(ApplicationArguments arguments) {
        require(!(context instanceof WebApplicationContext),
                "bootstrap mode에서 Web application context를 사용할 수 없습니다.");
        require(!context.containsBean(GENERIC_BOOTSTRAP_RUNNER),
                "bootstrap mode에서 generic bootstrap runner를 실행할 수 없습니다.");
        require(context.getBeansOfType(ProductionHouseholdBootstrapRunner.class).size() == 1,
                "bootstrap mode에는 production bootstrap runner가 정확히 하나 필요합니다.");
        require(context.getBeansOfType(RecurringScheduler.class).isEmpty(),
                "bootstrap mode에서 recurring scheduler를 실행할 수 없습니다.");
        require(!context.containsBean(SCHEDULING_PROCESSOR),
                "bootstrap mode에서 scheduling processor를 활성화할 수 없습니다.");
    }

    private void require(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }
}
