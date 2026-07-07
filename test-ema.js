const MockDataEngine = require('./mock-data.js');
const BacktestEngine = require('./backtest-engine.js');

global.MockDataEngine = MockDataEngine;
global.BacktestEngine = BacktestEngine;

const params = {
    indexName: 'NIFTY',
    startDate: '2024-01-01',
    endDate: '2024-05-01',
    legs: [], // Empty since we trade based on EMA cross signals
    entryTimeStr: '09:30',
    exitTimeStr: '15:00',
    slType: 'NONE',
    slVal: 0,
    tpType: 'NONE',
    tpVal: 0,
    capital: 200000,
    signalMode: 'EMA_CROSS',
    emaPeriod: 20
};

console.log("=== Testing EMA Crossing Options Strategy ===");
const results = BacktestEngine.run(params);

if (results.summary && results.summary.totalDays > 0) {
    console.log(`✅ [PASS] EMA Backtest Executed.`);
    console.log(`   Total Trading Days checked: ${results.summary.totalDays}`);
    console.log(`   Trades Executed: ${results.tradeLogs.length}`);
    console.log(`   Final Capital: ₹${results.summary.finalCapital}`);
    console.log(`   ROI: ${results.summary.roi}%`);
    console.log(`   Win Rate: ${results.summary.winRate}%`);
    
    // Print first 3 trade logs
    console.log("\nSample EMA Signal Trades:");
    results.tradeLogs.slice(0, 3).forEach(log => {
        console.log(`  Date: ${log.date} | Spot: ${log.spotAtEntry} -> ${log.spotAtExit} | Signal: ${log.signalType} | P&L: ₹${log.totalPnL}`);
        log.legs.forEach(leg => {
            console.log(`    Leg: ${leg.position} ${leg.strike} ${leg.type} | Entry: ₹${leg.entryPremium} | Exit: ₹${leg.exitPremium}`);
        });
    });

    // Verify chartData is returned and contains spot/ema values
    if (results.chartData && results.chartData.length > 0) {
        console.log(`\n✅ [PASS] chartData returned with ${results.chartData.length} records.`);
        console.log(`   Sample chartData record:`, results.chartData[results.chartData.length - 1]);
    } else {
        console.error("❌ [FAIL] chartData missing or empty!");
        process.exit(1);
    }
} else {
    console.error("❌ [FAIL] EMA Crossover Backtest failed to run!", results);
    process.exit(1);
}

console.log("\n🎉 EMA crossover engine verification complete!");
