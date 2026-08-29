package io.github.xxh3898.ourledger.export;

import io.github.xxh3898.ourledger.security.CurrentHousehold;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDate;

@RestController
public class TransactionCsvExportController {

    private final TransactionCsvExportService exportService;

    public TransactionCsvExportController(TransactionCsvExportService exportService) {
        this.exportService = exportService;
    }

    @GetMapping("/api/v1/exports/transactions.csv")
    ResponseEntity<byte[]> export(
            @AuthenticationPrincipal CurrentHousehold currentHousehold,
            @RequestParam LocalDate from,
            @RequestParam LocalDate to
    ) {
        TransactionCsvDocument document = exportService.export(currentHousehold, from, to);
        HttpHeaders headers = new HttpHeaders();
        headers.set(HttpHeaders.CONTENT_TYPE, "text/csv; charset=UTF-8");
        headers.set(HttpHeaders.CONTENT_DISPOSITION,
                "attachment; filename=\"%s\"".formatted(document.filename()));
        headers.set(HttpHeaders.CACHE_CONTROL, "no-store");
        headers.set("X-Content-Type-Options", "nosniff");
        return ResponseEntity.ok()
                .headers(headers)
                .body(document.content());
    }
}
