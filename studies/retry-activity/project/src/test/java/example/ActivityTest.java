package example;

import org.junit.Test;
import static org.junit.Assert.fail;

/** Controlled reporter capture, not a production reliability experiment. */
public class ActivityTest {
    private static int attempts = 0;

    @Test public void checkout() {
        attempts++;
        String scenario = System.getProperty("scenario", "pass");
        if (scenario.equals("failed") || (scenario.equals("recovered") && attempts == 1)) {
            fail("Controlled checkout timeout, attempt " + attempts);
        }
    }
}
