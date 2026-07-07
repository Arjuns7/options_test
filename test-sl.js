const MockDataEngine = require('./mock-data.js');
const BacktestEngine = require('./backtest-engine.js');

global.MockDataEngine = MockDataEngine;
global.BacktestEngine = BacktestEngine;

const baseParams = {
    indexName: 'NIFTY',
    startDate: '2024-01-01',
    endDate: '2024-05-01',
    legs: [
        { type: 'C', position: 'SELL', strike: 'ATM', qty: 1, expiry: 'WEEKLY' },
        { type: 'P', position: 'SELL', strike: 'ATM', qty: 1, expiry: 'WEEKLY' }
    ],
    entryTimeStr: '09:30',
    exitTimeStr: '15:00',
    capital: 200000
};

console.log("--- RUNNING BACKTEST: NO STOP LOSS ---");
const resNoSl = BacktestEngine.run({
    ...baseParams,
    slType: 'NONE',
    slVal: 0
});
console.log(`Days: ${resNoSl.summary.totalDays}`);
console.log(`Win Rate: ${resNoSl.summary.winRate}% (${resNoSl.summary.winningDays} Wins / ${resNoSl.summary.losingDays} Losses)`);
console.log(`Total P&L: ₹${resNoSl.summary.totalPnL}`);

console.log("\n--- RUNNING BACKTEST: 25% LEG STOP LOSS ---");
const resSl = BacktestEngine.run({
    ...baseParams,
    slType: 'PERCENT',
    slVal: 25
});
console.log(`Days: ${resSl.summary.totalDays}`);
console.log(`Win Rate: ${resSl.summary.winRate}% (${resSl.summary.winningDays} Wins / ${resSl.summary.losingDays} Losses)`);
console.log(`Total P&L: ₹${resSl.summary.totalPnL}`);

console.log("\n--- RUNNING BACKTEST: 30 POINTS LEG STOP LOSS ---");
const resPointsSl = BacktestEngine.run({
    ...baseParams,
    slType: 'POINTS',
    slVal: 30
});
console.log(`Days: ${resPointsSl.summary.totalDays}`);
console.log(`Win Rate: ${resPointsSl.summary.winRate}% (${resPointsSl.summary.winningDays} Wins / ${resPointsSl.summary.losingDays} Losses)`);
console.log(`Total P&L: ₹${resPointsSl.summary.totalPnL}`);

// Print a few sample trades from the SL log to verify hits
console.log("\nSample Trades with 25% SL:");
for (let i = 0; i < Math.min(5, resSl.tradeLogs.length); i++) {
    const log = resSl.tradeLogs[i];
    console.log(`Date: ${log.date} | Spot: ${log.spotAtEntry} -> ${log.spotAtExit} | Net P&L: ₹${log.totalPnL}`);
    log.legs.forEach((l, idx) => {
        console.log(`  Leg ${idx+1}: ${l.position} ${l.strike} ${l.type} | Entry: ₹${l.entryPremium} | Exit: ₹${l.exitPremium} | Status: ${l.status} | P&L: ₹${l.pnl}`);
    });
}
