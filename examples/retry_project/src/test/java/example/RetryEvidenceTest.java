package example;

import org.junit.Ignore;
import org.junit.Test;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

/** Controlled outcomes to exercise real Surefire retry serialization. */
public class RetryEvidenceTest {
    private static int recoveryAttempts = 0;
    private static int errorAttempts = 0;

    @Test public void recoversAfterTwoFailures() {
        assertTrue("connection not ready", ++recoveryAttempts >= 3);
    }

    @Test public void recoversFromError() {
        if (++errorAttempts == 1) throw new IllegalStateException("worker unavailable");
    }

    @Test public void alwaysFails() { fail("expected revision was not deployed"); }

    @Test public void alwaysErrors() { throw new IllegalStateException("invalid configuration"); }

    @Test public void alwaysPasses() { assertTrue(true); }

    @Ignore("disabled by the fixture") @Test public void skipped() { }
}
