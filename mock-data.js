/**
 * Mock Historical Data Engine for Nifty & Bank Nifty (2024 - 2026)
 * Generates deterministic, highly realistic trading day data including OHLC, 
 * Implied Volatility (IV), and macroeconomic events (e.g., elections, budgets).
 */

const MockDataEngine = (function() {
    // Deterministic random generator to keep backtests reproducible
    function seedRandom(seed) {
        let x = Math.sin(seed++) * 10000;
        return x - Math.floor(x);
    }

    // Helper to check if a date is a weekday (Mon-Fri)
    function isWeekday(date) {
        const day = date.getDay();
        return day !== 0 && day !== 6;
    }

    // Format date as YYYY-MM-DD
    function formatDate(date) {
        const y = date.getFullYear();
        const m = String(date.getMonth() + 1).padStart(2, '0');
        const d = String(date.getDate()).padStart(2, '0');
        return `${y}-${m}-${d}`;
    }

    /**
     * Generates daily price and volatility data for Nifty and Bank Nifty.
     */
    function getHistoricalData(indexName, startStr, endStr) {
        const data = [];
        const start = new Date(startStr);
        const end = new Date(endStr);
        
        // Base configurations
        const isNifty = indexName.toUpperCase() === 'NIFTY';
        const basePrice = isNifty ? 21700 : 48000;
        const annualDrift = isNifty ? 0.14 : 0.11; // 14% for Nifty, 11% for Bank Nifty
        const baseIv = isNifty ? 13 : 17; // 13% for Nifty, 17% for Bank Nifty
        
        let currentPrice = basePrice;
        let dayCounter = 0;
        
        // Loop from Jan 1, 2024 to current
        let currentDate = new Date('2024-01-01');
        const targetEndDate = new Date(endStr);
        
        // We generate data sequentially from 2024-01-01 to ensure consistency, 
        // then filter for the user's requested date range.
        while (currentDate <= targetEndDate) {
            if (isWeekday(currentDate)) {
                dayCounter++;
                const seed = dayCounter + (isNifty ? 1000 : 5000);
                const rand1 = seedRandom(seed);
                const rand2 = seedRandom(seed + 1);
                const rand3 = seedRandom(seed + 2);
                
                // 1. Calculate time delta (approx 1/252 of a year)
                const dt = 1 / 252;
                
                // 2. Adjust drift and IV for special historical events
                let iv = baseIv;
                let eventDrift = 0;
                
                const dateStr = formatDate(currentDate);
                
                // Lok Sabha Election Results (June 3-4, 2024)
                if (dateStr >= '2024-05-15' && dateStr <= '2024-06-10') {
                    if (dateStr === '2024-06-03') {
                        // Exit Poll Spike (+3%)
                        eventDrift = 0.035;
                        iv = baseIv * 2.2;
                    } else if (dateStr === '2024-06-04') {
                        // Election Result Crash (-6% for Nifty, -8% for BankNifty)
                        eventDrift = isNifty ? -0.065 : -0.085;
                        iv = baseIv * 2.8;
                    } else if (dateStr >= '2024-06-05' && dateStr <= '2024-06-08') {
                        // Recovery (+2% per day)
                        eventDrift = 0.022;
                        iv = baseIv * 2.2;
                    } else {
                        iv = baseIv * 1.8;
                    }
                }
                // Union Budget (July 23, 2024)
                else if (dateStr >= '2024-07-15' && dateStr <= '2024-07-26') {
                    iv = baseIv * 1.35;
                    if (dateStr === '2024-07-23') {
                        eventDrift = -0.015; // Budget day sell-off
                    }
                }
                // Global Tech Sell-off / Yen Carry Trade (Aug 5, 2024)
                else if (dateStr >= '2024-08-01' && dateStr <= '2024-08-08') {
                    iv = baseIv * 1.4;
                    if (dateStr === '2024-08-05') {
                        eventDrift = -0.028;
                    }
                }
                // Q3 Consolidation (Oct-Nov 2024)
                else if (dateStr >= '2024-10-01' && dateStr <= '2024-11-15') {
                    eventDrift = -0.001; // Correction
                    iv = baseIv * 1.1;
                }
                // Early 2025 Rally (Jan - Feb 2025)
                else if (dateStr >= '2025-01-01' && dateStr <= '2025-02-28') {
                    eventDrift = 0.0015;
                    iv = baseIv * 0.95;
                }
                // Late 2025 Peak and Correction (Sep - Oct 2025)
                else if (dateStr >= '2025-09-01' && dateStr <= '2025-10-31') {
                    if (dateStr >= '2025-09-01' && dateStr <= '2025-09-15') {
                        eventDrift = 0.002; // Peak
                    } else {
                        eventDrift = -0.0025; // Correction
                        iv = baseIv * 1.3;
                    }
                }
                // General cyclical sine wave overlay to represent market swing
                const cycle = Math.sin(dayCounter / 20) * 0.0015;
                
                // 3. Geometric Brownian Motion step
                // dS = S * (mu*dt + sigma*W)
                const mu = annualDrift + eventDrift;
                const sigma = (iv / 100) * (0.8 + rand1 * 0.4); // Randomize daily IV slightly
                const z = (rand2 + rand3 - 1) * 1.73; // Simple normal approximation
                
                const changePercent = (mu * dt) + (sigma * Math.sqrt(dt) * z);
                const prevClose = currentPrice;
                currentPrice = currentPrice * (1 + changePercent);
                
                // Intraday path generation metrics
                const dailyVol = sigma * Math.sqrt(dt);
                const high = Math.max(prevClose, currentPrice) * (1 + rand1 * dailyVol * 0.5);
                const low = Math.min(prevClose, currentPrice) * (1 - rand2 * dailyVol * 0.5);
                const open = prevClose * (1 + (rand3 - 0.5) * dailyVol * 0.2);
                
                // Save daily record
                const dayData = {
                    date: dateStr,
                    open: parseFloat(open.toFixed(2)),
                    high: parseFloat(high.toFixed(2)),
                    low: parseFloat(low.toFixed(2)),
                    close: parseFloat(currentPrice.toFixed(2)),
                    iv: parseFloat(iv.toFixed(2)),
                    riskFreeRate: 0.07 // 7% standard Indian G-Sec yield
                };
                
                // Filter records within the user's selected range
                if (currentDate >= start && currentDate <= end) {
                    data.push(dayData);
                }
            }
            // Move to next day
            currentDate.setDate(currentDate.getDate() + 1);
        }
        
        return data;
    }

    return {
        getHistoricalData: getHistoricalData
    };
})();

// Export for ES Modules or Browser global
if (typeof module !== 'undefined' && module.exports) {
    module.exports = MockDataEngine;
} else {
    window.MockDataEngine = MockDataEngine;
}
