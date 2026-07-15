/**
 * Options Backtesting Engine for Nifty & Bank Nifty
 * Performs Black-Scholes pricing, intraday path simulations, 
 * SL/TP monitoring, and performance metrics aggregation.
 */

const BacktestEngine = (function() {

    // --- Standard Normal Distribution Helpers ---
    function normalPDF(x) {
        return Math.exp(-0.5 * x * x) / Math.sqrt(2 * Math.PI);
    }

    function normalCDF(x) {
        const b1 = 0.319381530;
        const b2 = -0.356563782;
        const b3 = 1.781477937;
        const b4 = -1.821255978;
        const b5 = 1.330274429;
        const p = 0.2316419;
        const c = 0.39894228;

        if (x >= 0.0) {
            let t = 1.0 / (1.0 + p * x);
            return (1.0 - c * Math.exp(-x * x / 2.0) * t *
                (t * (t * (t * (t * b5 + b4) + b3) + b2) + b1));
        } else {
            let t = 1.0 / (1.0 - p * x);
            return (c * Math.exp(-x * x / 2.0) * t *
                (t * (t * (t * (t * b5 + b4) + b3) + b2) + b1));
        }
    }

    // --- Black-Scholes Formula ---
    function blackScholes(type, S, K, T, r, v) {
        if (T <= 0.0001) { // Near or at expiry, settle at intrinsic value
            if (type === 'C') return Math.max(0, S - K);
            if (type === 'P') return Math.max(0, K - S);
        }
        
        v = Math.max(v, 0.0001); // Avoid division by zero
        
        const d1 = (Math.log(S / K) + (r + (v * v) / 2) * T) / (v * Math.sqrt(T));
        const d2 = d1 - v * Math.sqrt(T);
        
        if (type === 'C') {
            return S * normalCDF(d1) - K * Math.exp(-r * T) * normalCDF(d2);
        } else {
            return K * Math.exp(-r * T) * normalCDF(-d2) - S * normalCDF(-d1);
        }
    }

    // --- Greeks Calculation ---
    function calculateGreeks(type, S, K, T, r, v) {
        if (T <= 0.0001) {
            return { delta: type === 'C' ? (S > K ? 1.0 : 0.0) : (S < K ? -1.0 : 0.0), theta: 0.0 };
        }
        v = Math.max(v, 0.0001);
        const d1 = (Math.log(S / K) + (r + (v * v) / 2) * T) / (v * Math.sqrt(T));
        const d2 = d1 - v * Math.sqrt(T);
        
        let delta = 0;
        let theta = 0;
        
        if (type === 'C') {
            delta = normalCDF(d1);
            theta = -(S * normalPDF(d1) * v) / (2 * Math.sqrt(T)) - r * K * Math.exp(-r * T) * normalCDF(d2);
        } else {
            delta = normalCDF(d1) - 1;
            theta = -(S * normalPDF(d1) * v) / (2 * Math.sqrt(T)) + r * K * Math.exp(-r * T) * normalCDF(-d2);
        }
        
        return {
            delta: parseFloat(delta.toFixed(3)),
            theta: parseFloat((theta / 365.25).toFixed(3)) // Daily decay
        };
    }

    // --- Format Date Helper ---
    function formatDate(date) {
        const y = date.getFullYear();
        const m = String(date.getMonth() + 1).padStart(2, '0');
        const d = String(date.getDate()).padStart(2, '0');
        return `${y}-${m}-${d}`;
    }

    // --- Expiry Resolver ---
    function getExpiryDate(currentDateStr, expiryType, indexName) {
        const current = new Date(currentDateStr);
        const year = current.getFullYear();
        const month = current.getMonth();
        
        if (expiryType === 'MONTHLY') {
            // Last Thursday of the month
            const lastDay = new Date(year, month + 1, 0);
            while (lastDay.getDay() !== 4) {
                lastDay.setDate(lastDay.getDate() - 1);
            }
            if (current > lastDay) {
                const nextMonthLastDay = new Date(year, month + 2, 0);
                while (nextMonthLastDay.getDay() !== 4) {
                    nextMonthLastDay.setDate(nextMonthLastDay.getDate() - 1);
                }
                return formatDate(nextMonthLastDay);
            }
            return formatDate(lastDay);
        } else {
            // Weekly Expiry
            // Nifty: Thursday, Bank Nifty: Wednesday
            const targetDay = indexName.toUpperCase() === 'BANKNIFTY' ? 3 : 4;
            let nextExpiry = new Date(current);
            const currentDay = nextExpiry.getDay();
            
            let daysToAdd = (targetDay - currentDay + 7) % 7;
            nextExpiry.setDate(nextExpiry.getDate() + daysToAdd);
            
            return formatDate(nextExpiry);
        }
    }

    // --- Strike Price Resolver ---
    function getStrikePrice(spot, indexName, legType, strikeSelection) {
        const isNifty = indexName.toUpperCase() === 'NIFTY';
        const step = isNifty ? 50 : 100;
        const atm = Math.round(spot / step) * step;
        
        if (strikeSelection === 'ATM') return atm;
        
        const isCall = legType.toUpperCase() === 'C';
        const direction = isCall ? 1 : -1; // Call OTM is above ATM, Put OTM is below ATM
        
        if (strikeSelection === 'OTM1') return atm + direction * step;
        if (strikeSelection === 'OTM2') return atm + direction * step * 2;
        if (strikeSelection === 'OTM3') return atm + direction * step * 3;
        if (strikeSelection === 'ITM1') return atm - direction * step;
        if (strikeSelection === 'ITM2') return atm - direction * step * 2;
        if (strikeSelection === 'ITM3') return atm - direction * step * 3;
        
        const offset = parseInt(strikeSelection, 10);
        if (!isNaN(offset)) {
            return atm + offset;
        }
        
        return atm;
    }

    // --- Intraday Path Interpolation ---
    // Generates 25 ticks (15-min intervals from 9:15 to 15:30)
    function generateIntradayTicks(open, high, low, close, seed) {
        function seedRandom(s) {
            let x = Math.sin(s) * 10000;
            return x - Math.floor(x);
        }
        
        const ticksCount = 25;
        const ticks = new Array(ticksCount);
        ticks[0] = open;
        ticks[ticksCount - 1] = close;
        
        // Pick random indices for High and Low
        let highIdx = 1 + Math.floor(seedRandom(seed) * (ticksCount - 2));
        let lowIdx = 1 + Math.floor(seedRandom(seed + 1.2) * (ticksCount - 2));
        if (highIdx === lowIdx) {
            lowIdx = (lowIdx + 5) % (ticksCount - 2) + 1;
        }
        
        ticks[highIdx] = high;
        ticks[lowIdx] = low;
        
        // Fill in the rest with Brownian bridge interpolation
        for (let i = 1; i < ticksCount - 1; i++) {
            if (i === highIdx || i === lowIdx) continue;
            
            // Find boundaries
            let prevIdx = 0;
            for (let j = i - 1; j >= 0; j--) {
                if (ticks[j] !== undefined) {
                    prevIdx = j;
                    break;
                }
            }
            let nextIdx = ticksCount - 1;
            for (let j = i + 1; j < ticksCount; j++) {
                if (ticks[j] !== undefined) {
                    nextIdx = j;
                    break;
                }
            }
            
            const dist = nextIdx - prevIdx;
            const weightNext = (i - prevIdx) / dist;
            const weightPrev = 1 - weightNext;
            
            // Linear interpolation + noise
            const interpolated = ticks[prevIdx] * weightPrev + ticks[nextIdx] * weightNext;
            const noiseFactor = 0.001 * (seedRandom(seed + i * 0.7) - 0.5);
            ticks[i] = interpolated * (1 + noiseFactor);
        }
        
        // Clamp ticks to make sure they do not exceed High or go below Low
        for (let i = 0; i < ticksCount; i++) {
            ticks[i] = Math.max(low, Math.min(high, ticks[i]));
            ticks[i] = parseFloat(ticks[i].toFixed(2));
        }
        
        return {
            ticks: ticks,
            highIdx: highIdx,
            lowIdx: lowIdx
        };
    }

    // Get time string corresponding to tick index
    function getTickTimeStr(tickIdx) {
        const startMinutes = 9 * 60 + 15; // 09:15 AM
        const currentMinutes = startMinutes + tickIdx * 15;
        const h = Math.floor(currentMinutes / 60);
        const m = currentMinutes % 60;
        return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
    }

    // --- Run Backtest ---
    function calculateEMA(prices, period) {
        const ema = new Array(prices.length).fill(null);
        if (prices.length < period) return ema;
        
        let sum = 0;
        for (let i = 0; i < period; i++) {
            sum += prices[i];
        }
        let currentEma = sum / period;
        ema[period - 1] = parseFloat(currentEma.toFixed(2));
        
        const k = 2 / (period + 1);
        for (let i = period; i < prices.length; i++) {
            currentEma = prices[i] * k + currentEma * (1 - k);
            ema[i] = parseFloat(currentEma.toFixed(2));
        }
        return ema;
    }

    function getLotSize(indexName, dateStr) {
        const date = new Date(dateStr);
        const index = indexName.toUpperCase();
        if (index === 'NIFTY') {
            if (date < new Date('2024-11-20')) return 25;
            if (date <= new Date('2025-12-31')) return 75;
            return 65;
        } else if (index === 'BANKNIFTY') {
            if (date < new Date('2024-11-20')) return 15;
            if (date <= new Date('2025-12-31')) return 35;
            return 30;
        }
        return 1;
    }

    // --- Run Backtest ---
    function run(params) {
        const {
            indexName,
            startDate,
            endDate,
            legs, // Array of leg: { type: 'C'/'P', position: 'BUY'/'SELL', strike: 'ATM'/'OTM1'..., qty: number, expiry: 'WEEKLY'/'MONTHLY' }
            entryTimeStr, // e.g. "09:20"
            exitTimeStr,  // e.g. "15:15"
            slType,       // 'NONE', 'PERCENT', 'POINTS'
            slVal,        // Stop loss value
            tpType,       // 'NONE', 'PERCENT', 'POINTS'
            tpVal,        // Target value
            capital,      // Starting capital, e.g. 500000
            signalMode,   // 'ALWAYS' or 'EMA_CROSS'
            emaPeriod,    // e.g. 20
            emaStrike,    // e.g. 'ATM'
            emaLots,      // e.g. 1
            feedMode      // 'REAL' or 'MOCK'
        } = params;

        // Get lot size
        const lotSize = getLotSize(indexName, startDate);
        
        // Fetch daily index records (with warmup starting from 2024-01-01)
        let fullRecords = [];
        const isReal = feedMode === 'REAL';
        
        if (isReal) {
            const realData = typeof window !== 'undefined' ? window.RealHistoricalData : (typeof global !== 'undefined' ? global.RealHistoricalData : null);
            if (realData && realData[indexName.toUpperCase()]) {
                // Filter records by date
                fullRecords = realData[indexName.toUpperCase()].filter(r => new Date(r.date) <= new Date(endDate));
            }
        } else {
            const dataEngine = typeof window !== 'undefined' ? window.MockDataEngine : (typeof global !== 'undefined' ? global.MockDataEngine : null);
            fullRecords = dataEngine ? 
                dataEngine.getHistoricalData(indexName, '2024-01-01', endDate) : [];
        }
            
        if (fullRecords.length === 0) {
            return { error: "No historical data found for selected range." };
        }

        // Calculate EMA on the full historical series
        const closePrices = fullRecords.map(r => r.close);
        const emaValues = calculateEMA(closePrices, emaPeriod || 20);

        // Convert entry/exit times to tick indices (0 to 24)
        function timeToTickIdx(timeStr) {
            const parts = timeStr.split(':');
            const minutes = parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10);
            const startMinutes = 9 * 60 + 15; // 09:15
            const tick = Math.round((minutes - startMinutes) / 15);
            return Math.max(0, Math.min(24, tick));
        }

        const entryTick = timeToTickIdx(entryTimeStr);
        const exitTick = timeToTickIdx(exitTimeStr);

        if (signalMode === 'EMA_CROSS_15MIN') {
            // Check if we have actual intraday data
            const realIntraday = typeof window !== 'undefined' ? window.RealIntradayData : (typeof global !== 'undefined' ? global.RealIntradayData : null);

            // Flatten all ticks in fullRecords
            const allTicks = [];
            for (let d = 0; d < fullRecords.length; d++) {
                const record = fullRecords[d];
                
                // Try to find real intraday ticks for this date
                let dayTicks = null;
                if (isReal && realIntraday && realIntraday[indexName.toUpperCase()]) {
                    const ticksForDay = realIntraday[indexName.toUpperCase()].filter(t => t.date === record.date);
                    if (ticksForDay && ticksForDay.length > 0) {
                        dayTicks = ticksForDay.sort((a, b) => a.tickIdx - b.tickIdx);
                    }
                }
                
                if (dayTicks) {
                    // Use real intraday candles!
                    dayTicks.forEach(tick => {
                        allTicks.push({
                            date: record.date,
                            tickIdx: tick.tickIdx,
                            spot: tick.spot,
                            iv: record.iv / 100,
                            r: record.riskFreeRate,
                            dayIdx: d,
                            record: record
                        });
                    });
                } else {
                    // Fall back to mathematically simulated ticks from daily OHLC
                    const spotTicksData = generateIntradayTicks(record.open, record.high, record.low, record.close, d);
                    const spots = spotTicksData.ticks;
                    for (let t = 0; t < 25; t++) {
                        allTicks.push({
                            date: record.date,
                            tickIdx: t,
                            spot: spots[t],
                            iv: record.iv / 100,
                            r: record.riskFreeRate,
                            dayIdx: d,
                            record: record
                        });
                    }
                }
            }

            // Calculate continuous 15-minute EMA
            const spotPrices = allTicks.map(t => t.spot);
            const ema15MinValues = calculateEMA(spotPrices, emaPeriod || 20);

            // Calculate daily close EMA for chart purposes
            const dailyCloses = fullRecords.map(r => r.close);
            const dailyEmaValues = calculateEMA(dailyCloses, emaPeriod || 20);

            let currentCapital = capital;
            let cumulativePnL = 0;
            const tradeLogs = [];
            const dailyPnLMap = {};
            const dailySignalMap = {};

            let activeTrade = null;
            let totalWinAmount = 0;
            let totalLossAmount = 0;
            let wins = 0;
            let losses = 0;
            let peakCapital = capital;
            let maxDrawdown = 0;
            let totalTrades = 0;

            const userStart = new Date(startDate);
            const userEnd = new Date(endDate);
            const lastEntryTick = Math.max(entryTick, exitTick - 2);

            for (let i = 2; i < allTicks.length; i++) {
                const tick = allTicks[i];
                const tickDate = new Date(tick.date);
                const isWithinRange = tickDate >= userStart && tickDate <= userEnd;
                if (!isWithinRange) continue;

                const tickIdx = tick.tickIdx;
                const spot = tick.spot;
                const emaVal = ema15MinValues[i];

                const prevSpot1 = allTicks[i-1].spot;
                const prevEma1 = ema15MinValues[i-1];
                const prevSpot2 = allTicks[i-2].spot;
                const prevEma2 = ema15MinValues[i-2];

                const isExitTime = tickIdx === exitTick;

                // 1. Manage active trade
                if (activeTrade) {
                    const daysDiff = Math.max(0, Math.round((new Date(activeTrade.expiry) - new Date(tick.date)) / (1000 * 60 * 60 * 24)));
                    const hoursLeftToday = (15.5 - (9 + (tickIdx * 15) / 60));
                    const T_tick = (daysDiff + (hoursLeftToday / 24)) / 365.25;

                    const currentPremium = blackScholes(activeTrade.type, spot, activeTrade.strike, T_tick, tick.r, tick.iv);
                    let pnl = (currentPremium - activeTrade.entryPremium) * activeTrade.qty;

                    let closeTrade = false;
                    let status = 'TIME_EXIT';
                    let exitPremium = currentPremium;

                    // Check SL
                    if (slType !== 'NONE' && slVal > 0) {
                        const limitPremium = activeTrade.entryPremium * (1 - slVal / 100);
                        if (currentPremium <= limitPremium) {
                            closeTrade = true;
                            status = 'SL_HIT';
                            exitPremium = limitPremium;
                            pnl = (exitPremium - activeTrade.entryPremium) * activeTrade.qty;
                        }
                    }

                    // Check TP
                    if (tpType !== 'NONE' && tpVal > 0) {
                        const limitPremium = activeTrade.entryPremium * (1 + tpVal / 100);
                        if (currentPremium >= limitPremium) {
                            closeTrade = true;
                            status = 'TP_HIT';
                            exitPremium = limitPremium;
                            pnl = (exitPremium - activeTrade.entryPremium) * activeTrade.qty;
                        }
                    }

                    // Square off at exit time
                    if (isExitTime) {
                        closeTrade = true;
                        status = 'TIME_EXIT';
                        exitPremium = currentPremium;
                        pnl = (exitPremium - activeTrade.entryPremium) * activeTrade.qty;
                    }

                    if (closeTrade) {
                        pnl = parseFloat(pnl.toFixed(2));
                        
                        tradeLogs.push({
                            date: activeTrade.entryDate,
                            spotAtEntry: activeTrade.entrySpot,
                            spotAtExit: spot,
                            signalType: activeTrade.type === 'C' ? 'Bullish (15-Min CE Buy)' : 'Bearish (15-Min PE Buy)',
                            legs: [{
                                type: activeTrade.type,
                                position: 'BUY',
                                strike: activeTrade.strike,
                                qty: activeTrade.qty,
                                entryPremium: activeTrade.entryPremium,
                                exitPremium: parseFloat(exitPremium.toFixed(2)),
                                status: status,
                                exitTime: getTickTimeStr(tickIdx),
                                pnl: pnl,
                                delta: activeTrade.delta,
                                theta: activeTrade.theta
                            }],
                            totalPnL: pnl
                        });

                        if (!dailyPnLMap[activeTrade.entryDate]) {
                            dailyPnLMap[activeTrade.entryDate] = 0;
                        }
                        dailyPnLMap[activeTrade.entryDate] += pnl;

                        totalTrades++;
                        if (pnl > 0) {
                            wins++;
                            totalWinAmount += pnl;
                        } else {
                            losses++;
                            totalLossAmount += Math.abs(pnl);
                        }

                        activeTrade = null;
                    }
                }

                // 2. Check crossover entries
                if (!activeTrade && tickIdx >= entryTick && tickIdx <= lastEntryTick && prevEma1 !== null && prevEma2 !== null) {
                    let signal = 'NONE';
                    if (prevSpot1 > prevEma1 && prevSpot2 <= prevEma2) {
                        signal = 'BULLISH';
                    } else if (prevSpot1 < prevEma1 && prevSpot2 >= prevEma2) {
                        signal = 'BEARISH';
                    }

                    if (signal !== 'NONE') {
                        const legType = signal === 'BULLISH' ? 'C' : 'P';
                        const strikePrice = getStrikePrice(spot, indexName, legType, emaStrike || 'ATM');
                        const expiryDateStr = getExpiryDate(tick.date, 'WEEKLY', indexName);

                        const daysDiff = Math.max(0, Math.round((new Date(expiryDateStr) - new Date(tick.date)) / (1000 * 60 * 60 * 24)));
                        const hoursLeftToday = (15.5 - (9 + (tickIdx * 15) / 60));
                        const T_entry = (daysDiff + (hoursLeftToday / 24)) / 365.25;

                        const entryPremium = blackScholes(legType, spot, strikePrice, T_entry, tick.r, tick.iv);
                        const greeks = calculateGreeks(legType, spot, strikePrice, T_entry, tick.r, tick.iv);

                        activeTrade = {
                            type: legType,
                            strike: strikePrice,
                            expiry: expiryDateStr,
                            entryPremium: parseFloat(entryPremium.toFixed(2)),
                            qty: (emaLots || 1) * getLotSize(indexName, tick.date),
                            entryDate: tick.date,
                            entrySpot: spot,
                            delta: greeks.delta,
                            theta: greeks.theta
                        };

                        dailySignalMap[tick.date] = signal;
                    }
                }
            }

            // 3. Compile daily outcomes
            const dailyPnLList = [];
            const chartData = [];

            for (let d = 0; d < fullRecords.length; d++) {
                const record = fullRecords[d];
                const dateObj = new Date(record.date);
                const isWithinRange = dateObj >= userStart && dateObj <= userEnd;
                if (!isWithinRange) continue;

                const dayPnL = parseFloat((dailyPnLMap[record.date] || 0).toFixed(2));
                currentCapital += dayPnL;
                cumulativePnL += dayPnL;

                if (currentCapital > peakCapital) {
                    peakCapital = currentCapital;
                }
                const dd = ((peakCapital - currentCapital) / peakCapital) * 100;
                if (dd > maxDrawdown) {
                    maxDrawdown = dd;
                }

                dailyPnLList.push({
                    date: record.date,
                    pnl: dayPnL,
                    cumulativePnL: parseFloat(cumulativePnL.toFixed(2)),
                    capital: parseFloat(currentCapital.toFixed(2)),
                    spot: record.close
                });

                chartData.push({
                    date: record.date,
                    spot: record.close,
                    ema: dailyEmaValues[d],
                    signal: dailySignalMap[record.date] || 'NONE'
                });
            }

            if (dailyPnLList.length === 0) {
                return { error: "No historical data records found within the selected date range. Please check your Start and End dates." };
            }

            // --- Aggregated Performance Metrics ---
            const winRate = totalTrades > 0 ? (wins / totalTrades) * 100 : 0;
            const profitFactor = totalLossAmount > 0 ? (totalWinAmount / totalLossAmount) : totalWinAmount > 0 ? 999 : 0;
            const avgWin = wins > 0 ? (totalWinAmount / wins) : 0;
            const avgLoss = losses > 0 ? (totalLossAmount / losses) : 0;
            const expectancy = totalTrades > 0 ? (cumulativePnL / totalTrades) : 0;
            const roi = (cumulativePnL / capital) * 100;

            let sharpe = 0;
            if (dailyPnLList.length > 1) {
                const returns = dailyPnLList.map(d => d.pnl / capital);
                const meanReturn = returns.reduce((a, b) => a + b, 0) / returns.length;
                const variance = returns.reduce((a, b) => a + Math.pow(b - meanReturn, 2), 0) / (returns.length - 1);
                const stdDev = Math.sqrt(variance);
                const dailyRf = 0.07 / 252;
                sharpe = stdDev > 0 ? (meanReturn - dailyRf) / stdDev * Math.sqrt(252) : 0;
            }

            return {
                summary: {
                    totalDays: totalTrades,
                    winningDays: wins,
                    losingDays: losses,
                    winRate: parseFloat(winRate.toFixed(2)),
                    profitFactor: parseFloat(profitFactor.toFixed(2)),
                    totalPnL: parseFloat(cumulativePnL.toFixed(2)),
                    roi: parseFloat(roi.toFixed(2)),
                    maxDrawdown: parseFloat(maxDrawdown.toFixed(2)),
                    avgWinDay: parseFloat(avgWin.toFixed(2)),
                    avgLossDay: parseFloat(avgLoss.toFixed(2)),
                    expectancy: parseFloat(expectancy.toFixed(2)),
                    sharpeRatio: parseFloat(sharpe.toFixed(2)),
                    finalCapital: parseFloat(currentCapital.toFixed(2))
                },
                dailyPnL: dailyPnLList,
                tradeLogs: tradeLogs,
                chartData: chartData
            };
        }

        let currentCapital = capital;
        const tradeLogs = [];
        const dailyPnLList = [];
        let cumulativePnL = 0;
        
        // Keep track of statistics
        let totalTrades = 0;
        let winningDays = 0;
        let losingDays = 0;
        let totalWinAmount = 0;
        let totalLossAmount = 0;
        let maxDrawdown = 0;
        let peakCapital = capital;

        // Expose index and EMA values for chart
        const chartData = [];

        // Loop through all records (but only trade within requested range)
        for (let d = 0; d < fullRecords.length; d++) {
            const record = fullRecords[d];
            const emaVal = emaValues[d];
            
            // Check range boundaries
            const recordDate = new Date(record.date);
            const userStart = new Date(startDate);
            const userEnd = new Date(endDate);
            const isWithinRange = recordDate >= userStart && recordDate <= userEnd;

            // 1. Calculate crossover signal from yesterday
            let signal = 'NONE';
            if (d >= 2 && emaValues[d-1] !== null && emaValues[d-2] !== null) {
                const prevClose1 = fullRecords[d-1].close;
                const prevClose2 = fullRecords[d-2].close;
                const prevEma1 = emaValues[d-1];
                const prevEma2 = emaValues[d-2];

                // Crossover checks:
                // Bullish Cross: Yesterday's Close > Yesterday's EMA AND Day before close <= Day before EMA
                if (prevClose1 > prevEma1 && prevClose2 <= prevEma2) {
                    signal = 'BULLISH';
                }
                // Bearish Cross: Yesterday's Close < Yesterday's EMA AND Day before close >= Day before EMA
                else if (prevClose1 < prevEma1 && prevClose2 >= prevEma2) {
                    signal = 'BEARISH';
                }
            }

            if (isWithinRange) {
                chartData.push({
                    date: record.date,
                    spot: record.close,
                    ema: emaVal,
                    signal: signal
                });
            }

            if (!isWithinRange) {
                continue; // Skip execution if outside date range
            }

            // Determine strategy legs to execute today
            let todayLegs = [];
            if (signalMode === 'EMA_CROSS' || signalMode === 'EMA_CROSS_DAILY') {
                if (signal === 'BULLISH') {
                    // Buy CE
                    todayLegs = [{ type: 'C', position: 'BUY', strike: emaStrike || 'ATM', qty: emaLots || 1, expiry: 'WEEKLY' }];
                } else if (signal === 'BEARISH') {
                    // Buy PE
                    todayLegs = [{ type: 'P', position: 'BUY', strike: emaStrike || 'ATM', qty: emaLots || 1, expiry: 'WEEKLY' }];
                } else {
                    // No signal - record flat day and continue
                    dailyPnLList.push({
                        date: record.date,
                        pnl: 0,
                        cumulativePnL: parseFloat(cumulativePnL.toFixed(2)),
                        capital: parseFloat(currentCapital.toFixed(2)),
                        spot: record.close
                    });
                    continue;
                }
            } else {
                todayLegs = legs;
            }

            const spotTicksData = generateIntradayTicks(record.open, record.high, record.low, record.close, d);
            const spots = spotTicksData.ticks;
            const iv = record.iv / 100; // decimal IV
            const r = record.riskFreeRate;
            
            const entrySpot = spots[entryTick];
            const activeLegs = [];
            
            // 1. Setup strategy legs at entry tick
            for (let i = 0; i < todayLegs.length; i++) {
                const legDef = todayLegs[i];
                const strikePrice = getStrikePrice(entrySpot, indexName, legDef.type, legDef.strike);
                const expiryDateStr = getExpiryDate(record.date, legDef.expiry, indexName);
                
                // Calculate time to expiry in years
                const expDate = new Date(expiryDateStr);
                const curDate = new Date(record.date);
                const daysDiff = Math.max(0, Math.round((expDate - curDate) / (1000 * 60 * 60 * 24)));
                
                // Intraday fractional time to expiry at entry
                const hoursLeftToday = (15.5 - (parseInt(entryTimeStr.split(':')[0]) + parseInt(entryTimeStr.split(':')[1])/60));
                const T_entry = (daysDiff + (hoursLeftToday / 24)) / 365.25;

                // Price option
                const entryPremium = blackScholes(legDef.type, entrySpot, strikePrice, T_entry, r, iv);
                const greeks = calculateGreeks(legDef.type, entrySpot, strikePrice, T_entry, r, iv);
                
                activeLegs.push({
                    index: i,
                    type: legDef.type,
                    position: legDef.position,
                    strike: strikePrice,
                    qty: legDef.qty * getLotSize(indexName, record.date),
                    expiry: expiryDateStr,
                    entryPremium: parseFloat(entryPremium.toFixed(2)),
                    delta: greeks.delta,
                    theta: greeks.theta,
                    
                    // Live state
                    status: 'ACTIVE',
                    exitPremium: null,
                    exitTickIdx: null,
                    exitTimeStr: null,
                    pnl: 0
                });
            }

            // 2. Simulate intraday ticks from entryTick to exitTick
            let portfolioStopped = false;
            let exitTickSelected = exitTick;

            for (let t = entryTick + 1; t <= exitTick; t++) {
                if (portfolioStopped) break;

                const currentSpot = spots[t];
                const timeStr = getTickTimeStr(t);
                const hoursLeftToday = (15.5 - (9 + (t * 15) / 60));
                
                let dayActivePnL = 0;

                // Value each leg at this tick
                for (let i = 0; i < activeLegs.length; i++) {
                    const leg = activeLegs[i];
                    if (leg.status !== 'ACTIVE') {
                        dayActivePnL += leg.pnl;
                        continue;
                    }
                    
                    const legExpDate = new Date(leg.expiry);
                    const legCurDate = new Date(record.date);
                    const daysDiff = Math.max(0, Math.round((legExpDate - legCurDate) / (1000 * 60 * 60 * 24)));
                    const T_tick = (daysDiff + (hoursLeftToday / 24)) / 365.25;
                    
                    const currentPremium = blackScholes(leg.type, currentSpot, leg.strike, T_tick, r, iv);
                    
                    // P&L calculation per unit
                    let unitPnL = 0;
                    if (leg.position === 'BUY') {
                        unitPnL = currentPremium - leg.entryPremium;
                    } else {
                        unitPnL = leg.entryPremium - currentPremium;
                    }
                    const totalLegPnL = unitPnL * leg.qty;
                    leg.pnl = parseFloat(totalLegPnL.toFixed(2));
                    
                    // Check individual leg SL / Target
                    if (slType !== 'NONE' && slVal > 0) {
                        let isSlHit = false;
                        if (slType === 'PERCENT') {
                            const limitPremium = leg.position === 'SELL' ? 
                                leg.entryPremium * (1 + slVal / 100) : 
                                leg.entryPremium * (1 - slVal / 100);
                            
                            if (leg.position === 'SELL' && currentPremium >= limitPremium) isSlHit = true;
                            if (leg.position === 'BUY' && currentPremium <= limitPremium) isSlHit = true;
                        } else if (slType === 'POINTS') {
                            const currentDiff = currentPremium - leg.entryPremium;
                            if (leg.position === 'SELL' && currentDiff >= slVal) isSlHit = true;
                            if (leg.position === 'BUY' && currentDiff <= -slVal) isSlHit = true;
                        }

                        if (isSlHit) {
                            leg.status = 'SL_HIT';
                            leg.exitPremium = parseFloat(currentPremium.toFixed(2));
                            leg.exitTickIdx = t;
                            leg.exitTimeStr = timeStr;
                            dayActivePnL += leg.pnl;
                            continue;
                        }
                    }

                    if (tpType !== 'NONE' && tpVal > 0) {
                        let isTpHit = false;
                        if (tpType === 'PERCENT') {
                            const limitPremium = leg.position === 'SELL' ? 
                                leg.entryPremium * (1 - tpVal / 100) : 
                                leg.entryPremium * (1 + tpVal / 100);
                            
                            if (leg.position === 'SELL' && currentPremium <= limitPremium) isTpHit = true;
                            if (leg.position === 'BUY' && currentPremium >= limitPremium) isTpHit = true;
                        } else if (tpType === 'POINTS') {
                            const currentDiff = currentPremium - leg.entryPremium;
                            if (leg.position === 'SELL' && currentDiff <= -tpVal) isTpHit = true;
                            if (leg.position === 'BUY' && currentDiff >= tpVal) isTpHit = true;
                        }

                        if (isTpHit) {
                            leg.status = 'TP_HIT';
                            leg.exitPremium = parseFloat(currentPremium.toFixed(2));
                            leg.exitTickIdx = t;
                            leg.exitTimeStr = timeStr;
                            dayActivePnL += leg.pnl;
                            continue;
                        }
                    }

                    dayActivePnL += leg.pnl;
                }
            }

            // 3. Finalize any active legs at exit time
            const exitSpot = spots[exitTickSelected];
            const exitTimeActual = getTickTimeStr(exitTickSelected);
            
            let dayFinalPnL = 0;
            const tradeLogItem = {
                date: record.date,
                spotAtEntry: entrySpot,
                spotAtExit: exitSpot,
                legs: [],
                signalType: signalMode === 'EMA_CROSS' ? (signal === 'BULLISH' ? 'Bullish (Buy Call)' : 'Bearish (Buy Put)') : 'Regular'
            };

            for (let i = 0; i < activeLegs.length; i++) {
                const leg = activeLegs[i];
                if (leg.status === 'ACTIVE') {
                    const legExpDate = new Date(leg.expiry);
                    const legCurDate = new Date(record.date);
                    const daysDiff = Math.max(0, Math.round((legExpDate - legCurDate) / (1000 * 60 * 60 * 24)));
                    const hoursLeftToday = (15.5 - (9 + (exitTickSelected * 15) / 60));
                    const T_exit = (daysDiff + (hoursLeftToday / 24)) / 365.25;
                    
                    const finalPremium = blackScholes(leg.type, exitSpot, leg.strike, T_exit, r, iv);
                    leg.status = 'TIME_EXIT';
                    leg.exitPremium = parseFloat(finalPremium.toFixed(2));
                    leg.exitTickIdx = exitTickSelected;
                    leg.exitTimeStr = exitTimeActual;
                    
                    let unitPnL = 0;
                    if (leg.position === 'BUY') {
                        unitPnL = finalPremium - leg.entryPremium;
                    } else {
                        unitPnL = leg.entryPremium - finalPremium;
                    }
                    leg.pnl = parseFloat((unitPnL * leg.qty).toFixed(2));
                }
                
                dayFinalPnL += leg.pnl;
                
                tradeLogItem.legs.push({
                    type: leg.type,
                    position: leg.position,
                    strike: leg.strike,
                    qty: leg.qty,
                    entryPremium: leg.entryPremium,
                    exitPremium: leg.exitPremium,
                    status: leg.status,
                    exitTime: leg.exitTimeStr,
                    pnl: leg.pnl,
                    delta: leg.delta,
                    theta: leg.theta
                });
            }

            dayFinalPnL = parseFloat(dayFinalPnL.toFixed(2));
            tradeLogItem.totalPnL = dayFinalPnL;
            tradeLogs.push(tradeLogItem);
            
            // Update performance stats
            totalTrades++;
            if (dayFinalPnL > 0) {
                winningDays++;
                totalWinAmount += dayFinalPnL;
            } else if (dayFinalPnL < 0) {
                losingDays++;
                totalLossAmount += Math.abs(dayFinalPnL);
            }
            
            cumulativePnL += dayFinalPnL;
            currentCapital += dayFinalPnL;
            
            // Drawdown calculation
            if (currentCapital > peakCapital) {
                peakCapital = currentCapital;
            }
            const dd = ((peakCapital - currentCapital) / peakCapital) * 100;
            if (dd > maxDrawdown) {
                maxDrawdown = dd;
            }

            dailyPnLList.push({
                date: record.date,
                pnl: dayFinalPnL,
                cumulativePnL: parseFloat(cumulativePnL.toFixed(2)),
                capital: parseFloat(currentCapital.toFixed(2)),
                spot: record.close
            });
        }

        if (dailyPnLList.length === 0) {
            return { error: "No historical data records found within the selected date range. Please check your Start and End dates." };
        }

        // --- Aggregated Performance Metrics ---
        const winRate = totalTrades > 0 ? (winningDays / totalTrades) * 100 : 0;
        const profitFactor = totalLossAmount > 0 ? (totalWinAmount / totalLossAmount) : totalWinAmount > 0 ? 999 : 0;
        const avgWin = winningDays > 0 ? (totalWinAmount / winningDays) : 0;
        const avgLoss = losingDays > 0 ? (totalLossAmount / losingDays) : 0;
        const expectancy = totalTrades > 0 ? (cumulativePnL / totalTrades) : 0;
        const roi = (cumulativePnL / capital) * 100;

        let sharpe = 0;
        if (dailyPnLList.length > 1) {
            const returns = dailyPnLList.map(d => d.pnl / capital);
            const meanReturn = returns.reduce((a, b) => a + b, 0) / returns.length;
            const variance = returns.reduce((a, b) => a + Math.pow(b - meanReturn, 2), 0) / (returns.length - 1);
            const stdDev = Math.sqrt(variance);
            const dailyRf = 0.07 / 252;
            sharpe = stdDev > 0 ? (meanReturn - dailyRf) / stdDev * Math.sqrt(252) : 0;
        }

        return {
            summary: {
                totalDays: totalTrades,
                winningDays: winningDays,
                losingDays: losingDays,
                winRate: parseFloat(winRate.toFixed(2)),
                profitFactor: parseFloat(profitFactor.toFixed(2)),
                totalPnL: parseFloat(cumulativePnL.toFixed(2)),
                roi: parseFloat(roi.toFixed(2)),
                maxDrawdown: parseFloat(maxDrawdown.toFixed(2)),
                avgWinDay: parseFloat(avgWin.toFixed(2)),
                avgLossDay: parseFloat(avgLoss.toFixed(2)),
                expectancy: parseFloat(expectancy.toFixed(2)),
                sharpeRatio: parseFloat(sharpe.toFixed(2)),
                finalCapital: parseFloat(currentCapital.toFixed(2))
            },
            dailyPnL: dailyPnLList,
            tradeLogs: tradeLogs,
            chartData: chartData
        };
    }

    return {
        run: run,
        blackScholes: blackScholes,
        calculateGreeks: calculateGreeks,
        getExpiryDate: getExpiryDate,
        getStrikePrice: getStrikePrice
    };
})();

// Export for ES Modules or Browser global
if (typeof module !== 'undefined' && module.exports) {
    module.exports = BacktestEngine;
} else {
    window.BacktestEngine = BacktestEngine;
}
