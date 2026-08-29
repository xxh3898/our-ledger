import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class HttpFetch {

    private HttpFetch() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.exit(2);
        }

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(2))
                .build();
        HttpRequest request = HttpRequest.newBuilder(URI.create(args[0]))
                .timeout(Duration.ofSeconds(3))
                .GET()
                .build();
        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString()
        );
        System.out.println(response.statusCode());
        System.out.print(response.body());
    }
}
