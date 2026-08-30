package io.github.xxh3898.ourledger.bootstrap;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

import java.io.InputStream;

@Component
@Profile("bootstrap")
@Order(Ordered.LOWEST_PRECEDENCE)
public final class ProductionHouseholdBootstrapRunner implements ApplicationRunner {

    public static final String CREATED_MARKER = "household-bootstrap: created";
    public static final String VERIFIED_MARKER = "household-bootstrap: verified";

    private final HouseholdBootstrapService service;
    private final InputStream input;
    private final ProductionBootstrapInputParser parser;

    private boolean invoked;
    private String successMarker;

    @Autowired
    public ProductionHouseholdBootstrapRunner(HouseholdBootstrapService service) {
        this(service, System.in, new ProductionBootstrapInputParser());
    }

    ProductionHouseholdBootstrapRunner(
            HouseholdBootstrapService service,
            InputStream input,
            ProductionBootstrapInputParser parser
    ) {
        this.service = service;
        this.input = input;
        this.parser = parser;
    }

    @Override
    public synchronized void run(ApplicationArguments arguments) {
        if (invoked) {
            throw new IllegalStateException("production bootstrap runner는 한 번만 실행할 수 있습니다.");
        }
        invoked = true;

        HouseholdBootstrapRequest request = parser.parse(input);
        HouseholdBootstrapResult result = service.provision(request);
        successMarker = result.created() ? CREATED_MARKER : VERIFIED_MARKER;
    }

    public synchronized String successMarker() {
        if (successMarker == null) {
            throw new IllegalStateException("production bootstrap이 완료되지 않았습니다.");
        }
        return successMarker;
    }
}
