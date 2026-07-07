/**
 * DeltaForge Terminal Orchestrator (app.js)
 * Manages UI events, presets, strategy builder state, Chart.js renderings,
 * and calls the BacktestEngine.
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize Lucide Icons
    lucide.createIcons();

    // Application State
    let state = {
        indexName: 'NIFTY',
        startDate: '2024-01-01',
        endDate: '2024-06-30',
        entryTime: '09:20',
        exitTime: '15:15',
        capital: 500000,
        slType: 'NONE',
        slVal: 25,
        tpType: 'NONE',
        tpVal: 50,
        legs: [],
        signalMode: 'ALWAYS',
        emaPeriod: 20,
        emaStrike: 'ATM',
        emaLots: 1,
        feedMode: 'REAL'
    };

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

    // Chart instances
    let equityChartInstance = null;
    let payoffChartInstance = null;
    let spotChartInstance = null;
    let currentBacktestResults = null;

    // --- Select Elements ---
    const indexToggle = document.getElementById('indexToggle');
    const feedToggle = document.getElementById('feedToggle');
    const inputStartDate = document.getElementById('startDate');
    const inputEndDate = document.getElementById('endDate');
    const selectEntryTime = document.getElementById('entryTime');
    const selectExitTime = document.getElementById('exitTime');
    const inputCapital = document.getElementById('capital');
    const selectSlType = document.getElementById('slType');
    const inputSlVal = document.getElementById('slVal');
    const selectTpType = document.getElementById('tpType');
    const inputTpVal = document.getElementById('tpVal');
    const selectSignalMode = document.getElementById('signalMode');
    const inputEmaPeriod = document.getElementById('emaPeriod');
    const inputEmaStrike = document.getElementById('emaStrike');
    const inputEmaLots = document.getElementById('emaLots');
    const btnDecLots = document.getElementById('decLotsBtn');
    const btnIncLots = document.getElementById('incLotsBtn');
    const emaPeriodGroup = document.getElementById('emaPeriodGroup');
    const legsContainer = document.getElementById('legsContainer');
    const addLegBtn = document.getElementById('addLegBtn');
    const runBtn = document.getElementById('runBacktestBtn');
    
    // UI Panel Toggles
    const welcomePanel = document.getElementById('welcomePanel');
    const resultsPanel = document.getElementById('resultsPanel');
    const loadingOverlay = document.getElementById('loadingOverlay');
    const loadingText = document.getElementById('loadingText');
    const loadingSub = document.getElementById('loadingSub');

    // Payoff Control Elements
    const spotSlider = document.getElementById('spotSlider');
    const spotSliderVal = document.getElementById('spotSliderVal');

    // Tickers
    const tickerNifty = document.getElementById('tickerNifty');
    const tickerBankNifty = document.getElementById('tickerBankNifty');

    // --- Ticker Simulator ---
    let niftyLiveVal = 23450.25;
    let bankNiftyLiveVal = 51280.90;
    
    setInterval(() => {
        niftyLiveVal += (Math.random() - 0.5) * 4;
        bankNiftyLiveVal += (Math.random() - 0.5) * 12;
        tickerNifty.textContent = niftyLiveVal.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        tickerBankNifty.textContent = bankNiftyLiveVal.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }, 1200);

    // --- Index Custom Theme Toggle ---
    function updateTheme(index) {
        state.indexName = index;
        const root = document.documentElement;
        if (index === 'NIFTY') {
            root.style.setProperty('--accent-theme', 'var(--accent-nifty)');
            root.style.setProperty('--accent-theme-glow', 'var(--accent-nifty-glow)');
        } else {
            root.style.setProperty('--accent-theme', 'var(--accent-banknifty)');
            root.style.setProperty('--accent-theme-glow', 'var(--accent-banknifty-glow)');
        }
        
        // Refresh slider limits based on index
        const currentSpot = index === 'NIFTY' ? 22000 : 48000;
        spotSlider.min = currentSpot * 0.92;
        spotSlider.max = currentSpot * 1.08;
        spotSlider.value = currentSpot;
        spotSliderVal.textContent = Math.round(currentSpot).toLocaleString('en-IN');
        
        if (currentBacktestResults) {
            drawPayoffChart(Math.round(currentSpot));
        }
    }

    // Bind Index Toggle buttons
    indexToggle.addEventListener('click', function(e) {
        const btn = e.target.closest('.pill-btn');
        if (!btn) return;
        
        indexToggle.querySelectorAll('.pill-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        updateTheme(btn.dataset.value);
        
        // Auto reload preset to fit index strikes
        loadPreset('straddle');
    });

    // Bind Feed Toggle buttons
    feedToggle.addEventListener('click', function(e) {
        const btn = e.target.closest('.pill-btn');
        if (!btn) return;
        
        feedToggle.querySelectorAll('.pill-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        state.feedMode = btn.dataset.value;
    });

    // Bind Start Date change to update lot size labels dynamically
    inputStartDate.addEventListener('change', function() {
        state.startDate = inputStartDate.value;
        renderLegs();
    });

    // Bind Signal Mode dropdown
    const presetsSection = document.getElementById('presetsSection');
    const legsSection = document.getElementById('legsSection');
    const emaSignalIndicator = document.getElementById('emaSignalIndicator');

    selectSignalMode.addEventListener('change', function() {
        if (selectSignalMode.value.startsWith('EMA_CROSS')) {
            emaPeriodGroup.style.display = 'block';
            emaSignalIndicator.style.display = 'block';
            presetsSection.style.display = 'none';
            legsSection.style.display = 'none';
        } else {
            emaPeriodGroup.style.display = 'none';
            emaSignalIndicator.style.display = 'none';
            presetsSection.style.display = 'block';
            legsSection.style.display = 'block';
        }
        state.signalMode = selectSignalMode.value;
    });

    // Bind Lots Increment/Decrement buttons
    btnDecLots.addEventListener('click', function() {
        let currentLots = parseInt(inputEmaLots.value, 10) || 1;
        if (currentLots > 1) {
            currentLots--;
            inputEmaLots.value = currentLots;
            state.emaLots = currentLots;
        }
    });

    btnIncLots.addEventListener('click', function() {
        let currentLots = parseInt(inputEmaLots.value, 10) || 1;
        if (currentLots < 100) {
            currentLots++;
            inputEmaLots.value = currentLots;
            state.emaLots = currentLots;
        }
    });

    // --- Strategy Legs Management ---
    function addLeg(type = 'C', position = 'SELL', strike = 'ATM', qty = 1, expiry = 'WEEKLY') {
        state.legs.push({ type, position, strike, qty, expiry });
        renderLegs();
    }

    function removeLeg(index) {
        state.legs.splice(index, 1);
        renderLegs();
    }

    function renderLegs() {
        legsContainer.innerHTML = '';
        
        state.legs.forEach((leg, index) => {
            const card = document.createElement('div');
            card.className = 'leg-card';
            card.dataset.index = index;
            
            const currentLot = getLotSize(state.indexName, state.startDate);
            const lotLabel = `${currentLot} units`;

            card.innerHTML = `
                <div class="leg-header">
                    <span class="leg-num">Leg #${index + 1} (${leg.position} ${leg.type})</span>
                    <button class="remove-leg" data-action="remove">Delete</button>
                </div>
                <div class="leg-controls">
                    <!-- Buy / Sell Toggle -->
                    <div class="leg-control-group" style="grid-column: span 2;">
                        <label>Position</label>
                        <div class="toggle-group" data-field="position">
                            <div class="toggle-item ${leg.position === 'BUY' ? 'active' : ''}" data-value="BUY" data-type="BUY">BUY</div>
                            <div class="toggle-item ${leg.position === 'SELL' ? 'active' : ''}" data-value="SELL" data-type="SELL">SELL</div>
                        </div>
                    </div>
                    
                    <!-- Call / Put Toggle -->
                    <div class="leg-control-group" style="grid-column: span 2;">
                        <label>Type</label>
                        <div class="toggle-group" data-field="type">
                            <div class="toggle-item ${leg.type === 'C' ? 'active' : ''}" data-value="C" data-type="C">CE (Call)</div>
                            <div class="toggle-item ${leg.type === 'P' ? 'active' : ''}" data-value="P" data-type="P">PE (Put)</div>
                        </div>
                    </div>
                </div>
                
                <div class="leg-controls" style="margin-top: 8px;">
                    <!-- Strike Select -->
                    <div class="leg-control-group" style="grid-column: span 2;">
                        <label>Strike Selection</label>
                        <select class="leg-select" data-field="strike">
                            <option value="ATM" ${leg.strike === 'ATM' ? 'selected' : ''}>ATM</option>
                            <option value="OTM1" ${leg.strike === 'OTM1' ? 'selected' : ''}>OTM 1</option>
                            <option value="OTM2" ${leg.strike === 'OTM2' ? 'selected' : ''}>OTM 2</option>
                            <option value="OTM3" ${leg.strike === 'OTM3' ? 'selected' : ''}>OTM 3</option>
                            <option value="ITM1" ${leg.strike === 'ITM1' ? 'selected' : ''}>ITM 1</option>
                            <option value="ITM2" ${leg.strike === 'ITM2' ? 'selected' : ''}>ITM 2</option>
                            <option value="+100" ${leg.strike === '+100' ? 'selected' : ''}>+100 Offset</option>
                            <option value="-100" ${leg.strike === '-100' ? 'selected' : ''}>-100 Offset</option>
                            <option value="+200" ${leg.strike === '+200' ? 'selected' : ''}>+200 Offset</option>
                            <option value="-200" ${leg.strike === '-200' ? 'selected' : ''}>-200 Offset</option>
                        </select>
                    </div>

                    <!-- Expiry Select -->
                    <div class="leg-control-group">
                        <label>Expiry</label>
                        <select class="leg-select" data-field="expiry">
                            <option value="WEEKLY" ${leg.expiry === 'WEEKLY' ? 'selected' : ''}>Weekly</option>
                            <option value="MONTHLY" ${leg.expiry === 'MONTHLY' ? 'selected' : ''}>Monthly</option>
                        </select>
                    </div>

                    <!-- Quantity (Lots) -->
                    <div class="leg-control-group">
                        <label>Lots (${lotLabel})</label>
                        <input type="number" class="leg-input" data-field="qty" value="${leg.qty}" min="1" max="100">
                    </div>
                </div>
            `;
            
            // Event bindings inside card
            card.querySelector('.remove-leg').addEventListener('click', () => removeLeg(index));
            
            // Toggle groups
            card.querySelectorAll('.toggle-group').forEach(group => {
                const field = group.dataset.field;
                group.addEventListener('click', (e) => {
                    const toggleItem = e.target.closest('.toggle-item');
                    if (!toggleItem) return;
                    
                    group.querySelectorAll('.toggle-item').forEach(el => el.classList.remove('active'));
                    toggleItem.classList.add('active');
                    
                    state.legs[index][field] = toggleItem.dataset.value;
                });
            });

            // Selects and inputs
            card.querySelectorAll('[data-field]').forEach(element => {
                if (element.tagName === 'SELECT' || element.tagName === 'INPUT') {
                    element.addEventListener('change', (e) => {
                        let val = e.target.value;
                        if (e.target.type === 'number') {
                            val = parseInt(val, 10) || 1;
                        }
                        state.legs[index][e.target.dataset.field] = val;
                    });
                }
            });

            legsContainer.appendChild(card);
        });
    }

    addLegBtn.addEventListener('click', () => {
        addLeg('C', 'SELL', 'ATM', 1, 'WEEKLY');
    });

    // --- Strategy Presets Loader ---
    function loadPreset(presetName) {
        state.legs = [];
        
        // Reset Signal Mode to Always Active when a preset is selected
        selectSignalMode.value = 'ALWAYS';
        emaPeriodGroup.style.display = 'none';
        emaSignalIndicator.style.display = 'none';
        presetsSection.style.display = 'block';
        legsSection.style.display = 'block';
        state.signalMode = 'ALWAYS';

        if (presetName === 'straddle') {
            addLeg('C', 'SELL', 'ATM', 1, 'WEEKLY');
            addLeg('P', 'SELL', 'ATM', 1, 'WEEKLY');
        } else if (presetName === 'strangle') {
            addLeg('C', 'SELL', 'OTM1', 1, 'WEEKLY');
            addLeg('P', 'SELL', 'OTM1', 1, 'WEEKLY');
        } else if (presetName === 'condor') {
            addLeg('C', 'SELL', 'OTM1', 1, 'WEEKLY');
            addLeg('C', 'BUY', 'OTM2', 1, 'WEEKLY');
            addLeg('P', 'SELL', 'OTM1', 1, 'WEEKLY');
            addLeg('P', 'BUY', 'OTM2', 1, 'WEEKLY');
        } else if (presetName === 'bullcall') {
            addLeg('C', 'BUY', 'ATM', 1, 'WEEKLY');
            addLeg('C', 'SELL', 'OTM1', 1, 'WEEKLY');
        }
    }

    // Bind preset buttons
    document.querySelectorAll('.preset-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            loadPreset(e.target.dataset.preset);
        });
    });

    // --- Loading Overlay Controller ---
    function showLoading(text, sub, duration = 800) {
        loadingText.textContent = text;
        loadingSub.textContent = sub;
        loadingOverlay.classList.add('active');
        return new Promise(resolve => setTimeout(resolve, duration));
    }

    function hideLoading() {
        loadingOverlay.classList.remove('active');
    }

    // --- Run Backtest Action ---
    runBtn.addEventListener('click', async function() {
        state.signalMode = selectSignalMode.value;
        state.emaPeriod = parseInt(inputEmaPeriod.value, 10) || 20;
        state.emaStrike = inputEmaStrike.value || 'ATM';
        state.emaLots = parseInt(inputEmaLots.value, 10) || 1;

        if (!state.signalMode.startsWith('EMA_CROSS') && state.legs.length === 0) {
            alert("Please add at least one option leg to execute the backtest!");
            return;
        }

        // Sync main state inputs
        state.startDate = inputStartDate.value;
        state.endDate = inputEndDate.value;
        state.entryTime = selectEntryTime.value;
        state.exitTime = selectExitTime.value;
        state.capital = parseFloat(inputCapital.value) || 500000;
        state.slType = selectSlType.value;
        state.slVal = parseFloat(inputSlVal.value) || 0;
        state.tpType = selectTpType.value;
        state.tpVal = parseFloat(inputTpVal.value) || 0;

        await showLoading("Valuing Options Contracts...", "Running Black-Scholes equations for 25 intraday ticks per trading day...");
        
        try {
            // Run simulation on engine
            const results = BacktestEngine.run({
                indexName: state.indexName,
                startDate: state.startDate,
                endDate: state.endDate,
                legs: state.legs,
                entryTimeStr: state.entryTime,
                exitTimeStr: state.exitTime,
                slType: state.slType,
                slVal: state.slVal,
                tpType: state.tpType,
                tpVal: state.tpVal,
                capital: state.capital,
                signalMode: state.signalMode,
                emaPeriod: state.emaPeriod,
                emaStrike: state.emaStrike,
                emaLots: state.emaLots,
                feedMode: state.feedMode
            });

            if (results.error) {
                alert(results.error);
                hideLoading();
                return;
            }

            currentBacktestResults = results;
            
            // Switch UI views
            welcomePanel.style.display = 'none';
            resultsPanel.style.display = 'flex';

            // Render Results components
            updateMetricsDashboard(results.summary);
            drawEquityCurveChart(results.dailyPnL);
            drawSpotEmaChart(results.chartData);
            
            // Set slider default based on average index price or final spot
            const lastValidPnL = results.dailyPnL.filter(d => d.spot > 0);
            const avgSpot = lastValidPnL.length > 0 ? lastValidPnL[lastValidPnL.length - 1].spot : 22000;
            spotSlider.min = Math.round(avgSpot * 0.9);
            spotSlider.max = Math.round(avgSpot * 1.1);
            spotSlider.value = Math.round(avgSpot);
            spotSliderVal.textContent = Math.round(avgSpot).toLocaleString('en-IN');
            
            drawPayoffChart(Math.round(avgSpot));
            populateTradeLogTable(results.tradeLogs);
            renderMonthlyHeatmap(results.dailyPnL);

        } catch (err) {
            console.error(err);
            alert("An error occurred during backtesting: " + err.message);
        } finally {
            hideLoading();
        }
    });

    // --- Update Metrics Cards ---
    function updateMetricsDashboard(summary) {
        const valTotalPnL = document.getElementById('valTotalPnL');
        const valRoi = document.getElementById('valRoi');
        const valWinRate = document.getElementById('valWinRate');
        const valRatio = document.getElementById('valRatio');
        const valDrawdown = document.getElementById('valDrawdown');
        const valSharpe = document.getElementById('valSharpe');
        const valExpectancy = document.getElementById('valExpectancy');
        const valProfitFactor = document.getElementById('valProfitFactor');

        // Color coding classes helper
        function stylePnL(element, card, val) {
            if (val > 0) {
                element.className = 'metric-val positive';
                card.className = 'glass-panel metric-card positive';
            } else if (val < 0) {
                element.className = 'metric-val negative';
                card.className = 'glass-panel metric-card negative';
            } else {
                element.className = 'metric-val';
                card.className = 'glass-panel metric-card neutral';
            }
        }

        const formattedPnL = (summary.totalPnL >= 0 ? '+' : '') + '₹' + summary.totalPnL.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        valTotalPnL.textContent = formattedPnL;
        valRoi.textContent = `ROI: ${summary.roi >= 0 ? '+' : ''}${summary.roi}%`;
        stylePnL(valTotalPnL, document.getElementById('cardTotalPnL'), summary.totalPnL);

        valWinRate.textContent = `${summary.winRate}%`;
        valRatio.textContent = `Win/Loss Days: ${summary.winningDays} / ${summary.losingDays}`;
        
        valDrawdown.textContent = `${summary.maxDrawdown}%`;
        valSharpe.textContent = `Sharpe Ratio: ${summary.sharpeRatio}`;
        
        valExpectancy.textContent = (summary.expectancy >= 0 ? '+' : '') + '₹' + Math.round(summary.expectancy).toLocaleString('en-IN');
        valProfitFactor.textContent = `Profit Factor: ${summary.profitFactor}`;
    }

    // --- Draw Equity Curve Chart ---
    function drawEquityCurveChart(dailyPnL) {
        const ctx = document.getElementById('equityCurveChart').getContext('2d');
        
        const labels = dailyPnL.map(d => d.date);
        const dataCapital = dailyPnL.map(d => d.capital);
        
        if (equityChartInstance) {
            equityChartInstance.destroy();
        }

        const isProfitable = dailyPnL.length > 0 ? dailyPnL[dailyPnL.length - 1].capital >= state.capital : false;
        const colorAccent = isProfitable ? '#10b981' : '#ef4444';
        const fillGlow = isProfitable ? 'rgba(16, 185, 129, 0.05)' : 'rgba(239, 68, 68, 0.05)';

        equityChartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Portfolio Value (₹)',
                    data: dataCapital,
                    borderColor: colorAccent,
                    borderWidth: 2.5,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                    pointBackgroundColor: colorAccent,
                    fill: true,
                    backgroundColor: fillGlow,
                    tension: 0.15
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        mode: 'index',
                        intersect: false,
                        backgroundColor: 'rgba(3, 4, 10, 0.95)',
                        titleColor: '#9ca3af',
                        bodyColor: '#f3f4f6',
                        borderColor: 'rgba(255,255,255,0.08)',
                        borderWidth: 1,
                        callbacks: {
                            label: function(context) {
                                return ` Capital: ₹${context.raw.toLocaleString('en-IN')}`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { color: '#6b7280', font: { size: 10 } }
                    },
                    y: {
                        grid: { color: 'rgba(255,255,255,0.04)' },
                        ticks: { 
                            color: '#6b7280', 
                            font: { size: 10 },
                            callback: function(value) {
                                return '₹' + (value / 1000).toFixed(0) + 'k';
                            }
                        }
                    }
                }
            }
        });
    }

    // --- Draw Spot Price & EMA Crossovers Chart ---
    function drawSpotEmaChart(chartData) {
        const ctx = document.getElementById('spotEmaChart').getContext('2d');
        
        const labels = chartData.map(d => d.date);
        const dataSpot = chartData.map(d => d.spot);
        const dataEma = chartData.map(d => d.ema);
        
        if (spotChartInstance) {
            spotChartInstance.destroy();
        }

        const isNifty = state.indexName === 'NIFTY';
        const spotColor = isNifty ? '#06b6d4' : '#8b5cf6'; // Cyan vs Purple
        const emaColor = '#f59e0b'; // Amber / Orange

        spotChartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Spot Price (₹)',
                        data: dataSpot,
                        borderColor: spotColor,
                        borderWidth: 2,
                        pointRadius: function(context) {
                            if (context.dataIndex === undefined) return 0;
                            const d = chartData[context.dataIndex];
                            return (d && d.signal !== 'NONE') ? 6 : 0;
                        },
                        pointStyle: function(context) {
                            if (context.dataIndex === undefined) return 'circle';
                            const d = chartData[context.dataIndex];
                            return (d && d.signal !== 'NONE') ? 'triangle' : 'circle';
                        },
                        pointRotation: function(context) {
                            if (context.dataIndex === undefined) return 0;
                            const d = chartData[context.dataIndex];
                            return (d && d.signal === 'BEARISH') ? 180 : 0;
                        },
                        pointBackgroundColor: function(context) {
                            if (context.dataIndex === undefined) return spotColor;
                            const d = chartData[context.dataIndex];
                            return (d && d.signal === 'BULLISH') ? '#10b981' : ((d && d.signal === 'BEARISH') ? '#ef4444' : spotColor);
                        },
                        pointBorderColor: function(context) {
                            if (context.dataIndex === undefined) return spotColor;
                            const d = chartData[context.dataIndex];
                            return (d && d.signal === 'BULLISH') ? '#10b981' : ((d && d.signal === 'BEARISH') ? '#ef4444' : spotColor);
                        },
                        tension: 0.15,
                        fill: false
                    },
                    {
                        label: 'EMA (₹)',
                        data: dataEma,
                        borderColor: emaColor,
                        borderWidth: 1.5,
                        borderDash: [4, 4],
                        pointRadius: 0,
                        pointHoverRadius: 0,
                        tension: 0.15,
                        fill: false
                    },
                    {
                        label: 'Buy Call Signal',
                        data: [],
                        backgroundColor: '#10b981',
                        borderColor: '#10b981',
                        pointStyle: 'triangle',
                        showLine: false
                    },
                    {
                        label: 'Buy Put Signal',
                        data: [],
                        backgroundColor: '#ef4444',
                        borderColor: '#ef4444',
                        pointStyle: 'triangle',
                        rotation: 180,
                        showLine: false
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        labels: {
                            color: '#9ca3af',
                            font: { size: 10, family: 'var(--font-main)' },
                            boxWidth: 12
                        }
                    },
                    tooltip: {
                        mode: 'index',
                        intersect: false,
                        backgroundColor: 'rgba(3, 4, 10, 0.95)',
                        titleColor: '#9ca3af',
                        bodyColor: '#f3f4f6',
                        borderColor: 'rgba(255,255,255,0.08)',
                        borderWidth: 1
                    }
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { color: '#6b7280', font: { size: 9 } }
                    },
                    y: {
                        grid: { color: 'rgba(255,255,255,0.04)' },
                        ticks: { 
                            color: '#6b7280',
                            font: { size: 9 },
                            callback: function(value) {
                                return '₹' + value.toLocaleString('en-IN');
                            }
                        }
                    }
                }
            }
        });
    }

    // --- Interactive Strategy Payoff Calculator ---
    function calculateStrategyPayoff(settleSpot) {
        // Evaluate payoff for all legs at expiry relative to input strike values
        let totalPnL = 0;
        const lotSize = getLotSize(state.indexName, state.startDate);
        
        state.legs.forEach(leg => {
            // We resolve the strike price dynamically using a mock current spot of 22000/48000
            const indexBaseSpot = state.indexName === 'NIFTY' ? 22000 : 48000;
            const strikePrice = BacktestEngine.getStrikePrice(indexBaseSpot, state.indexName, leg.type, leg.strike);
            
            // Standard simulated entry premium based on a typical 15% IV environment
            const daysToExpiryFraction = 4 / 365.25; // 4 days remaining as standard
            const r = 0.07;
            const iv = (state.indexName === 'NIFTY' ? 13 : 17) / 100;
            const entryPremium = BacktestEngine.blackScholes(leg.type, indexBaseSpot, strikePrice, daysToExpiryFraction, r, iv);

            // Settle payoff at expiry
            let settlementVal = 0;
            if (leg.type === 'C') {
                settlementVal = Math.max(0, settleSpot - strikePrice);
            } else {
                settlementVal = Math.max(0, strikePrice - settleSpot);
            }

            let payoffPerUnit = 0;
            if (leg.position === 'BUY') {
                payoffPerUnit = settlementVal - entryPremium;
            } else {
                payoffPerUnit = entryPremium - settlementVal;
            }

            totalPnL += payoffPerUnit * leg.qty * lotSize;
        });

        return totalPnL;
    }

    // --- Draw Strategy Payoff Chart ---
    function drawPayoffChart(selectedSpotVal) {
        const ctx = document.getElementById('payoffChart').getContext('2d');
        
        // Setup price bounds (e.g. +/- 6% around center spot)
        const centerSpot = state.indexName === 'NIFTY' ? 22000 : 48000;
        const minPrice = centerSpot * 0.94;
        const maxPrice = centerSpot * 1.06;
        const step = state.indexName === 'NIFTY' ? 10 : 30;

        const xValues = [];
        const yValues = [];

        for (let p = minPrice; p <= maxPrice; p += step) {
            xValues.push(Math.round(p));
            yValues.push(calculateStrategyPayoff(p));
        }

        // Selected spot payoff value
        const currentSelectedPayoff = calculateStrategyPayoff(selectedSpotVal);

        if (payoffChartInstance) {
            payoffChartInstance.destroy();
        }

        payoffChartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: xValues,
                datasets: [
                    {
                        label: 'P&L at Expiry',
                        data: yValues,
                        borderColor: '#06b6d4',
                        borderWidth: 2,
                        pointRadius: 0,
                        pointHoverRadius: 4,
                        fill: {
                            target: 'origin',
                            above: 'rgba(16, 185, 129, 0.05)',
                            below: 'rgba(239, 68, 68, 0.05)'
                        },
                        tension: 0.1
                    },
                    {
                        label: 'Settle Cursor',
                        data: xValues.map(x => (Math.abs(x - selectedSpotVal) < step ? currentSelectedPayoff : null)),
                        borderColor: '#8b5cf6',
                        borderWidth: 0,
                        pointRadius: 6,
                        pointBackgroundColor: '#8b5cf6',
                        showLine: false
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: 'rgba(3, 4, 10, 0.95)',
                        callbacks: {
                            title: function(items) {
                                return `Spot Price: ₹${items[0].label}`;
                            },
                            label: function(item) {
                                return ` P&L: ₹${Math.round(item.raw).toLocaleString('en-IN')}`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { color: '#6b7280', font: { size: 9 } }
                    },
                    y: {
                        grid: { color: 'rgba(255,255,255,0.04)' },
                        ticks: { 
                            color: '#6b7280',
                            font: { size: 9 },
                            callback: function(value) {
                                return '₹' + (value >= 0 ? '+' : '') + (value / 1000).toFixed(1) + 'k';
                            }
                        }
                    }
                }
            }
        });
    }

    // Connect payoff spot slider input
    spotSlider.addEventListener('input', function(e) {
        const value = parseInt(e.target.value, 10);
        spotSliderVal.textContent = value.toLocaleString('en-IN');
        
        drawPayoffChart(value);
    });

    // --- Populate Trade Log Table ---
    function populateTradeLogTable(logs) {
        const tbody = document.querySelector('#tradeLogTable tbody');
        tbody.innerHTML = '';
        
        logs.forEach(log => {
            const tr = document.createElement('tr');
            
            // Generate HTML for legs inside this log row
            let legsHtml = `<div class="log-legs-container">`;
            log.legs.forEach(leg => {
                const posBadge = leg.position === 'BUY' ? 'buy' : 'sell';
                const typeBadge = leg.type === 'C' ? 'call' : 'put';
                const pnlClass = leg.pnl >= 0 ? 'pnl-pos' : 'pnl-neg';
                const statusBadge = leg.status === 'SL_HIT' ? 'sl-hit' : leg.status === 'TP_HIT' ? 'tp-hit' : 'time-exit';
                const statusText = leg.status === 'SL_HIT' ? 'SL' : leg.status === 'TP_HIT' ? 'Target' : 'Time';
                const typeLabel = leg.type === 'C' ? 'CE' : 'PE';
                
                legsHtml += `
                    <div class="log-leg-row">
                        <span class="badge ${posBadge}">${leg.position}</span>
                        <span class="badge ${typeBadge}">${leg.strike} ${typeLabel}</span>
                        <span style="color: var(--text-secondary);">Entry: ₹${leg.entryPremium}</span>
                        <span style="color: var(--text-muted);">&rarr;</span>
                        <span style="color: var(--text-secondary);">Exit: ₹${leg.exitPremium} (${statusText})</span>
                        <span class="${pnlClass}" style="font-weight:600; margin-left: auto;">₹${leg.pnl.toLocaleString('en-IN')}</span>
                    </div>
                `;
            });
            legsHtml += `</div>`;

            const totalPnLClass = log.totalPnL >= 0 ? 'pnl-pos' : 'pnl-neg';
            const formattedTotalPnL = (log.totalPnL >= 0 ? '+' : '') + '₹' + log.totalPnL.toLocaleString('en-IN');

            // Format date nicely
            const dateObj = new Date(log.date);
            const dateFormatted = dateObj.toLocaleDateString('en-US', { day: 'numeric', month: 'short', year: 'numeric' });

            // Add signal type badge if available
            let signalBadge = '';
            if (log.signalType && log.signalType !== 'Regular') {
                const isBullish = log.signalType.includes('Bullish');
                const badgeClass = isBullish ? 'buy' : 'sell';
                signalBadge = `<br><span class="badge ${badgeClass}" style="margin-top: 6px; font-size: 9px; line-height: 1;">${log.signalType}</span>`;
            }

            tr.innerHTML = `
                <td style="font-weight: 600; white-space: nowrap; vertical-align: top;">${dateFormatted}${signalBadge}</td>
                <td style="vertical-align: top;">₹${log.spotAtEntry.toLocaleString('en-IN')}</td>
                <td style="vertical-align: top;">₹${log.spotAtExit.toLocaleString('en-IN')}</td>
                <td>${legsHtml}</td>
                <td class="${totalPnLClass}" style="font-weight: 700; font-size: 14px; text-align: right; white-space: nowrap; vertical-align: top;">${formattedTotalPnL}</td>
            `;

            tbody.appendChild(tr);
        });
    }

    // --- Render Monthly Heatmap Grid ---
    function renderMonthlyHeatmap(dailyPnL) {
        const heatmapContainer = document.getElementById('heatmapContainer');
        heatmapContainer.innerHTML = '';

        // Process daily logs into monthly P&Ls
        const monthlyData = {}; // Format: { '2024': { '0': PnL, '1': PnL, ... } }
        
        dailyPnL.forEach(day => {
            const date = new Date(day.date);
            const year = date.getFullYear();
            const month = date.getMonth(); // 0 - 11
            
            if (!monthlyData[year]) {
                monthlyData[year] = {};
                for (let i = 0; i < 12; i++) {
                    monthlyData[year][i] = null; // Initialize months
                }
            }
            
            if (monthlyData[year][month] === null) {
                monthlyData[year][month] = 0;
            }
            monthlyData[year][month] += day.pnl;
        });

        const monthsShort = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

        Object.keys(monthlyData).sort().forEach(year => {
            const rowCard = document.createElement('div');
            rowCard.className = 'glass-panel';
            rowCard.style.padding = '12px 16px';
            rowCard.style.display = 'flex';
            rowCard.style.flexDirection = 'column';
            rowCard.style.gap = '8px';

            const header = document.createElement('div');
            header.style.fontFamily = 'var(--font-display)';
            header.style.fontSize = '14px';
            header.style.fontWeight = '700';
            header.style.color = 'var(--accent-theme)';
            header.textContent = `Year: ${year}`;
            rowCard.appendChild(header);

            const grid = document.createElement('div');
            grid.style.display = 'grid';
            grid.style.gridTemplateColumns = 'repeat(12, 1fr)';
            grid.style.gap = '8px';
            
            let yearTotal = 0;

            for (let m = 0; m < 12; m++) {
                const cellVal = monthlyData[year][m];
                const cell = document.createElement('div');
                cell.style.borderRadius = '6px';
                cell.style.padding = '8px 4px';
                cell.style.textAlign = 'center';
                cell.style.fontSize = '12px';
                cell.style.display = 'flex';
                cell.style.flexDirection = 'column';
                cell.style.justifyContent = 'center';
                
                const label = document.createElement('span');
                label.style.fontWeight = '700';
                label.style.color = 'var(--text-muted)';
                label.style.fontSize = '10px';
                label.textContent = monthsShort[m];
                cell.appendChild(label);

                const valSpan = document.createElement('span');
                valSpan.style.fontWeight = '600';
                valSpan.style.marginTop = '2px';

                if (cellVal === null) {
                    cell.style.background = 'rgba(255,255,255,0.02)';
                    cell.style.border = '1px solid rgba(255,255,255,0.03)';
                    valSpan.textContent = '-';
                    valSpan.style.color = 'var(--text-muted)';
                } else {
                    yearTotal += cellVal;
                    const isProfit = cellVal >= 0;
                    cell.style.background = isProfit ? 'var(--accent-green-glow)' : 'var(--accent-red-glow)';
                    cell.style.border = isProfit ? '1px solid rgba(16,185,129,0.1)' : '1px solid rgba(239,68,68,0.1)';
                    valSpan.textContent = (isProfit ? '+' : '') + Math.round(cellVal / 1000) + 'k';
                    valSpan.style.color = isProfit ? 'var(--accent-green)' : 'var(--accent-red)';
                }
                
                cell.appendChild(valSpan);
                grid.appendChild(cell);
            }

            rowCard.appendChild(grid);

            // Add Yearly summary banner
            const footer = document.createElement('div');
            footer.style.fontSize = '11px';
            footer.style.color = 'var(--text-secondary)';
            footer.style.marginTop = '4px';
            footer.style.textAlign = 'right';
            const yearPnLClass = yearTotal >= 0 ? 'pnl-pos' : 'pnl-neg';
            footer.innerHTML = `Annualized Performance: <strong class="${yearPnLClass}">₹${Math.round(yearTotal).toLocaleString('en-IN')}</strong>`;
            rowCard.appendChild(footer);

            heatmapContainer.appendChild(rowCard);
        });
    }

    // --- Tabs Event Switching ---
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            e.target.classList.add('active');

            const tab = e.target.dataset.tab;
            if (tab === 'tradeLog') {
                document.getElementById('tabContent_tradeLog').style.display = 'block';
                document.getElementById('tabContent_monthlyHeatmap').style.display = 'none';
            } else {
                document.getElementById('tabContent_tradeLog').style.display = 'none';
                document.getElementById('tabContent_monthlyHeatmap').style.display = 'block';
            }
        });
    });

    // --- Init Default State ---
    updateTheme('NIFTY');
    loadPreset('straddle');
});
