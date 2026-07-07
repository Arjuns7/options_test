/**
 * Test and Verification Suite for Options Backtesting Engine
 * Run with: node test-engine.js
 */

const MockDataEngine = require('./mock-data.js');
const BacktestEngine = require('./backtest-engine.js');

// Helper to assert similarity
function assertClose(actual, expected, tolerance = 0.05, label = "") {
    const diff = Math.abs(actual - expected);
    if (diff <= tolerance) {
        console.log(`✅ [PASS] ${label}: Got ${actual.toFixed(4)}, expected ${expected.toFixed(4)} (diff: ${diff.toFixed(4)})`);
    } else {
        console.error(`❌ [FAIL] ${label}: Got ${actual.toFixed(4)}, expected ${expected.toFixed(4)} (diff: ${diff.toFixed(4)})`);
        process.exit(1);
    }
}

console.log("=== Testing Option Pricing Model (Black-Scholes) ===");
// Case 1: ATM Option
// S = 100, K = 100, T = 1.0 year, r = 5% (0.05), v = 20% (0.20)
// Theoretical BS values: Call ~10.4506, Put ~5.5735
const S1 = 100, K1 = 100, T1 = 1.0, r1 = 0.05, v1 = 0.20;
const call1 = BacktestEngine.blackScholes('C', S1, K1, T1, r1, v1);
const put1 = BacktestEngine.blackScholes('P', S1, K1, T1, r1, v1);
assertClose(call1, 10.4506, 0.01, "BS Call (ATM, T=1)");
assertClose(put1, 5.5735, 0.01, "BS Put (ATM, T=1)");

// Case 2: Near Expiry Call (Intrinsic Settle)
// S = 105, K = 100, T = 0.00001 (expiry), r = 5%, v = 20%
// Theoretical values: Call = 5.0, Put = 0.0
const callNear = BacktestEngine.blackScholes('C', 105, 100, 0, r1, v1);
const putNear = BacktestEngine.blackScholes('P', 105, 100, 0, r1, v1);
assertClose(callNear, 5.0, 0.001, "Near-Expiry ITM Call Settle");
assertClose(putNear, 0.0, 0.001, "Near-Expiry OTM Put Settle");

console.log("\n=== Testing Option Expiry Calculator ===");
// TargetDay: Nifty (Thursday = 4)
// Starting: Friday, Jan 5, 2024 (should yield next Thursday, Jan 11, 2024)
const expiryWk = BacktestEngine.getExpiryDate('2024-01-05', 'WEEKLY', 'NIFTY');
console.log(`Weekly Nifty Expiry from Jan 5, 2024: Got ${expiryWk}, expected 2024-01-11`);
if (expiryWk === '2024-01-11') {
    console.log("✅ [PASS] Weekly Expiry Calculation");
} else {
    console.error("❌ [FAIL] Weekly Expiry Calculation");
    process.exit(1);
}

// Monthly Expiry: Last Thursday of Jan 2024 (should be Jan 25, 2024)
const expiryMo = BacktestEngine.getExpiryDate('2024-01-05', 'MONTHLY', 'NIFTY');
console.log(`Monthly Nifty Expiry for Jan 2024: Got ${expiryMo}, expected 2024-01-25`);
if (expiryMo === '2024-01-25') {
    console.log("✅ [PASS] Monthly Expiry Calculation");
} else {
    console.error("❌ [FAIL] Monthly Expiry Calculation");
    process.exit(1);
}

console.log("\n=== Testing Backtest Simulation Integration ===");
// Setup window mock for Node environment
global.MockDataEngine = MockDataEngine;
global.BacktestEngine = BacktestEngine;

// Run sample backtest (Nifty Short Straddle)
const testParams = {
    indexName: 'NIFTY',
    startDate: '2024-01-01',
    endDate: '2024-01-10',
    legs: [
        { type: 'C', position: 'SELL', strike: 'ATM', qty: 1, expiry: 'WEEKLY' },
        { type: 'P', position: 'SELL', strike: 'ATM', qty: 1, expiry: 'WEEKLY' }
    ],
    entryTimeStr: '09:20',
    exitTimeStr: '15:15',
    slType: 'PERCENT',
    slVal: 20,
    tpType: 'NONE',
    tpVal: 0,
    capital: 500000
};

const results = BacktestEngine.run(testParams);
if (results.summary && results.summary.totalDays > 0) {
    console.log(`✅ [PASS] Simulation executed. Total Days Run: ${results.summary.totalDays}`);
    console.log(`   Final Capital: ₹${results.summary.finalCapital}`);
    console.log(`   ROI: ${results.summary.roi}%`);
    console.log(`   Win Rate: ${results.summary.winRate}%`);
    console.log(`   Max Drawdown: ${results.summary.maxDrawdown}%`);
} else {
    console.error("❌ [FAIL] Simulation execution returned empty or invalid results", results);
    process.exit(1);
}

console.log("\n🎉 All tests passed successfully!");
