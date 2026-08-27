package io.github.xxh3898.ourledger;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.annotation.AnnotatedElementUtils;

import static org.assertj.core.api.Assertions.assertThat;

class OurLedgerApplicationTest {

    @Test
    void should_declareSpringBootApplication_when_bootstrapClassIsInspected() {
        assertThat(AnnotatedElementUtils.hasAnnotation(
                OurLedgerApplication.class,
                SpringBootApplication.class
        )).isTrue();
    }
}
