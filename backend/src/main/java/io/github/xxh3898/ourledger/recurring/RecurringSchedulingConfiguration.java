package io.github.xxh3898.ourledger.recurring;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

import java.time.Clock;

@Configuration
@EnableScheduling
public class RecurringSchedulingConfiguration {

    @Bean
    Clock recurringClock() {
        return Clock.systemUTC();
    }
}
