package io.github.xxh3898.ourledger.bootstrap;

import org.junit.jupiter.api.Test;
import org.springframework.boot.DefaultApplicationArguments;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class ProductionHouseholdBootstrapRunnerTest {

    private static final HouseholdBootstrapRequest REQUEST = new HouseholdBootstrapRequest(
            "테스트 Household",
            "owner@example.test",
            "Owner",
            "member@example.test",
            "Member"
    );

    @Test
    void should_publishCreatedMarker_when_serviceCreatesExactState() throws Exception {
        HouseholdBootstrapService service = mock(HouseholdBootstrapService.class);
        when(service.provision(REQUEST))
                .thenReturn(new HouseholdBootstrapResult(true, 11L, 21L, 22L));
        ProductionHouseholdBootstrapRunner runner = runner(service);

        runner.run(new DefaultApplicationArguments(new String[0]));

        assertThat(runner.successMarker())
                .isEqualTo(ProductionHouseholdBootstrapRunner.CREATED_MARKER)
                .doesNotContain("11", "21", "22", "example.test");
        verify(service).provision(REQUEST);
    }

    @Test
    void should_publishVerifiedMarker_when_serviceVerifiesExactState() throws Exception {
        HouseholdBootstrapService service = mock(HouseholdBootstrapService.class);
        when(service.provision(REQUEST))
                .thenReturn(new HouseholdBootstrapResult(false, 11L, 21L, 22L));
        ProductionHouseholdBootstrapRunner runner = runner(service);

        runner.run(new DefaultApplicationArguments(new String[0]));

        assertThat(runner.successMarker())
                .isEqualTo(ProductionHouseholdBootstrapRunner.VERIFIED_MARKER);
        verify(service).provision(REQUEST);
    }

    @Test
    void should_rejectSecondInvocation_when_runnerWasAlreadyInvoked() throws Exception {
        HouseholdBootstrapService service = mock(HouseholdBootstrapService.class);
        when(service.provision(REQUEST))
                .thenReturn(new HouseholdBootstrapResult(true, 11L, 21L, 22L));
        ProductionHouseholdBootstrapRunner runner = runner(service);
        DefaultApplicationArguments arguments = new DefaultApplicationArguments(new String[0]);

        runner.run(arguments);

        assertThatThrownBy(() -> runner.run(arguments))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("production bootstrap runner는 한 번만 실행할 수 있습니다.");
        verify(service).provision(REQUEST);
    }

    @Test
    void should_rejectMarkerRead_when_bootstrapDidNotComplete() {
        ProductionHouseholdBootstrapRunner runner = runner(mock(HouseholdBootstrapService.class));

        assertThatThrownBy(runner::successMarker)
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("production bootstrap이 완료되지 않았습니다.");
    }

    private ProductionHouseholdBootstrapRunner runner(HouseholdBootstrapService service) {
        String json = """
                {
                  "formatVersion": 1,
                  "householdName": "테스트 Household",
                  "owner": {"email": "owner@example.test", "displayName": "Owner"},
                  "member": {"email": "member@example.test", "displayName": "Member"}
                }
                """;
        return new ProductionHouseholdBootstrapRunner(
                service,
                new ByteArrayInputStream(json.getBytes(StandardCharsets.UTF_8)),
                new ProductionBootstrapInputParser()
        );
    }
}
