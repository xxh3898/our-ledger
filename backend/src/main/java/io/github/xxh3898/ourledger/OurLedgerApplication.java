package io.github.xxh3898.ourledger;

import io.github.xxh3898.ourledger.bootstrap.ProductionHouseholdBootstrapRunner;
import io.github.xxh3898.ourledger.ops.MigrationEnvironmentValidator;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class OurLedgerApplication {

    public static void main(String[] args) {
        SpringApplication application = new SpringApplication(OurLedgerApplication.class);
        application.addListeners(new MigrationEnvironmentValidator());
        ConfigurableApplicationContext context = application.run(args);

        if (MigrationEnvironmentValidator.isMigrationMode(context.getEnvironment())) {
            System.out.println("migration-validation: success");
            int exitCode = SpringApplication.exit(context);
            System.exit(exitCode);
        }

        if (MigrationEnvironmentValidator.isBootstrapMode(context.getEnvironment())) {
            ProductionHouseholdBootstrapRunner runner =
                    context.getBean(ProductionHouseholdBootstrapRunner.class);
            System.out.println(runner.successMarker());
            int exitCode = SpringApplication.exit(context);
            System.exit(exitCode);
        }
    }
}
