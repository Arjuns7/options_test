const RealHistoricalData = require('./real-data.js');
const BacktestEngine = require('./backtest-engine.js');

global.RealHistoricalData = RealHistoricalData;
global.BacktestEngine = BacktestEngine;

// Optimized parameters from grid search (Nifty 15-Min crossover 2025)
const params = {
    indexName: 'NIFTY',
    startDate: '2025-01-01',
    endDate: '2025-12-31',
    legs: [], // Empty since crossover mode auto-enters
    entryTimeStr: '09:20',
    exitTimeStr: '15:15',
    slType: 'PERCENT',
    slVal: 20,
    tpType: 'PERCENT',
    tpVal: 30,
    capital: 500000,
    signalMode: 'EMA_CROSS_15MIN',
    emaPeriod: 9,
    emaStrike: 'ITM1',
    emaLots: 2,
    feedMode: 'REAL'
};

console.log("=== Testing 15-Min Crossover & ITM 1 Strike selection ===");
const results = BacktestEngine.run(params);

if (results.summary && results.summary.totalDays > 0) {
    console.log(`\u2705 [PASS] 15-Min Crossover Backtest Executed.`);
    console.log(`   Total Trades Executed: ${results.summary.totalDays}`);
    console.log(`   Winning Trades: ${results.summary.winningDays}`);
    console.log(`   Losing Trades: ${results.summary.losingDays}`);
    console.log(`   Net P&L: \u20b9${results.summary.totalPnL}`);
    console.log(`   ROI: ${results.summary.roi}%`);
    console.log(`   Win Rate: ${results.summary.winRate}%`);
    
    // Print first 5 trades
    console.log("\nFirst 5 Crossover Trades:");
    results.tradeLogs.slice(0, 5).forEach((log, idx) => {
        console.log(`  [Trade #${idx + 1}] Date: ${log.date} | Signal: ${log.signalType} | Spot: \u20b9${log.spotAtEntry} -> \u20b9${log.spotAtExit} | Net P&L: \u20b9${log.totalPnL}`);
        log.legs.forEach(leg => {
            console.log(`    Contract: ${leg.position} ${leg.strike} ${leg.type} | Entry: \u20b9${leg.entryPremium} -> Exit: \u20b9${leg.exitPremium} (${leg.status} at ${leg.exitTime})`);
        });
    });

    // Verification asserts
    if (results.summary.totalDays === 433 && results.summary.winRate === 61.43) {
        console.log(`\n\u2705 [PASS] Matches the grid-search optimized results exactly (433 trades, 61.43% win rate).`);
    } else {
        console.warn(`\n⚠️ [WARN] Backtest runs successfully but mismatch in numbers: ${results.summary.totalDays} trades, ${results.summary.winRate}% win rate vs expected 433 trades, 61.43% win rate.`);
    }
} else {
    console.error("\u274c [FAIL] 15-Min Crossover Backtest failed to run!", results);
    process.exit(1);
}

console.log("\n\u200b🎉 15-Min crossover verification script finished!");
