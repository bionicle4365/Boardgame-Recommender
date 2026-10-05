---
layout: null
---
// In-memory cache
    const collectionCache = {};
    const profileCache = {};

    // Chart references
    let chartPlaytime = null;
    let chartPlayers = null;
    let chartRatings = null;
    let chartMostPlayed = null;
    let chartTasteMechanics = null;
    let chartTasteCategories = null;

    let gamesData = []; // Store the fetched game data

    function showCollectionSkeletons(message) {
        const collectionDataDiv = document.getElementById('collection-data');
        const sidebarDiv = document.getElementById('filters-column');
        const controlsDiv = document.getElementById('browser-controls-bar');
        const paginationBar = document.getElementById('pagination-bar');

        // Keep sidebar and controls visible in loading state to prevent layout jumping
        if (sidebarDiv) {
            sidebarDiv.style.display = 'block';
            sidebarDiv.classList.add('filters-loading');
        }
        if (controlsDiv) {
            controlsDiv.style.display = 'flex';
            controlsDiv.style.opacity = '0.6';
            controlsDiv.style.pointerEvents = 'none';
        }
        if (paginationBar) paginationBar.style.display = 'none';

        if (currentViewMode === 'grid') {
            let skeletonCards = '';
            for (let i = 0; i < 8; i++) {
                skeletonCards += `
                    <div class="collection-card-skeleton">
                        <div class="skeleton-img-box"></div>
                        <div class="skeleton-card-body">
                            <div class="skeleton skeleton-text title" style="width: 75%; height: 18px; margin-bottom: 6px;"></div>
                            <div class="skeleton skeleton-text" style="width: 35%; height: 12px; margin-bottom: 8px;"></div>
                            <div class="skeleton-details-grid">
                                <div class="skeleton skeleton-text" style="height: 14px; margin: 0;"></div>
                                <div class="skeleton skeleton-text" style="height: 14px; margin: 0;"></div>
                                <div class="skeleton skeleton-text" style="height: 14px; margin: 0;"></div>
                                <div class="skeleton skeleton-text" style="height: 14px; margin: 0;"></div>
                            </div>
                        </div>
                    </div>
                `;
            }

            collectionDataDiv.innerHTML = `
                <div class="collection-status-card" style="margin: 0 0 20px 0;">
                    <div class="collection-spinner"></div>
                    <div class="collection-status-text">${message}</div>
                </div>
                <div class="game-cards-grid">
                    ${skeletonCards}
                </div>
            `;
        } else {
            let skeletonRows = '';
            for (let i = 0; i < 10; i++) {
                skeletonRows += `
                    <tr class="skeleton-row">
                        <td><div class="skeleton skeleton-text" style="width: 80%; height: 14px;"></div></td>
                        <td><div class="skeleton skeleton-text" style="width: 50%; height: 14px;"></div></td>
                        <td><div class="skeleton skeleton-text" style="width: 40%; height: 14px;"></div></td>
                        <td><div class="skeleton skeleton-text" style="width: 40%; height: 14px;"></div></td>
                        <td><div class="skeleton skeleton-text" style="width: 45%; height: 14px;"></div></td>
                        <td><div class="skeleton skeleton-text" style="width: 30%; height: 14px;"></div></td>
                        <td><div class="skeleton skeleton-text" style="width: 30%; height: 14px;"></div></td>
                        <td><div class="skeleton skeleton-text" style="width: 50%; height: 14px;"></div></td>
                        <td><div class="skeleton skeleton-text" style="width: 70%; height: 14px;"></div></td>
                        <td><div class="skeleton skeleton-text" style="width: 30%; height: 14px;"></div></td>
                        <td><div class="skeleton skeleton-text" style="width: 40%; height: 14px;"></div></td>
                        <td><div class="skeleton skeleton-text" style="width: 40%; height: 14px;"></div></td>
                    </tr>
                `;
            }

            collectionDataDiv.innerHTML = `
                <div class="collection-status-card" style="margin: 0 0 20px 0;">
                    <div class="collection-spinner"></div>
                    <div class="collection-status-text">${message}</div>
                </div>
                <table id="bgg-collection-table">
                    <thead>
                        <tr>
                            <th>Name</th>
                            <th>Year</th>
                            <th>BGG Rating</th>
                            <th>BGG User Avg</th>
                            <th>BGG Rank</th>
                            <th>Min Players</th>
                            <th>Max Players</th>
                            <th>Play Time</th>
                            <th>Status</th>
                            <th>Plays</th>
                            <th>My Rating</th>
                            <th>My Rank</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${skeletonRows}
                    </tbody>
                </table>
            `;
        }
        collectionDataDiv.classList.add('has-content');
    }
    let filteredGamesData = []; // Store the currently filtered data
    let currentSortColumn = null;
    let currentSortDirection = 'asc';
    let currentPage = 1;
    let pageSize = 25;
    let currentViewMode = 'grid';
    let currentLoadedCount = 25;
    let isInfiniteScrollLoading = false;

    // Facet Filter State Variables
    let activeStatuses = []; // Array of active status strings
    let activeMinPlayers = 1;
    let activeMaxPlayers = 8;
    let activeMinPlaytime = 0;
    let activeMaxPlaytime = 15;
    let activeMinRating = 1.0;
    let activeMaxRating = 10.0;

    // Chart.js Theme Defaults
    if (typeof Chart !== 'undefined') {
        Chart.defaults.font.family = "'Outfit', 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
        Chart.defaults.font.size = 12;
        Chart.defaults.color = "#475569"; // Slate 600
        Chart.defaults.plugins.tooltip.backgroundColor = "rgba(15, 23, 42, 0.9)";
        Chart.defaults.plugins.tooltip.titleFont = { family: "'Outfit', sans-serif", weight: 'bold' };
        Chart.defaults.plugins.tooltip.bodyFont = { family: "'Inter', sans-serif" };
        Chart.defaults.plugins.tooltip.padding = 10;
        Chart.defaults.plugins.tooltip.cornerRadius = 8;
    }

    function switchCollectionTab(tabName) {
        document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
        document.querySelectorAll('.tab-panel').forEach(panel => panel.classList.add('hidden'));

        const sidebarDiv = document.getElementById('filters-column');

        if (tabName === 'grid') {
            document.getElementById('tab-btn-grid').classList.add('active');
            document.getElementById('collection-panel-grid').classList.remove('hidden');
            if (gamesData.length > 0 && sidebarDiv) {
                sidebarDiv.style.display = 'block';
            }
        } else if (tabName === 'analytics') {
            document.getElementById('tab-btn-analytics').classList.add('active');
            document.getElementById('collection-panel-analytics').classList.remove('hidden');
            if (sidebarDiv) {
                sidebarDiv.style.display = 'none';
            }
            // Force charts resize/draw when tab is shown
            setTimeout(() => {
                if (chartPlaytime) chartPlaytime.resize();
                if (chartPlayers) chartPlayers.resize();
                if (chartRatings) chartRatings.resize();
                if (chartMostPlayed) chartMostPlayed.resize();
                if (chartTasteMechanics) chartTasteMechanics.resize();
                if (chartTasteCategories) chartTasteCategories.resize();
            }, 50);
        }
    }

    function generateFallbackProfile(games) {
        if (!games || games.length === 0) {
            return {
                complexity_weights: {
                    "Light": 0.0,
                    "Medium-Light": 1.0,
                    "Medium-Heavy": 0.0,
                    "Heavy": 0.0
                },
                mech_weights: {},
                cat_weights: {},
                designer_weights: {},
                publisher_weights: {},
                generated_at: new Date().toISOString(),
                is_fallback: true
            };
        }

        let complexityCount = 0;
        let complexity_weights = {
            "Light": 0.0,
            "Medium-Light": 0.0,
            "Medium-Heavy": 0.0,
            "Heavy": 0.0
        };
        let complexityCounts = {
            "Light": 0,
            "Medium-Light": 0,
            "Medium-Heavy": 0,
            "Heavy": 0
        };
        
        let soloCount = 0;
        let highPlayerCount = 0;
        let shortTimeCount = 0;
        let mediumTimeCount = 0;
        let longTimeCount = 0;
        let epicTimeCount = 0;
        let highRatingCount = 0;
        let mediumRatingCount = 0;

        games.forEach(g => {
            let estComp = 2.2;
            const time = parseInt(g.playingTime);
            if (!isNaN(time) && time > 0) {
                if (time <= 30) estComp = 1.4;
                else if (time <= 60) estComp = 2.2;
                else if (time <= 120) estComp = 2.9;
                else estComp = 3.8;
            }

            const ratingVal = parseFloat(g.userRating !== 'N/A' ? g.userRating : g.bggRating);
            const r = (!isNaN(ratingVal) && ratingVal > 0) ? ratingVal : 7.0;
            const weight = Math.max(1.0, r - 5.0);

            let bucket = "Medium-Light";
            if (estComp < 2.0) {
                bucket = "Light";
            } else if (estComp <= 2.8) {
                bucket = "Medium-Light";
            } else if (estComp <= 3.5) {
                bucket = "Medium-Heavy";
            } else {
                bucket = "Heavy";
            }
            complexity_weights[bucket] += weight;
            complexityCounts[bucket]++;
            complexityCount++;

            if (parseInt(g.minPlayers) === 1) soloCount++;
            if (parseInt(g.maxPlayers) >= 5) highPlayerCount++;

            if (!isNaN(time) && time > 0) {
                if (time <= 30) shortTimeCount++;
                else if (time <= 60) mediumTimeCount++;
                else if (time <= 120) longTimeCount++;
                else epicTimeCount++;
            }

            const rating = parseFloat(g.userRating !== 'N/A' ? g.userRating : g.bggRating);
            if (!isNaN(rating)) {
                if (rating >= 8.0) highRatingCount++;
                else if (rating >= 6.5) mediumRatingCount++;
            }
        });

        if (complexityCount === 0) {
            complexity_weights["Medium-Light"] = 1.0;
        } else {
            for (let bucket in complexity_weights) {
                if (complexityCounts[bucket] > 0) {
                    complexity_weights[bucket] = parseFloat((complexity_weights[bucket] / complexityCounts[bucket]).toFixed(2));
                } else {
                    complexity_weights[bucket] = 0.0;
                }
            }
        }

        const n = games.length;
        const scaleValue = (val) => parseFloat(((val / n) * 5.0).toFixed(1));

        const mech_weights = {
            "Solo Friendly": scaleValue(soloCount),
            "High Player Counts": scaleValue(highPlayerCount),
            "Quick Play / Filler": scaleValue(shortTimeCount),
            "Medium Weight": scaleValue(mediumTimeCount),
            "Long Playtime": scaleValue(longTimeCount),
            "Epic Playtime": scaleValue(epicTimeCount)
        };

        const cat_weights = {
            "Highly Rated": scaleValue(highRatingCount),
            "Well Received": scaleValue(mediumRatingCount),
            "Casual / Light": scaleValue(shortTimeCount + soloCount),
            "Heavy Strategy": scaleValue(epicTimeCount + longTimeCount)
        };

        return {
            complexity_weights: complexity_weights,
            mech_weights: mech_weights,
            cat_weights: cat_weights,
            designer_weights: {},
            publisher_weights: {},
            generated_at: new Date().toISOString(),
            is_fallback: true
        };
    }

    async function fetchAndRenderTasteProfile(lowerUsername) {
        const statusDiv = document.getElementById('taste-profile-status');
        const panelDiv = document.getElementById('taste-profile-panel');
        
        statusDiv.style.display = 'block';
        panelDiv.style.display = 'none';
        statusDiv.innerHTML = '<div class="collection-spinner" style="margin: 0 auto 10px auto;"></div><div>Loading user taste profile...</div>';

        let profile = profileCache[lowerUsername];
        let isFallback = false;

        if (!profile) {
            const apiBaseUrl = "{{ site.api_url }}";
            const profileUrl = `${apiBaseUrl}/profile?username=${lowerUsername}`;
            try {
                const response = await fetch(profileUrl);
                if (response.ok) {
                    profile = await response.json();
                    profileCache[lowerUsername] = profile;
                } else if (response.status === 404) {
                    console.warn(`Profile 404 for ${lowerUsername}, generating fallback client-side.`);
                    profile = generateFallbackProfile(gamesData);
                    profileCache[lowerUsername] = profile;
                    isFallback = true;
                } else {
                    throw new Error("HTTP " + response.status);
                }
            } catch (e) {
                console.error("Failed fetching user taste profile:", e);
                profile = generateFallbackProfile(gamesData);
                profileCache[lowerUsername] = profile;
                isFallback = true;
            }
        } else {
            isFallback = profile.is_fallback || false;
        }

        statusDiv.style.display = 'none';
        panelDiv.style.display = 'block';

        const sectionTitle = panelDiv.querySelector('h2');
        if (isFallback) {
            sectionTitle.textContent = "Taste Profile (Estimated from Collection)";
            panelDiv.querySelector('p').innerHTML = `⚠️ Profile not found on backend. These weights are estimated client-side from the user's BGG collection XML stats.`;
        } else {
            sectionTitle.textContent = "User Taste Profile";
            panelDiv.querySelector('p').textContent = `Visualizing category and mechanic weights compiled from user ratings and BGG statistics. (Pre-computed / Scraped)`;
        }

        renderTasteProfileCharts(profile);
    }

    function renderTasteProfileCharts(profile) {
        const mechData = profile.mech_weights || {};
        const sortedMechs = Object.entries(mechData)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 8);
        
        const labelsMech = sortedMechs.map(item => item[0]);
        const dataMech = sortedMechs.map(item => item[1]);

        if (chartTasteMechanics) chartTasteMechanics.destroy();
        
        if (labelsMech.length > 0) {
            const ctxMech = document.getElementById('chart-taste-mechanics').getContext('2d');
            chartTasteMechanics = new Chart(ctxMech, {
                type: 'radar',
                data: {
                    labels: labelsMech,
                    datasets: [{
                        label: 'Affinity Weight',
                        data: dataMech,
                        backgroundColor: 'rgba(16, 185, 129, 0.2)',
                        borderColor: 'rgb(16, 185, 129)',
                        pointBackgroundColor: 'rgb(16, 185, 129)',
                        pointBorderColor: '#fff',
                        pointHoverBackgroundColor: '#fff',
                        pointHoverBorderColor: 'rgb(16, 185, 129)',
                        borderWidth: 2
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        r: {
                            angleLines: { display: true, color: 'rgba(0, 0, 0, 0.05)' },
                            grid: { color: 'rgba(0, 0, 0, 0.05)' },
                            suggestedMin: 0,
                            ticks: { backdropColor: 'transparent', color: '#64748b' }
                        }
                    }
                }
            });
        }

        const catData = profile.cat_weights || {};
        const sortedCats = Object.entries(catData)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 8);
        
        const labelsCat = sortedCats.map(item => item[0]);
        const dataCat = sortedCats.map(item => item[1]);

        if (chartTasteCategories) chartTasteCategories.destroy();
        
        if (labelsCat.length > 0) {
            const ctxCat = document.getElementById('chart-taste-categories').getContext('2d');
            chartTasteCategories = new Chart(ctxCat, {
                type: 'bar',
                data: {
                    labels: labelsCat,
                    datasets: [{
                        label: 'Affinity Weight',
                        data: dataCat,
                        backgroundColor: 'rgba(59, 130, 246, 0.7)',
                        borderColor: 'rgb(59, 130, 246)',
                        borderWidth: 1.5,
                        borderRadius: 6
                    }]
                },
                options: {
                    indexAxis: 'y',
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { beginAtZero: true, grid: { color: 'rgba(0, 0, 0, 0.05)' } },
                        y: { grid: { display: false } }
                    }
                }
            });
        }
    }

    function updateAnalytics() {
        const totalGames = filteredGamesData.length;
        document.getElementById('card-total-games').textContent = totalGames;

        const ownedGamesCount = filteredGamesData.filter(g => g.collectionStatus && g.collectionStatus.includes('Own')).length;
        document.getElementById('card-owned-games').textContent = `${ownedGamesCount} / ${totalGames}`;

        const totalPlays = filteredGamesData.reduce((sum, g) => sum + g.numPlays, 0);
        document.getElementById('card-total-plays').textContent = totalPlays;

        const sortedByPlays = [...filteredGamesData].sort((a, b) => b.numPlays - a.numPlays);
        if (sortedByPlays.length > 0 && sortedByPlays[0].numPlays > 0) {
            document.getElementById('card-most-played').textContent = `${sortedByPlays[0].name} (${sortedByPlays[0].numPlays})`;
            document.getElementById('card-most-played').title = `${sortedByPlays[0].name} (${sortedByPlays[0].numPlays} plays)`;
        } else {
            document.getElementById('card-most-played').textContent = '-';
            document.getElementById('card-most-played').title = '';
        }

        let shortCount = 0, medCount = 0, longCount = 0, epicCount = 0;
        filteredGamesData.forEach(g => {
            const time = g.playingTime;
            if (time !== 'N/A' && time > 0) {
                if (time < 30) shortCount++;
                else if (time <= 60) medCount++;
                else if (time <= 120) longCount++;
                else epicCount++;
            }
        });

        const playtimeData = [shortCount, medCount, longCount, epicCount];
        if (chartPlaytime) chartPlaytime.destroy();
        
        const ctxPlaytime = document.getElementById('chart-playtime').getContext('2d');
        chartPlaytime = new Chart(ctxPlaytime, {
            type: 'doughnut',
            data: {
                labels: ['Short (<30m)', 'Medium (30-60m)', 'Long (60-120m)', 'Epic (>120m)'],
                datasets: [{
                    data: playtimeData,
                    backgroundColor: [
                        'rgba(16, 185, 129, 0.7)',
                        'rgba(59, 130, 246, 0.7)',
                        'rgba(245, 158, 11, 0.7)',
                        'rgba(236, 72, 153, 0.7)'
                    ],
                    borderColor: '#ffffff',
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'bottom' }
                }
            }
        });

        let solo = 0, twoP = 0, threeFourP = 0, fivePlus = 0;
        filteredGamesData.forEach(g => {
            const min = g.minPlayers;
            const max = g.maxPlayers;
            if (min !== 'N/A' && max !== 'N/A') {
                if (min <= 1 && max >= 1) solo++;
                if (min <= 2 && max >= 2) twoP++;
                if (min <= 4 && max >= 3) threeFourP++;
                if (max >= 5) fivePlus++;
            }
        });

        if (chartPlayers) chartPlayers.destroy();
        const ctxPlayers = document.getElementById('chart-players').getContext('2d');
        chartPlayers = new Chart(ctxPlayers, {
            type: 'bar',
            data: {
                labels: ['Solo', '2-Player', '3-4 Players', '5+ Players'],
                datasets: [{
                    label: 'Games Supported',
                    data: [solo, twoP, threeFourP, fivePlus],
                    backgroundColor: 'rgba(59, 130, 246, 0.7)',
                    borderColor: 'rgb(59, 130, 246)',
                    borderWidth: 1.5,
                    borderRadius: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    y: { beginAtZero: true, grid: { color: 'rgba(0, 0, 0, 0.05)' } },
                    x: { grid: { display: false } }
                }
            }
        });

        let rUnder6 = 0, r6to7 = 0, r7to8 = 0, r8to9 = 0, r9Plus = 0;
        let rNotRated = 0;
        filteredGamesData.forEach(g => {
            const rating = g.userRating;
            if (rating === 'N/A' || rating === null || rating === undefined) {
                rNotRated++;
            } else {
                const r = parseFloat(rating);
                if (r < 6.0) rUnder6++;
                else if (r < 7.0) r6to7++;
                else if (r < 8.0) r7to8++;
                else if (r < 9.0) r8to9++;
                else r9Plus++;
            }
        });

        if (chartRatings) chartRatings.destroy();
        const ctxRatings = document.getElementById('chart-ratings').getContext('2d');
        const ratingsLabels = ['<6.0', '6.0-6.9', '7.0-7.9', '8.0-8.9', '9.0+'];
        if (rNotRated > 0) ratingsLabels.push('Not Rated');
        const ratingsData = [rUnder6, r6to7, r7to8, r8to9, r9Plus];
        if (rNotRated > 0) ratingsData.push(rNotRated);
        chartRatings = new Chart(ctxRatings, {
            type: 'bar',
            data: {
                labels: ratingsLabels,
                datasets: [{
                    label: 'Games',
                    data: ratingsData,
                    backgroundColor: [
                        'rgba(239, 68, 68, 0.7)',
                        'rgba(245, 158, 11, 0.7)',
                        'rgba(59, 130, 246, 0.7)',
                        'rgba(16, 185, 129, 0.7)',
                        'rgba(139, 92, 246, 0.7)',
                        'rgba(148, 163, 184, 0.5)'
                    ],
                    borderColor: [
                        'rgb(239, 68, 68)',
                        'rgb(245, 158, 11)',
                        'rgb(59, 130, 246)',
                        'rgb(16, 185, 129)',
                        'rgb(139, 92, 246)',
                        'rgb(148, 163, 184)'
                    ],
                    borderWidth: 1.5,
                    borderRadius: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    y: { beginAtZero: true, grid: { color: 'rgba(0, 0, 0, 0.05)' }, ticks: { precision: 0 } },
                    x: { grid: { display: false } }
                }
            }
        });

        const topPlayed = [...filteredGamesData]
            .filter(g => g.numPlays > 0)
            .sort((a, b) => b.numPlays - a.numPlays)
            .slice(0, 6);

        const labelsPlayed = topPlayed.map(g => g.name);
        const dataPlayed = topPlayed.map(g => g.numPlays);

        if (chartMostPlayed) chartMostPlayed.destroy();
        const ctxMostPlayed = document.getElementById('chart-most-played-list').getContext('2d');
        chartMostPlayed = new Chart(ctxMostPlayed, {
            type: 'bar',
            data: {
                labels: labelsPlayed.length > 0 ? labelsPlayed : ['No games played'],
                datasets: [{
                    label: 'Plays Count',
                    data: dataPlayed.length > 0 ? dataPlayed : [0],
                    backgroundColor: 'rgba(245, 158, 11, 0.7)',
                    borderColor: 'rgb(245, 158, 11)',
                    borderWidth: 1.5,
                    borderRadius: 6
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { beginAtZero: true, grid: { color: 'rgba(0, 0, 0, 0.05)' } },
                    y: { grid: { display: false } }
                }
            }
        });
    }

    function processCollectionXml(xmlDoc, lowerUsername) {
        gamesData = [];
        const items = xmlDoc.getElementsByTagName('item');
        for (let i = 0; i < items.length; i++) {
            const name = items[i].getElementsByTagName('name')[0]?.textContent || 'N/A';
            const yearPublished = items[i].getElementsByTagName('yearpublished')[0]?.textContent || 'N/A';

            const status = items[i].getElementsByTagName('status')[0];
            let collectionStatus = '';
            if (status) {
                if (status.getAttribute('own') === '1') collectionStatus += 'Own ';
                if (status.getAttribute('preordered') === '1') collectionStatus += 'Preordered ';
                if (status.getAttribute('wanttoplay') === '1') collectionStatus += 'Want to Play ';
                if (status.getAttribute('wanttobuy') === '1') collectionStatus += 'Want to Buy ';
                if (status.getAttribute('wishlist') === '1') collectionStatus += 'Wishlist ';
                collectionStatus = collectionStatus.trim() || 'N/A';
            }

            const numPlays = items[i].getElementsByTagName('numplays')[0]?.textContent || '0';

            const stats = items[i].getElementsByTagName('stats')[0];
            const minPlayers = stats?.getAttribute('minplayers') || 'N/A';
            const maxPlayers = stats?.getAttribute('maxplayers') || 'N/A';
            const playingTime = stats?.getAttribute('playingtime') || 'N/A';

            const userRating = stats?.getElementsByTagName('rating')[0]?.getAttribute('value') || 'N/A';
            const userAverage = stats?.getElementsByTagName('average')[0]?.getAttribute('value') || 'N/A';
            const bggAverage = stats?.getElementsByTagName('bayesaverage')[0]?.getAttribute('value') || 'N/A';

            let bggRank = 'N/A';
            const ranks = stats?.getElementsByTagName('ranks')[0];
            if (ranks) {
                const boardgameRank = Array.from(ranks.getElementsByTagName('rank')).find(r => r.getAttribute('name') === 'boardgame');
                bggRank = boardgameRank?.getAttribute('value') || 'N/A';
            }

            const item_id = items[i].getAttribute('objectid') || 'N/A';

            let thumbnail = items[i].getElementsByTagName('thumbnail')[0]?.textContent || '';
            if (thumbnail.startsWith('//')) {
                thumbnail = 'https:' + thumbnail;
            }
            let image = items[i].getElementsByTagName('image')[0]?.textContent || '';
            if (image.startsWith('//')) {
                image = 'https:' + image;
            }

            gamesData.push({
                item_id: item_id,
                name: name,
                yearPublished: yearPublished === 'N/A' ? 'N/A' : parseInt(yearPublished),
                bggRating: bggAverage === 'N/A' ? 'N/A' : parseFloat(bggAverage),
                bggUserRating: userAverage === 'N/A' ? 'N/A' : parseFloat(userAverage),
                bggRank: bggRank === 'N/A' ? Infinity : parseInt(bggRank),
                minPlayers: minPlayers === 'N/A' ? 'N/A' : parseInt(minPlayers),
                maxPlayers: maxPlayers === 'N/A' ? 'N/A' : parseInt(maxPlayers),
                playingTime: playingTime === 'N/A' ? 'N/A' : parseInt(playingTime),
                collectionStatus: collectionStatus,
                numPlays: parseInt(numPlays),
                userRating: userRating === 'N/A' ? 'N/A' : parseFloat(userRating),
                thumbnail: thumbnail,
                image: image,
            });
        }
        calculateUserRanks();
        currentPage = 1;
        currentViewMode = 'grid'; // Default/reset to Card Grid view when collection loads
        updateViewToggleButtons();
        filteredGamesData = [...gamesData];
        
        // Show tabs navigation and layout wrap container, hide empty state
        const tabsNav = document.getElementById('collection-tabs-nav');
        if (tabsNav) tabsNav.style.display = 'flex';
        document.getElementById('collection-layout-wrap').style.display = 'flex';
        document.getElementById('collection-empty-state').style.display = 'none';
        switchCollectionTab('grid');
        
        renderTable();
        updateAnalytics();
        fetchAndRenderTasteProfile(lowerUsername);
    }

    const headers = [
        { name: 'Name', key: 'name', type: 'string' },
        { name: 'Year', key: 'yearPublished', type: 'number' },
        { name: 'BGG Rating', key: 'bggRating', type: 'number' },
        { name: 'BGG User Avg', key: 'bggUserRating', type: 'number' },
        { name: 'BGG Rank', key: 'bggRank', type: 'number' },
        { name: 'Min Players', key: 'minPlayers', type: 'number' },
        { name: 'Max Players', key: 'maxPlayers', type: 'number' },
        { name: 'Play Time', key: 'playingTime', type: 'number' },
        { name: 'Status', key: 'collectionStatus', type: 'string' },
        { name: 'Plays', key: 'numPlays', type: 'number' },
        { name: 'My Rating', key: 'userRating', type: 'number' },
        { name: 'My Rank', key: 'userRank', type: 'number' }
    ];

    // Faceted filtering helper functions (previously query builder helper functions)

    function calculateUserRanks() {
        // Filter out games with N/A user ratings for ranking purposes
        const rankedGames = gamesData.filter(game => game.userRating !== 'N/A');

        // Sort games by userRating in descending order
        rankedGames.sort((a, b) => parseFloat(b.userRating) - parseFloat(a.userRating));

        let currentRank = 1;
        for (let i = 0; i < rankedGames.length; i++) {
            if (i > 0 && parseFloat(rankedGames[i].userRating) < parseFloat(rankedGames[i - 1].userRating)) {
                currentRank = i + 1;
            }
            rankedGames[i].userRank = currentRank;
        }

        // Assign N/A to games that were not ranked
        gamesData.forEach(game => {
            if (game.userRating === 'N/A') {
                game.userRank = 'N/A';
            }
        });
    }

    function renderPagination(totalGames) {
        const paginationBar = document.getElementById('pagination-bar');
        const infoText = document.getElementById('pagination-info-text');
        const pageList = document.getElementById('pagination-page-list');

        if (totalGames === 0) {
            paginationBar.style.display = 'none';
            return;
        }

        paginationBar.style.display = 'flex';
        const limit = pageSize === 'all' ? totalGames : parseInt(pageSize);
        const totalPages = Math.ceil(totalGames / limit) || 1;

        if (currentPage > totalPages) currentPage = totalPages;
        const startOffset = totalGames === 0 ? 0 : (currentPage - 1) * limit + 1;
        const endOffset = Math.min(startOffset + limit - 1, totalGames);

        infoText.textContent = `Showing ${startOffset}-${endOffset} of ${totalGames} games`;

        let buttonsHtml = '';
        
        // Prev button
        buttonsHtml += `<button class="pagination-btn ${currentPage === 1 ? 'disabled' : ''}" id="page-prev" data-page="${currentPage - 1}">&larr; Prev</button>`;

        // Numbered buttons - full numbered list
        for (let i = 1; i <= totalPages; i++) {
            buttonsHtml += `<button class="pagination-btn ${currentPage === i ? 'active' : ''}" data-page="${i}">${i}</button>`;
        }

        // Next button
        buttonsHtml += `<button class="pagination-btn ${currentPage === totalPages ? 'disabled' : ''}" id="page-next" data-page="${currentPage + 1}">Next &rarr;</button>`;

        pageList.innerHTML = buttonsHtml;

        // Add event listeners to page buttons
        pageList.querySelectorAll('.pagination-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                if (this.classList.contains('disabled') || this.classList.contains('active')) return;
                currentPage = parseInt(this.dataset.page);
                renderTable();
            });
        });
    }

    function renderTable() {
        const collectionDataDiv = document.getElementById('collection-data');
        const sidebarDiv = document.getElementById('filters-column');
        const controlsDiv = document.getElementById('browser-controls-bar');

        if (gamesData.length === 0) {
            collectionDataDiv.innerHTML = '';
            collectionDataDiv.classList.remove('has-content');
            if (sidebarDiv) sidebarDiv.style.display = 'none';
            controlsDiv.style.display = 'none';
            renderPagination(0);
            return;
        }

        if (sidebarDiv) {
            sidebarDiv.classList.remove('filters-loading');
        }
        if (controlsDiv) {
            controlsDiv.style.display = 'flex';
            controlsDiv.style.opacity = '1';
            controlsDiv.style.pointerEvents = 'auto';
        }
        
        // Only show sidebar filters on Grid View tab
        const activeTab = document.querySelector('.tab-btn.active');
        if (activeTab && activeTab.id === 'tab-btn-grid') {
            if (sidebarDiv) sidebarDiv.style.display = 'block';
        } else {
            if (sidebarDiv) sidebarDiv.style.display = 'none';
        }

        if (filteredGamesData.length === 0) {
            collectionDataDiv.innerHTML = '<div class="collection-message">No games match the current filters.</div>';
            collectionDataDiv.classList.add('has-content');
            const loader = document.getElementById('infinite-scroll-loader');
            if (loader) loader.style.display = 'none';
            renderPagination(0);
            return;
        }

        const totalGames = filteredGamesData.length;

        if (currentViewMode === 'grid') {
            // Slicing for infinite scroll
            const gridGames = filteredGamesData.slice(0, currentLoadedCount);
            const showLoader = currentLoadedCount < totalGames;
            renderCardGrid(gridGames, collectionDataDiv, showLoader);
            
            // Hide page size select and pagination bar
            const pageSizeControls = document.getElementById('page-size-controls');
            if (pageSizeControls) pageSizeControls.style.display = 'none';
            document.getElementById('pagination-bar').style.display = 'none';
        } else {
            // Slicing for pagination
            const limit = pageSize === 'all' ? totalGames : parseInt(pageSize);
            const totalPages = Math.ceil(totalGames / limit) || 1;
            if (currentPage > totalPages) currentPage = totalPages;
            const startOffset = (currentPage - 1) * limit;
            const endOffset = Math.min(startOffset + limit, totalGames);
            const listGames = filteredGamesData.slice(startOffset, endOffset);

            renderTableList(listGames, collectionDataDiv);
            
            // Show page size select controls
            const pageSizeControls = document.getElementById('page-size-controls');
            if (pageSizeControls) pageSizeControls.style.display = 'flex';

            // Render numbered pagination list (which shows/hides the pagination-bar itself)
            renderPagination(totalGames);
        }
    }

    function renderTableList(pagedGames, container) {
        let tableHtml = '<table id="bgg-collection-table"><thead><tr>';

        headers.forEach(header => {
            let sortIndicator = '';
            if (currentSortColumn === header.key) {
                sortIndicator = currentSortDirection === 'asc' ? ' &#9650;' : ' &#9660;'; // Up or Down arrow
            }
            tableHtml += `<th data-sort-by="${header.key}" data-sort-type="${header.type}">${header.name}${sortIndicator}</th>`;
        });
        tableHtml += '</tr></thead><tbody>';

        pagedGames.forEach(game => {
            tableHtml += `<tr>
                <td><a href="https://boardgamegeek.com/boardgame/${game.item_id}" target="_blank">${game.name}</a></td>
                <td>${game.yearPublished}</td>
                <td>${game.bggRating !== 'N/A' ? parseFloat(game.bggRating).toFixed(2) : 'N/A'}</td>
                <td>${game.bggUserRating !== 'N/A' ? parseFloat(game.bggUserRating).toFixed(2) : 'N/A'}</td>
                <td>${isNaN(game.bggRank) || game.bggRank === Infinity ? 'N/A' : game.bggRank}</td>
                <td>${game.minPlayers}</td>
                <td>${game.maxPlayers}</td>
                <td>${game.playingTime !== 'N/A' ? game.playingTime + ' min' : 'N/A'}</td>
                <td>${game.collectionStatus}</td>
                <td>${game.numPlays}</td>
                <td>${game.userRating !== 'N/A' ? parseFloat(game.userRating).toFixed(2) : 'N/A'}</td>
                <td>${game.userRank}</td>
            </tr>`;
        });
        tableHtml += '</tbody></table>';
        container.innerHTML = tableHtml;
        container.classList.add('has-content');

        // Add event listeners to new headers
        document.querySelectorAll('#bgg-collection-table th').forEach(header => {
            header.addEventListener('click', function () {
                const sortBy = this.dataset.sortBy;
                const sortType = this.dataset.sortType;
                sortTable(sortBy, sortType);
            });
        });
    }

    function renderCardGrid(pagedGames, container, showLoader) {
        let gridHtml = '<div class="collection-grid">';

        pagedGames.forEach(game => {
            // Determine BGG rating class
            let ratingClass = 'rating-none';
            let ratingText = 'N/A';
            if (game.bggRating !== 'N/A') {
                ratingText = parseFloat(game.bggRating).toFixed(1);
                const r = parseFloat(game.bggRating);
                if (r >= 8.0) ratingClass = 'rating-excellent';
                else if (r >= 7.0) ratingClass = 'rating-good';
                else if (r >= 6.0) ratingClass = 'rating-fine';
                else if (r >= 5.0) ratingClass = 'rating-average';
                else ratingClass = 'rating-poor';
            }

            // Determine status badge
            let primaryStatus = '';
            let statusClass = 'status-other';
            const statusStr = game.collectionStatus || '';
            
            if (statusStr.includes('Own')) {
                primaryStatus = 'Own';
                statusClass = 'status-own';
            } else if (statusStr.includes('Preordered')) {
                primaryStatus = 'Preordered';
                statusClass = 'status-preorder';
            } else if (statusStr.includes('Want to Play')) {
                primaryStatus = 'Want to Play';
                statusClass = 'status-wantplay';
            } else if (statusStr.includes('Want to Buy')) {
                primaryStatus = 'Want to Buy';
                statusClass = 'status-wantbuy';
            } else if (statusStr.includes('Wishlist')) {
                primaryStatus = 'Wishlist';
                statusClass = 'status-wishlist';
            } else if (statusStr !== 'N/A' && statusStr !== '') {
                primaryStatus = statusStr.split(' ')[0];
                statusClass = 'status-other';
            }

            // Players range
            let playersText = 'N/A';
            if (game.minPlayers !== 'N/A' && game.maxPlayers !== 'N/A') {
                if (game.minPlayers === game.maxPlayers) {
                    playersText = `${game.minPlayers} players`;
                } else {
                    playersText = `${game.minPlayers}-${game.maxPlayers} players`;
                }
            }

            // Playtime
            let playtimeText = 'N/A';
            if (game.playingTime !== 'N/A') {
                playtimeText = `${game.playingTime} Min`;
            }

            // Rank
            let rankText = 'N/A';
            if (game.bggRank && game.bggRank !== Infinity) {
                rankText = `#${game.bggRank}`;
            }

            // User rating & User rank
            let userRatingHtml = '';
            if (game.userRating !== 'N/A') {
                userRatingHtml = `<span class="game-card-user-rating" title="My Rating: ${game.userRating}">⭐ ${parseFloat(game.userRating).toFixed(1)}</span>`;
            } else {
                userRatingHtml = `<span class="game-card-user-rating" style="color: var(--text-muted);" title="Not Rated by me">⭐ -</span>`;
            }

            let playsHtml = '';
            if (game.numPlays > 0) {
                playsHtml = `<span class="game-card-plays">${game.numPlays} ${game.numPlays === 1 ? 'play' : 'plays'}</span>`;
            }

            let imageHtml = '';
            if (game.thumbnail) {
                imageHtml = `<img src="${game.thumbnail}" class="game-card-img" alt="${game.name}" loading="lazy">`;
            } else {
                imageHtml = `<div class="game-card-placeholder-img">${game.name.substring(0, 2).toUpperCase()}</div>`;
            }

            let statusBadgeHtml = '';
            if (primaryStatus) {
                statusBadgeHtml = `<div class="game-card-status-badge ${statusClass}">${primaryStatus}</div>`;
            }

            gridHtml += `
            <div class="game-card">
                <a href="https://boardgamegeek.com/boardgame/${game.item_id}" target="_blank" style="text-decoration: none; color: inherit; display: flex; flex-direction: column; height: 100%;">
                    <div class="game-card-img-container">
                        ${statusBadgeHtml}
                        <div class="game-card-bgg-rating-badge ${ratingClass}" title="BGG Rating">${ratingText}</div>
                        ${imageHtml}
                    </div>
                    <div class="game-card-body">
                        <div class="game-card-title-row">
                            <h3 class="game-card-title">${game.name}</h3>
                            <p class="game-card-year">${game.yearPublished !== 'N/A' ? game.yearPublished : ''}</p>
                        </div>
                        <div class="game-card-divider"></div>
                        <div class="game-card-details-grid">
                            <div class="game-card-detail-item" title="Player Count">
                                <span class="game-card-detail-icon">👥</span>
                                <span class="game-card-detail-text">${playersText}</span>
                            </div>
                            <div class="game-card-detail-item" title="Play Time">
                                <span class="game-card-detail-icon">⏱️</span>
                                <span class="game-card-detail-text">${playtimeText}</span>
                            </div>
                            <div class="game-card-detail-item" title="BGG Rank">
                                <span class="game-card-detail-icon">🏆</span>
                                <span class="game-card-detail-text">${rankText}</span>
                            </div>
                            <div class="game-card-detail-item" title="My Rank">
                                <span class="game-card-detail-icon">🏅</span>
                                <span class="game-card-detail-text">${game.userRank !== 'N/A' ? 'Rank #' + game.userRank : 'Unranked'}</span>
                            </div>
                        </div>
                        <div class="game-card-footer">
                            ${userRatingHtml}
                            ${playsHtml}
                        </div>
                    </div>
                </a>
            </div>`;
        });

        gridHtml += '</div>';

        if (showLoader) {
            gridHtml += `
            <div id="infinite-scroll-loader" class="infinite-scroll-loading" style="display: flex;">
                <div class="collection-spinner" style="width: 22px; height: 22px; border-width: 2.5px; margin: 0;"></div>
                <span>Loading more games...</span>
            </div>`;
        }

        container.innerHTML = gridHtml;
        container.classList.add('has-content');
    }

    function sortTable(columnKey, columnType) {
        if (currentSortColumn === columnKey) {
            currentSortDirection = currentSortDirection === 'asc' ? 'desc' : 'asc';
        } else {
            currentSortColumn = columnKey;
            currentSortDirection = 'asc';
        }
        currentPage = 1; // Reset to page 1 on sorting change
        filterAndRender();
    }

    function filterAndRender() {
        currentLoadedCount = 25; // Reset infinite scroll batch count
        filteredGamesData = [...gamesData]; // Start with all data
        
        // Apply global search filter
        const searchInput = document.getElementById('game-search-input');
        const query = searchInput ? searchInput.value.trim().toLowerCase() : '';
        if (query) {
            filteredGamesData = filteredGamesData.filter(game => 
                game.name.toLowerCase().includes(query)
            );
        }

        // Apply Faceted Filters
        
        // 1. Status Filter (Multi-select OR logic)
        if (activeStatuses.length > 0) {
            filteredGamesData = filteredGamesData.filter(game => {
                const gameStatus = game.collectionStatus || '';
                return activeStatuses.some(status => gameStatus.includes(status));
            });
        }

        // 2. Player Count Range Filter
        if (activeMinPlayers !== 1 || activeMaxPlayers !== 8) {
            filteredGamesData = filteredGamesData.filter(game => {
                const min = parseInt(game.minPlayers);
                const max = parseInt(game.maxPlayers);
                if (isNaN(min) || isNaN(max)) return false;
                if (activeMaxPlayers === 8) {
                    return max >= activeMinPlayers;
                } else {
                    return min <= activeMaxPlayers && max >= activeMinPlayers;
                }
            });
        }

        // 3. Play Time Range Filter
        if (activeMinPlaytime !== 0 || activeMaxPlaytime !== 15) {
            const playtimeValues = [15, 30, 45, 60, 75, 90, 105, 120, 135, 150, 165, 180, 195, 210, 225, 240];
            const minTime = playtimeValues[activeMinPlaytime];
            const maxTime = playtimeValues[activeMaxPlaytime];
            filteredGamesData = filteredGamesData.filter(game => {
                const time = parseInt(game.playingTime);
                if (isNaN(time) || time <= 0) return false;
                if (activeMaxPlaytime === 15) {
                    return time >= minTime;
                } else {
                    return time >= minTime && time <= maxTime;
                }
            });
        }

        // 4. Rating Range Filter (User Rating)
        if (activeMinRating !== 1.0 || activeMaxRating !== 10.0) {
            filteredGamesData = filteredGamesData.filter(game => {
                const rating = parseFloat(game.userRating);
                if (isNaN(rating)) return false;
                return rating >= activeMinRating && rating <= activeMaxRating;
            });
        }

        // Re-sort after filtering/searching, maintaining current sort order
        if (currentSortColumn) {
            const columnType = headers.find(h => h.key === currentSortColumn)?.type || 'string';
            filteredGamesData.sort((a, b) => {
                let valA = a[currentSortColumn];
                let valB = b[currentSortColumn];

                if (columnType === 'number') {
                    valA = parseFloat(valA);
                    valB = parseFloat(valB);
                    if (isNaN(valA)) valA = currentSortDirection === 'asc' ? Infinity : -Infinity;
                    if (isNaN(valB)) valB = currentSortDirection === 'asc' ? Infinity : -Infinity;
                } else {
                    valA = String(valA).toLowerCase();
                    valB = String(valB).toLowerCase();
                }

                if (valA < valB) {
                    return currentSortDirection === 'asc' ? -1 : 1;
                } else if (valA > valB) {
                    return currentSortDirection === 'asc' ? 1 : -1;
                } else {
                    return 0;
                }
            });
        }
        
        renderTable();
        updateAnalytics();
    }

    // Set up controls event listeners
    document.getElementById('page-size-select').addEventListener('change', function() {
        pageSize = this.value;
        currentPage = 1;
        filterAndRender();
    });

    document.getElementById('game-search-input').addEventListener('input', function() {
        currentPage = 1;
        filterAndRender();
    });

    function updateViewToggleButtons() {
        const gridBtn = document.getElementById('view-mode-grid');
        const listBtn = document.getElementById('view-mode-list');
        if (gridBtn && listBtn) {
            if (currentViewMode === 'grid') {
                gridBtn.classList.add('active');
                listBtn.classList.remove('active');
            } else {
                gridBtn.classList.remove('active');
                listBtn.classList.add('active');
            }
        }
    }

    const modeGridBtn = document.getElementById('view-mode-grid');
    const modeListBtn = document.getElementById('view-mode-list');
    if (modeGridBtn && modeListBtn) {
        modeGridBtn.addEventListener('click', function() {
            if (currentViewMode === 'grid') return;
            currentViewMode = 'grid';
            updateViewToggleButtons();
            renderTable();
        });

        modeListBtn.addEventListener('click', function() {
            if (currentViewMode === 'list') return;
            currentViewMode = 'list';
            updateViewToggleButtons();
            renderTable();
        });
        
        updateViewToggleButtons();
    }

    function updateTrackHighlight(minInput, maxInput, trackId, rangeMin, rangeMax) {
        const track = document.getElementById(trackId);
        if (!track) return;
        const percent1 = ((parseFloat(minInput.value) - rangeMin) / (rangeMax - rangeMin)) * 100;
        const percent2 = ((parseFloat(maxInput.value) - rangeMin) / (rangeMax - rangeMin)) * 100;
        track.style.background = `linear-gradient(to right, var(--border) ${percent1}%, #10b981 ${percent1}%, #10b981 ${percent2}%, var(--border) ${percent2}%)`;
    }

    // Set up faceted filter listeners
    function setupFacetedFilters() {
        // Status chips (multi-select)
        document.querySelectorAll('.status-chip').forEach(chip => {
            chip.addEventListener('click', function() {
                const status = this.dataset.status;
                this.classList.toggle('active');
                if (this.classList.contains('active')) {
                    if (!activeStatuses.includes(status)) {
                        activeStatuses.push(status);
                    }
                } else {
                    activeStatuses = activeStatuses.filter(s => s !== status);
                }
                currentPage = 1;
                filterAndRender();
            });
        });

        // Helper to update players slider UI & state
        const playerMin = document.getElementById('player-min-input');
        const playerMax = document.getElementById('player-max-input');
        const playerVal = document.getElementById('player-slider-value');
        
        function updatePlayersUI() {
            let minVal = parseInt(playerMin.value);
            let maxVal = parseInt(playerMax.value);
            activeMinPlayers = minVal;
            activeMaxPlayers = maxVal;
            
            updateTrackHighlight(playerMin, playerMax, 'player-slider-track', 1, 8);
            
            if (minVal === 1 && maxVal === 8) {
                playerVal.textContent = 'Any';
            } else if (minVal === maxVal) {
                if (minVal === 8) {
                    playerVal.textContent = '8+ Players';
                } else if (minVal === 1) {
                    playerVal.textContent = '1 (Solo)';
                } else {
                    playerVal.textContent = `${minVal} Players`;
                }
            } else {
                if (maxVal === 8) {
                    playerVal.textContent = `${minVal} - 8+ Players`;
                } else {
                    playerVal.textContent = `${minVal} - ${maxVal} Players`;
                }
            }
        }

        if (playerMin && playerMax) {
            playerMin.addEventListener('input', function() {
                if (parseInt(playerMin.value) > parseInt(playerMax.value)) {
                    playerMin.value = playerMax.value;
                }
                updatePlayersUI();
                currentPage = 1;
                filterAndRender();
            });
            playerMax.addEventListener('input', function() {
                if (parseInt(playerMax.value) < parseInt(playerMin.value)) {
                    playerMax.value = playerMin.value;
                }
                updatePlayersUI();
                currentPage = 1;
                filterAndRender();
            });
            updatePlayersUI();
        }

        // Helper to update playtime slider UI & state
        const timeMin = document.getElementById('time-min-input');
        const timeMax = document.getElementById('time-max-input');
        const timeVal = document.getElementById('time-slider-value');
        const playtimeValues = [15, 30, 45, 60, 75, 90, 105, 120, 135, 150, 165, 180, 195, 210, 225, 240];

        function updatePlaytimeUI() {
            let minStep = parseInt(timeMin.value);
            let maxStep = parseInt(timeMax.value);
            activeMinPlaytime = minStep;
            activeMaxPlaytime = maxStep;

            updateTrackHighlight(timeMin, timeMax, 'time-slider-track', 0, 15);

            if (minStep === 0 && maxStep === 15) {
                timeVal.textContent = 'Any';
            } else if (minStep === maxStep) {
                if (minStep === 15) {
                    timeVal.textContent = '240+ Min';
                } else {
                    timeVal.textContent = `${playtimeValues[minStep]} Min`;
                }
            } else {
                if (maxStep === 15) {
                    timeVal.textContent = `${playtimeValues[minStep]} - 240+ Min`;
                } else {
                    timeVal.textContent = `${playtimeValues[minStep]} - ${playtimeValues[maxStep]} Min`;
                }
            }
        }

        if (timeMin && timeMax) {
            timeMin.addEventListener('input', function() {
                if (parseInt(timeMin.value) > parseInt(timeMax.value)) {
                    timeMin.value = timeMax.value;
                }
                updatePlaytimeUI();
                currentPage = 1;
                filterAndRender();
            });
            timeMax.addEventListener('input', function() {
                if (parseInt(timeMax.value) < parseInt(timeMin.value)) {
                    timeMax.value = timeMin.value;
                }
                updatePlaytimeUI();
                currentPage = 1;
                filterAndRender();
            });
            updatePlaytimeUI();
        }

        // Helper to update rating slider UI & state
        const ratingMin = document.getElementById('rating-min-input');
        const ratingMax = document.getElementById('rating-max-input');
        const ratingValDisplay = document.getElementById('rating-slider-value');

        function updateRatingUI() {
            let minV = parseFloat(ratingMin.value);
            let maxV = parseFloat(ratingMax.value);
            activeMinRating = minV;
            activeMaxRating = maxV;

            updateTrackHighlight(ratingMin, ratingMax, 'rating-slider-track', 1.0, 10.0);

            if (minV === 1.0 && maxV === 10.0) {
                ratingValDisplay.textContent = 'Any';
            } else if (minV === maxV) {
                ratingValDisplay.textContent = minV.toFixed(1);
            } else {
                ratingValDisplay.textContent = `${minV.toFixed(1)} - ${maxV.toFixed(1)}`;
            }
        }

        if (ratingMin && ratingMax) {
            ratingMin.addEventListener('input', function() {
                if (parseFloat(ratingMin.value) > parseFloat(ratingMax.value)) {
                    ratingMin.value = ratingMax.value;
                }
                updateRatingUI();
                currentPage = 1;
                filterAndRender();
            });
            ratingMax.addEventListener('input', function() {
                if (parseFloat(ratingMax.value) < parseFloat(ratingMin.value)) {
                    ratingMax.value = ratingMin.value;
                }
                updateRatingUI();
                currentPage = 1;
                filterAndRender();
            });
            updateRatingUI();
        }

        // Clear all filters button
        const clearBtn = document.getElementById('clear-all-filters');
        if (clearBtn) {
            clearBtn.addEventListener('click', function() {
                activeStatuses = [];
                activeMinPlayers = 1;
                activeMaxPlayers = 8;
                activeMinPlaytime = 0;
                activeMaxPlaytime = 15;
                activeMinRating = 1.0;
                activeMaxRating = 10.0;

                document.querySelectorAll('.status-chip').forEach(chip => chip.classList.remove('active'));
                
                if (playerMin && playerMax) {
                    playerMin.value = 1;
                    playerMax.value = 8;
                    updatePlayersUI();
                }
                if (timeMin && timeMax) {
                    timeMin.value = 0;
                    timeMax.value = 15;
                    updatePlaytimeUI();
                }
                if (ratingMin && ratingMax) {
                    ratingMin.value = 1.0;
                    ratingMax.value = 10.0;
                    updateRatingUI();
                }

                const searchInput = document.getElementById('game-search-input');
                if (searchInput) searchInput.value = '';

                currentPage = 1;
                filterAndRender();
            });
        }
    }

    // Initialize listeners
    setupFacetedFilters();

    document.getElementById('bgg-form').addEventListener('submit', async function (event) {
        event.preventDefault();

        const username = document.getElementById('bgg_username').value;
        if (!username) {
            alert('Please enter a BGG username.');
            return;
        }

        const lowerUsername = username.trim().toLowerCase();

        // Reset navigation and tab states; show collection layout, hide empty state immediately
        const tabsNav = document.getElementById('collection-tabs-nav');
        if (tabsNav) tabsNav.style.display = 'flex';
        document.getElementById('collection-layout-wrap').style.display = 'flex';
        document.getElementById('collection-empty-state').style.display = 'none';
        document.getElementById('collection-panel-grid').classList.remove('hidden');
        document.getElementById('collection-panel-analytics').classList.add('hidden');

        const apiBaseUrl = "{{ site.api_url }}";
        const isValidUrl = apiBaseUrl && (apiBaseUrl.startsWith('http://') || apiBaseUrl.startsWith('https://'));
        const apiUrl = isValidUrl
            ? `${apiBaseUrl}/collection?username=${lowerUsername}`
            : `https://boardgamegeek.com/xmlapi2/collection?username=${lowerUsername}&stats=1`;

        const collectionDataDiv = document.getElementById('collection-data');
        showCollectionSkeletons("Fetching collection data from BGG...");

        // Check cache first
        if (collectionCache[lowerUsername]) {
            console.log("Serving collection XML from cache for " + lowerUsername);
            processCollectionXml(collectionCache[lowerUsername], lowerUsername);
            return;
        }

        let xmlDoc = null;
        let attempts = 0;
        const maxAttempts = 6;

        while (attempts < maxAttempts) {
            attempts++;
            try {
                const response = await fetch(apiUrl);
                const text = await response.text();
                const parser = new DOMParser();
                xmlDoc = parser.parseFromString(text, "text/xml");

                // Check for API-specific errors within the XML
                const errors = xmlDoc.getElementsByTagName('errors');
                if (errors.length > 0) {
                    const errorMessage = errors[0].getElementsByTagName('error')[0]?.textContent || 'Unknown API error.';
                    collectionDataDiv.innerHTML = `
                        <div class="collection-message error">
                            BGG API Error: ${errorMessage}
                        </div>
                    `;
                    collectionDataDiv.classList.add('has-content');
                    document.getElementById('faceted-filters').style.display = 'none'; // Hide filters on API error
                    document.getElementById('browser-controls-bar').style.display = 'none';
                    renderPagination(0);
                    return;
                }

                // Check if response is BGG 202 processing queue message
                const messageTag = xmlDoc.getElementsByTagName('message');
                if (messageTag.length > 0 && (messageTag[0].textContent.includes('process') || messageTag[0].textContent.includes('queue') || messageTag[0].textContent.includes('accepted'))) {
                    console.log(`BGG is currently processing the collection for ${lowerUsername}. Retrying...`);
                    if (attempts < maxAttempts) {
                        showCollectionSkeletons(`BGG is processing request, retrying in 5s (Attempt ${attempts}/${maxAttempts})...`);
                        await new Promise(resolve => setTimeout(resolve, 5000));
                        continue;
                    } else {
                        collectionDataDiv.innerHTML = `
                            <div class="collection-message error">
                                BGG is still processing this collection. Please try again in a few minutes.
                            </div>
                        `;
                        collectionDataDiv.classList.add('has-content');
                        document.getElementById('faceted-filters').style.display = 'none';
                        document.getElementById('browser-controls-bar').style.display = 'none';
                        renderPagination(0);
                        return;
                    }
                }

                break;

            } catch (error) {
                console.error(`Attempt ${attempts}: Error fetching BGG collection:`, error);
                if (attempts < maxAttempts) {
                    showCollectionSkeletons(`Attempt ${attempts}: Network error fetching collection data. Retrying...`);
                    await new Promise(resolve => setTimeout(resolve, 2000)); // Wait 2 seconds before retrying
                } else {
                    collectionDataDiv.innerHTML = `
                        <div class="collection-message error">
                            Failed to fetch collection data after multiple retries due to network issues. Please try again later.
                        </div>
                    `;
                    collectionDataDiv.classList.add('has-content');
                    const sidebarDiv = document.getElementById('filters-column');
                    if (sidebarDiv) sidebarDiv.style.display = 'none';
                    document.getElementById('browser-controls-bar').style.display = 'none';
                    renderPagination(0);
                    return;
                }
            }
        }

        if (!xmlDoc) {
            collectionDataDiv.innerHTML = `
                <div class="collection-message error">
                    Failed to fetch collection data. Please try again later.
                </div>
            `;
            collectionDataDiv.classList.add('has-content');
            const sidebarDiv = document.getElementById('filters-column');
            if (sidebarDiv) sidebarDiv.style.display = 'none';
            document.getElementById('browser-controls-bar').style.display = 'none';
            renderPagination(0);
            return;
        }

        // Cache the successful XML doc if it has items
        const items = xmlDoc.getElementsByTagName('item');
        if (items.length > 0) {
            collectionCache[lowerUsername] = xmlDoc;
        }

        processCollectionXml(xmlDoc, lowerUsername);
    });

    // Sync BGG username from backend preferences if logged in
    async function loadPreferencesBggUsername() {
        if (typeof Auth === 'undefined' || !Auth.isLoggedIn()) return;

        try {
            const response = await fetchApi('/preferences');
            if (response.ok) {
                const data = await response.json();
                if (data.bgg_username) {
                    const input = document.getElementById("bgg_username");
                    if (input) {
                        input.value = data.bgg_username;
                        
                        // Automatically submit the form to load the collection if the input is pre-populated
                        // and the collection hasn't been loaded yet.
                        const form = document.getElementById("bgg-form");
                        if (form && !document.getElementById("collection-data").classList.contains("has-content")) {
                            form.dispatchEvent(new Event("submit"));
                        }
                    }
                }
            }
        } catch (e) {
            console.error("Failed to fetch preferences in collection browser:", e);
        }
    }

    function setupInfiniteScroll() {
        const scrollContainer = document.getElementById('main-wrapper');
        if (!scrollContainer) return;

        scrollContainer.addEventListener('scroll', function() {
            if (currentViewMode !== 'grid') return;
            if (isInfiniteScrollLoading) return;

            const threshold = 250; // pixels from the bottom
            const isNearBottom = scrollContainer.scrollHeight - scrollContainer.scrollTop - scrollContainer.clientHeight <= threshold;

            if (isNearBottom) {
                loadMoreGames();
            }
        });
    }

    function loadMoreGames() {
        if (currentLoadedCount >= filteredGamesData.length) return;
        
        isInfiniteScrollLoading = true;
        // The loader is appended dynamically by renderTable() -> renderCardGrid()
        setTimeout(() => {
            currentLoadedCount += 25;
            renderTable();
            isInfiniteScrollLoading = false;
        }, 300);
    }

    // Load preferences on DOMContentLoaded and on login success event
    loadPreferencesBggUsername();
    document.addEventListener("bgg_login_success", loadPreferencesBggUsername);
    setupInfiniteScroll();
