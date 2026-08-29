package io.github.xxh3898.ourledger;

import io.github.xxh3898.ourledger.bootstrap.HouseholdBootstrapRequest;
import io.github.xxh3898.ourledger.bootstrap.HouseholdBootstrapService;
import io.github.xxh3898.ourledger.security.LocalIdentityAuthenticationFilter;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.restdocs.test.autoconfigure.AutoConfigureRestDocs;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import java.nio.charset.StandardCharsets;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ActiveProfiles("test")
@AutoConfigureMockMvc
@AutoConfigureRestDocs
@Import(TestcontainersConfiguration.class)
@SpringBootTest
class TransactionCsvExportApiDocsTest {

    private static final String LOCAL_IDENTITY_HEADER =
            LocalIdentityAuthenticationFilter.HEADER_NAME;
    private static final String OWNER_EMAIL = "csv-owner@example.test";

    @Autowired private MockMvc mockMvc;
    @Autowired private HouseholdBootstrapService bootstrapService;
    @Autowired private JdbcTemplate jdbcTemplate;

    @BeforeEach
    void setUp() {
        clearDatabase();
        bootstrapService.provision(new HouseholdBootstrapRequest(
                "CSV Household",
                OWNER_EMAIL,
                "CSV Owner",
                "csv-partner@example.test",
                "CSV Partner"
        ));
    }

    @AfterEach
    void tearDown() {
        clearDatabase();
    }

    @Test
    void should_documentCsvAttachment_when_currentHouseholdExportsValidRange() throws Exception {
        byte[] content = mockMvc.perform(get("/api/v1/exports/transactions.csv")
                        .queryParam("from", "2026-08-01")
                        .queryParam("to", "2026-08-31")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL))
                .andExpect(status().isOk())
                .andExpect(header().string(HttpHeaders.CONTENT_TYPE, "text/csv; charset=UTF-8"))
                .andExpect(header().string(
                        HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"our-ledger-transactions_2026-08-01_2026-08-31.csv\""
                ))
                .andExpect(header().string(HttpHeaders.CACHE_CONTROL, "no-store"))
                .andExpect(header().string("X-Content-Type-Options", "nosniff"))
                .andDo(document("transaction-csv-export"))
                .andReturn()
                .getResponse()
                .getContentAsByteArray();

        assertThat(content).startsWith((byte) 0xEF, (byte) 0xBB, (byte) 0xBF);
        assertThat(new String(content, StandardCharsets.UTF_8))
                .isEqualTo("\uFEFF거래ID,발생일,발생시각,거래유형,조정유형,금액,귀속,소유자,결제자,"
                        + "카테고리,계좌,출금계좌,입금계좌,메모,원거래ID,반복거래,반복발생일,"
                        + "생성시각,수정시각\r\n");
    }

    @Test
    void should_returnStableJsonErrors_when_exportRangeIsInvalid() throws Exception {
        mockMvc.perform(get("/api/v1/exports/transactions.csv")
                        .queryParam("from", "2026-08-01")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_REQUEST"));

        mockMvc.perform(get("/api/v1/exports/transactions.csv")
                        .queryParam("from", "not-a-date")
                        .queryParam("to", "2026-08-01")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_REQUEST"));

        mockMvc.perform(get("/api/v1/exports/transactions.csv")
                        .queryParam("from", "2026-08-02")
                        .queryParam("to", "2026-08-01")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_REQUEST"));

        mockMvc.perform(get("/api/v1/exports/transactions.csv")
                        .queryParam("from", "2016-01-01")
                        .queryParam("to", "2026-01-01")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.code").value("EXPORT_RANGE_TOO_LARGE"))
                .andDo(document("transaction-csv-export-range-too-large"));
    }

    @Test
    void should_requireAuthenticatedInternalUser_when_exportIsRequested() throws Exception {
        mockMvc.perform(get("/api/v1/exports/transactions.csv")
                        .queryParam("from", "2026-08-01")
                        .queryParam("to", "2026-08-31"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("AUTHENTICATION_REQUIRED"));

        mockMvc.perform(get("/api/v1/exports/transactions.csv")
                        .queryParam("from", "2026-08-01")
                        .queryParam("to", "2026-08-31")
                        .header(LOCAL_IDENTITY_HEADER, "unknown@example.test"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("USER_NOT_REGISTERED"));
    }

    private void clearDatabase() {
        jdbcTemplate.execute("""
                TRUNCATE TABLE
                    goal_accounts,
                    goals,
                    recurring_transaction_accounts,
                    transaction_account_entries,
                    transactions,
                    recurring_transactions,
                    budgets,
                    categories,
                    category_groups,
                    accounts,
                    household_members,
                    households,
                    users
                RESTART IDENTITY CASCADE
                """);
    }
}
