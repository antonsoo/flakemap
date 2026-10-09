// Controlled reporter fixture: these outcomes do not describe production reliability.
#include <gtest/gtest.h>

TEST(Execution, AlwaysPasses) { EXPECT_EQ(2 + 2, 4); }

TEST(Execution, DISABLED_FailsWhenEnabled) {
  FAIL() << "This test never passes when it actually runs";
}

TEST(DISABLED_UnavailableDevice, NeedsHardware) {
  FAIL() << "This disabled suite did not exercise hardware";
}

TEST(Execution, RuntimeSkip) {
  GTEST_SKIP() << "Controlled skip: no device attached";
}

TEST(Execution, AFailFastTrigger) { FAIL() << "Controlled fail-fast trigger"; }

TEST(Execution, ZAfterTrigger) { EXPECT_TRUE(true); }
