/**
 * Cafe Patron Portal & Vibe Check UI - Client Script (cafe.js)
 * Implements mobile-first 3-tap vibe quiz, venue branding, and game card rendering.
 */

(function () {
    "use strict";

    // Application State
    const state = {
        cafeId: "",
        venueMeta: null,
        table: "1",
        activeTab: "collection",
        collection: [],
        filteredCollection: [],
        recommendations: [],
        searchQuery: "",
        activeFilter: "all",
        sortBy: "name_asc",
        isCollectionLoading: false,
        quiz: {
            playerCount: "4",
            duration: "medium",
            vibe: "casual_strategy",
            hobbyistUsers: ""
        },
        isLoading: false,
        activeVoteSession: null,
        userBallot: {}
    };

    // Helper: Parse URL parameters or fallback to path/storage
    function parseVenueContext() {
        const urlParams = new URLSearchParams(window.location.search);
        
        // 1. Extract cafe ID
        let cafeId = urlParams.get("cafe") || urlParams.get("cafe_id") || urlParams.get("id");
        if (!cafeId) {
            // Check path segments: e.g. /cafe/the-malt-and-meeple
            const pathParts = window.location.pathname.split("/").filter(Boolean);
            const cafeIdx = pathParts.indexOf("cafe");
            if (cafeIdx !== -1 && pathParts.length > cafeIdx + 1) {
                const seg = pathParts[cafeIdx + 1];
                if (seg !== "index.html" && seg !== "manage" && seg !== "onboard") {
                    cafeId = seg;
                }
            }
        }

        // If no cafe is provided in URL or path, do NOT assume a venue or table!
        if (!cafeId) {
            state.cafeId = "";
            state.table = "";
            return false;
        }

        // 2. Extract table (optional)
        let table = urlParams.get("table");

        state.cafeId = cafeId.trim().toLowerCase();
        state.table = table ? table.trim() : (sessionStorage.getItem("cafe_patron_table") || "");

        // Persist in session
        try {
            sessionStorage.setItem("cafe_patron_cafe_id", state.cafeId);
            if (state.table) sessionStorage.setItem("cafe_patron_table", state.table);
        } catch (e) {}

        return true;
    }

    // Load saved quiz state from sessionStorage if available
    function restoreQuizState() {
        try {
            const saved = sessionStorage.getItem("cafe_patron_quiz_state");
            if (saved) {
                const parsed = JSON.parse(saved);
                if (parsed.playerCount) state.quiz.playerCount = parsed.playerCount;
                if (parsed.duration) state.quiz.duration = parsed.duration;
                if (parsed.vibe) state.quiz.vibe = parsed.vibe;
                if (parsed.hobbyistUsers) state.quiz.hobbyistUsers = parsed.hobbyistUsers;
            }
        } catch (e) {}
    }

    function saveQuizState() {
        try {
            sessionStorage.setItem("cafe_patron_quiz_state", JSON.stringify(state.quiz));
        } catch (e) {}
    }

    // Fetch Venue Metadata
    async function loadVenueMetadata() {
        const titleEl = document.getElementById("venue-name-title");
        const taglineEl = document.getElementById("venue-tagline");
        const tableBadge = document.getElementById("header-table-badge");
        const wifiSsid = document.getElementById("wifi-ssid-label");
        const wifiPass = document.getElementById("wifi-pass-label");
        const wifiChip = document.getElementById("header-wifi-chip");
        const avatarEl = document.getElementById("venue-avatar-wrap");

        if (tableBadge) {
            tableBadge.textContent = state.table ? `🪑 Table ${state.table}` : "🪑 Seating (Set Table #)";
        }
        const ctaTableNum = document.getElementById("cta-table-num");
        if (ctaTableNum) {
            ctaTableNum.textContent = state.table ? state.table : "1";
        }

        try {
            const resp = await window.fetchApi(`/cafe/meta?cafe_id=${encodeURIComponent(state.cafeId)}`);
            if (resp.ok) {
                const data = await resp.json();
                state.venueMeta = data;
                
                if (titleEl && data.name) titleEl.textContent = data.name;
                if (taglineEl && data.tagline) taglineEl.textContent = data.tagline;
                if (avatarEl && data.logo_url) {
                    avatarEl.innerHTML = `<img src="${window.escapeHTML ? window.escapeHTML(data.logo_url) : data.logo_url}" alt="Logo">`;
                }

                // Wi-Fi setup
                if (wifiChip) {
                    if (data.wifi_ssid) {
                        wifiChip.style.display = "inline-flex";
                        if (wifiSsid) wifiSsid.textContent = data.wifi_ssid;
                        if (wifiPass && data.wifi_password) {
                            wifiPass.textContent = `(${data.wifi_password})`;
                        } else if (wifiPass) {
                            wifiPass.textContent = "";
                        }
                    } else {
                        wifiChip.style.display = "none";
                    }
                }
                return;
            }
        } catch (err) {
            console.warn("Failed fetching venue metadata, using fallback:", err);
        }

        // Default fallback branding if venue not found
        state.venueMeta = {
            cafe_id: state.cafeId,
            name: "The Malt & Meeple Cafe",
            tagline: "Craft brews & 500+ tabletop games on tap.",
            wifi_ssid: "MaltMeeple-Guest",
            wifi_password: "rollforinitiative",
            drink_pairings_enabled: true,
            bgg_username: "maltandmeeple"
        };
        if (titleEl) titleEl.textContent = state.venueMeta.name;
        if (taglineEl) taglineEl.textContent = state.venueMeta.tagline;
        if (wifiSsid) wifiSsid.textContent = state.venueMeta.wifi_ssid;
        if (wifiPass) wifiPass.textContent = `(${state.venueMeta.wifi_password})`;
    }

    // Set up interactive single-select pills and cards
    function setupQuizControls() {
        // Step 1: Player Count Pills
        const playerPills = document.querySelectorAll("[data-player-count]");
        playerPills.forEach(pill => {
            const count = pill.getAttribute("data-player-count");
            if (count === state.quiz.playerCount) {
                pill.classList.add("active");
            } else {
                pill.classList.remove("active");
            }

            pill.addEventListener("click", () => {
                playerPills.forEach(p => p.classList.remove("active"));
                pill.classList.add("active");
                state.quiz.playerCount = count;
                saveQuizState();
            });
        });

        // Step 2: Time Window Pills
        const timePills = document.querySelectorAll("[data-time-duration]");
        timePills.forEach(pill => {
            const duration = pill.getAttribute("data-time-duration");
            if (duration === state.quiz.duration) {
                pill.classList.add("active");
            } else {
                pill.classList.remove("active");
            }

            pill.addEventListener("click", () => {
                timePills.forEach(p => p.classList.remove("active"));
                pill.classList.add("active");
                state.quiz.duration = duration;
                saveQuizState();
            });
        });

        // Step 3: Vibe Cards
        const vibeCards = document.querySelectorAll("[data-vibe-key]");
        vibeCards.forEach(card => {
            const vibeKey = card.getAttribute("data-vibe-key");
            if (vibeKey === state.quiz.vibe) {
                card.classList.add("active");
            } else {
                card.classList.remove("active");
            }

            card.addEventListener("click", () => {
                vibeCards.forEach(c => c.classList.remove("active"));
                card.classList.add("active");
                state.quiz.vibe = vibeKey;
                saveQuizState();
            });
        });

        // Hobbyist Bypass Accordion
        const hobbyistToggle = document.getElementById("hobbyist-accordion-toggle");
        const hobbyistAccordion = document.getElementById("hobbyist-accordion");
        const hobbyistInput = document.getElementById("hobbyist-usernames-input");

        if (hobbyistToggle && hobbyistAccordion) {
            hobbyistToggle.addEventListener("click", () => {
                hobbyistAccordion.classList.toggle("open");
            });
        }

        if (hobbyistInput) {
            hobbyistInput.value = state.quiz.hobbyistUsers || "";
            hobbyistInput.addEventListener("input", (e) => {
                state.quiz.hobbyistUsers = e.target.value.trim();
                saveQuizState();
            });
        }

        // Table Switcher
        const switchTableBtn = document.getElementById("switch-table-trigger");
        if (switchTableBtn) {
            switchTableBtn.addEventListener("click", () => {
                const newTable = prompt("Enter your table number:", state.table);
                if (newTable && newTable.trim()) {
                    state.table = newTable.trim();
                    try {
                        sessionStorage.setItem("cafe_patron_table", state.table);
                    } catch (e) {}
                    const tableBadge = document.getElementById("header-table-badge");
                    if (tableBadge) tableBadge.textContent = `🪑 Table ${state.table}`;
                    const resTitle = document.getElementById("results-table-num");
                    if (resTitle) resTitle.textContent = state.table;
                    const ctaTableEl = document.getElementById("cta-table-num");
                    if (ctaTableEl) ctaTableEl.textContent = state.table;
                }
            });
        }

        // Wi-Fi Copy action
        const wifiChip = document.getElementById("header-wifi-chip");
        if (wifiChip) {
            wifiChip.addEventListener("click", () => {
                const pass = state.venueMeta && state.venueMeta.wifi_password ? state.venueMeta.wifi_password : "rollforinitiative";
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText(pass).then(() => {
                        const orig = wifiChip.getAttribute("title") || "";
                        wifiChip.setAttribute("title", "Copied to clipboard!");
                        alert(`Copied Wi-Fi password: "${pass}"`);
                    }).catch(() => {
                        prompt("Copy Wi-Fi password:", pass);
                    });
                } else {
                    prompt("Copy Wi-Fi password:", pass);
                }
            });
        }

        // Re-roll / change filters button
        const rerollBtn = document.getElementById("btn-reroll-quiz");
        if (rerollBtn) {
            rerollBtn.addEventListener("click", () => {
                const quizCard = document.getElementById("vibe-quiz-card");
                if (quizCard && typeof quizCard.scrollIntoView === "function") {
                    quizCard.scrollIntoView({ behavior: "smooth", block: "start" });
                }
            });
        }

        // Form Submit
        const quizForm = document.getElementById("vibe-quiz-form");
        if (quizForm) {
            quizForm.addEventListener("submit", (e) => {
                e.preventDefault();
                fetchCafeRecommendations();
            });
        }
    }

    // Recommendation Fetcher
    async function fetchCafeRecommendations() {
        if (state.isLoading) return;
        state.isLoading = true;

        const resultsSection = document.getElementById("results-section");
        const resultsContainer = document.getElementById("cafe-results-container");
        const submitBtn = document.getElementById("quiz-submit-btn");
        const resTableNum = document.getElementById("results-table-num");

        if (resTableNum) resTableNum.textContent = state.table ? state.table : "Your Table";
        if (resultsSection) resultsSection.style.display = "block";

        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerHTML = `<span>🎲 Finding Recommendations...</span>`;
        }

        // Render skeleton cards
        renderCafeSkeletons(resultsContainer, 3);
        if (resultsSection && typeof resultsSection.scrollIntoView === "function") {
            resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
        }

        // Determine cafe BGG username / ID
        const targetCafe = (state.venueMeta && state.venueMeta.bgg_username) 
            ? state.venueMeta.bgg_username 
            : state.cafeId;

        const params = new URLSearchParams({
            cafe_id: targetCafe,
            vibe: state.quiz.vibe,
            player_count: state.quiz.playerCount === "6+" ? "6" : state.quiz.playerCount,
            duration_pref: state.quiz.duration,
            table: state.table || "General"
        });

        // Hobbyist usernames if provided
        if (state.quiz.hobbyistUsers) {
            params.set("username", state.quiz.hobbyistUsers);
        }

        try {
            const resp = await window.fetchApi(`/recommendations?${params.toString()}`);
            const data = await resp.json();

            state.isLoading = false;
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.innerHTML = `<span>🎲 Find Our Table's Game</span>`;
            }

            if (!resp.ok) {
                renderErrorState(resultsContainer, data.error || "Unable to load recommendations.");
                return;
            }

            if (data.status === "scraping") {
                renderScrapingState(resultsContainer, data.message || "Syncing library for this venue...");
                return;
            }

            const recs = data.recommendations || [];
            state.recommendations = recs;
            if (recs.length === 0) {
                renderEmptyState(resultsContainer);
            } else {
                renderCafeCards(resultsContainer, recs);
            }
        } catch (err) {
            state.isLoading = false;
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.innerHTML = `<span>🎲 Find Our Table's Game</span>`;
            }
            renderErrorState(resultsContainer, "Network error retrieving recommendations. Please try again.");
        }
    }

    // Estimate teach time if not explicitly provided
    function estimateTeachTime(complexity) {
        if (!complexity) return "5-10 min teach";
        const c = parseFloat(complexity);
        if (c < 1.8) return "3-5 min teach";
        if (c < 2.6) return "5-10 min teach";
        if (c < 3.4) return "10-15 min teach";
        return "15-20 min teach";
    }

    // Derive Drink Pairing based on Vibe
    function getDrinkPairing(vibe) {
        const pairings = {
            party: "🍺 Guru Pairing: Crisp Pilsner, Hard Seltzer, or Loaded Nachos",
            casual_strategy: "🍷 Guru Pairing: Hazy IPA, Red Blend, or Artisan Flatbread",
            deep_strategy: "☕ Guru Pairing: Nitro Cold Brew, Imperial Stout, or Pretzel Bites",
            cooperative: "🍹 Guru Pairing: Shareable Craft Pitcher or Warm Cider",
            direct_conflict: "🥃 Guru Pairing: Smoked Old Fashioned or Buffalo Wings"
        };
        return pairings[vibe] || pairings.casual_strategy;
    }

    // Render Game Cards (Shared for Collection Browser & Recommendations)
    function renderCafeCards(container, recs, options = {}) {
        const isRecView = options.isRecommendationView !== false;
        const escape = window.escapeHTML || (s => s ? String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])) : "");
        let html = "";

        recs.forEach((rec, idx) => {
            const thumb = rec.thumbnail || "https://cf.geekdo-images.com/images/placeholder_thumb.png";
            const bggUrl = rec.id ? `https://boardgamegeek.com/boardgame/${rec.id}` : `https://boardgamegeek.com/geeksearch.php?action=search&objecttype=boardgame&q=${encodeURIComponent(rec.name)}`;
            const videoUrl = `https://www.youtube.com/results?search_query=${encodeURIComponent(rec.name + " board game how to play rules")}`;

            // Prominent Shelf Location (Only if present in comments/data - STRICTLY NO fallback)
            const shelf = (rec.shelf_location || rec.shelf || "").trim();
            const shelfBadgeHtml = shelf ? `
                <span class="shelf-location-badge" title="Physical shelf location in cafe">
                    📍 ${escape(shelf)}
                </span>
            ` : "";
            
            // Teach Time
            const teach = rec.teach_time || estimateTeachTime(rec.complexity);

            // Stats
            const ratingStr = rec.rating ? `<span class="cafe-stat-pill" title="BGG Rating">★ ${parseFloat(rec.rating).toFixed(1)}</span>` : "";
            
            let compClass = "complexity-light";
            if (rec.complexity >= 3.2) compClass = "complexity-heavy";
            else if (rec.complexity >= 2.2) compClass = "complexity-med";
            const compStr = rec.complexity ? `<span class="cafe-stat-pill ${compClass}" title="Game Complexity">⚙ ${parseFloat(rec.complexity).toFixed(1)}/5</span>` : "";

            let playerStr = "";
            if (rec.min_players && rec.max_players) {
                const p = rec.min_players === rec.max_players ? rec.min_players : `${rec.min_players}-${rec.max_players}`;
                playerStr = `<span class="cafe-stat-pill" title="Player Count">👥 ${p} Players</span>`;
            }

            let timeStr = "";
            if (rec.playing_time || rec.min_playtime) {
                const t = rec.playing_time || rec.min_playtime;
                timeStr = `<span class="cafe-stat-pill" title="Playtime">🕒 ${t}m</span>`;
            }

            // Sommelier Quote (in recommendation view or if explicitly included)
            let quoteHtml = "";
            if (isRecView) {
                const reasonText = rec.reason || `Perfect for Table ${state.table}! High engagement with clean rules and satisfying decisions.`;
                quoteHtml = `
                    <div class="sommelier-quote-bubble">
                        <div class="sommelier-header">
                            <span>🍷 Cafe Guru Recommendation</span>
                        </div>
                        <p class="sommelier-quote-text">"${escape(reasonText)}"</p>
                    </div>
                `;
            }

            // Drink Pairing (in recommendation view)
            const drinkTag = (isRecView && state.venueMeta && state.venueMeta.drink_pairings_enabled !== false) 
                ? `<div class="drink-pairing-tag">${escape(getDrinkPairing(state.quiz.vibe))}</div>` 
                : "";

            // Genre / Mechanic Tags for collection browser
            let tagsHtml = "";
            if (!isRecView && (rec.mechanics || rec.categories)) {
                const tags = [
                    ...(Array.isArray(rec.mechanics) ? rec.mechanics.slice(0, 2) : []),
                    ...(Array.isArray(rec.categories) ? rec.categories.slice(0, 1) : [])
                ];
                if (tags.length > 0) {
                    tagsHtml = `<div class="cafe-card-tags">${tags.map(t => `<span class="cafe-genre-tag">${escape(t)}</span>`).join('')}</div>`;
                }
            }

            html += `
                <div class="cafe-game-card" style="animation-delay: ${idx * 0.04}s;">
                    <div class="cafe-card-top">
                        <div class="cafe-card-thumb-wrap">
                            <img class="cafe-card-thumb" src="${thumb}" alt="${escape(rec.name)}" loading="lazy" onerror="this.onerror=null; this.src='https://cf.geekdo-images.com/images/placeholder_thumb.png';">
                        </div>
                        <div class="cafe-card-info">
                            <div class="cafe-card-title-row">
                                <a href="${bggUrl}" target="_blank" class="cafe-card-title">${escape(rec.name)}</a>
                                ${rec.year_published ? `<span class="cafe-card-year">(${rec.year_published})</span>` : ''}
                            </div>

                            <!-- Badges (Shelf Location strictly if present, Teach Time) -->
                            <div class="cafe-prominent-badges">
                                ${shelfBadgeHtml}
                                <span class="teach-time-badge" title="Estimated rules explanation time">
                                    ⏱️ ${escape(teach)}
                                </span>
                            </div>

                            <div class="cafe-stats-row">
                                ${ratingStr}
                                ${compStr}
                                ${playerStr}
                                ${timeStr}
                            </div>

                            ${tagsHtml}
                        </div>
                    </div>

                    ${quoteHtml}
                    ${drinkTag}

                    <!-- Actions -->
                    <div class="cafe-card-actions">
                        <button type="button" class="btn-card-action primary btn-watch-rules" data-game-id="${escape(rec.id)}" title="Watch video rules tutorial in-app">
                            🎬 Watch Rules
                        </button>
                        <a href="${bggUrl}" target="_blank" class="btn-card-action" rel="noopener noreferrer">
                            📖 BGG Info
                        </a>
                    </div>
                </div>
            `;
        });

        container.innerHTML = html;
    }

    // Render Skeletons during loading
    function renderCafeSkeletons(container, count = 3) {
        let html = "";
        for (let i = 0; i < count; i++) {
            html += `
                <div class="cafe-game-card" style="opacity: 0.85;">
                    <div class="cafe-card-top">
                        <div class="skeleton" style="width: 82px; height: 82px; border-radius: 12px; flex-shrink: 0;"></div>
                        <div class="cafe-card-info" style="gap: 8px;">
                            <div class="skeleton" style="width: 65%; height: 22px; border-radius: 6px;"></div>
                            <div style="display: flex; gap: 8px;">
                                <div class="skeleton" style="width: 90px; height: 24px; border-radius: 8px;"></div>
                                <div class="skeleton" style="width: 100px; height: 24px; border-radius: 8px;"></div>
                            </div>
                            <div style="display: flex; gap: 6px;">
                                <div class="skeleton" style="width: 50px; height: 20px; border-radius: 6px;"></div>
                                <div class="skeleton" style="width: 60px; height: 20px; border-radius: 6px;"></div>
                                <div class="skeleton" style="width: 70px; height: 20px; border-radius: 6px;"></div>
                            </div>
                        </div>
                    </div>
                    <div class="skeleton" style="width: 100%; height: 50px; border-radius: 12px; margin-top: 4px;"></div>
                </div>
            `;
        }
        container.innerHTML = html;
    }

    // Render Empty State with Filter Relaxation
    function renderEmptyState(container) {
        container.innerHTML = `
            <div class="empty-results-card">
                <div class="empty-icon">🎲</div>
                <h3 class="empty-title">No Exact Shelf Matches</h3>
                <p class="empty-desc">
                    We couldn't find an exact fit for <strong>${state.quiz.playerCount} players</strong> in 
                    <strong>${state.quiz.duration} duration</strong> with <strong>${state.quiz.vibe.replace('_', ' ')}</strong> vibe. 
                    Try relaxing one of your filters below:
                </p>
                <div class="relaxation-chips-wrap">
                    <button type="button" class="btn-relax-filter" id="relax-time-btn">⏱️ Any Playtime</button>
                    <button type="button" class="btn-relax-filter" id="relax-vibe-btn">🍻 Casual Strategy Vibe</button>
                    <button type="button" class="btn-relax-filter" id="relax-players-btn">👥 Any Player Count</button>
                </div>
            </div>
        `;

        const relaxTime = document.getElementById("relax-time-btn");
        if (relaxTime) {
            relaxTime.addEventListener("click", () => {
                state.quiz.duration = "any";
                saveQuizState();
                fetchCafeRecommendations();
            });
        }

        const relaxVibe = document.getElementById("relax-vibe-btn");
        if (relaxVibe) {
            relaxVibe.addEventListener("click", () => {
                state.quiz.vibe = "casual_strategy";
                // Update UI active card
                document.querySelectorAll("[data-vibe-key]").forEach(c => {
                    c.classList.toggle("active", c.getAttribute("data-vibe-key") === "casual_strategy");
                });
                saveQuizState();
                fetchCafeRecommendations();
            });
        }

        const relaxPlayers = document.getElementById("relax-players-btn");
        if (relaxPlayers) {
            relaxPlayers.addEventListener("click", () => {
                state.quiz.playerCount = "any";
                saveQuizState();
                fetchCafeRecommendations();
            });
        }
    }

    // Render Scraping State
    function renderScrapingState(container, msg) {
        container.innerHTML = `
            <div class="empty-results-card">
                <div class="empty-icon">⏳</div>
                <h3 class="empty-title">Updating Shelf Inventory</h3>
                <p class="empty-desc">${window.escapeHTML ? window.escapeHTML(msg) : msg}</p>
                <p style="font-size: 0.8rem; color: var(--text-muted);">Please check back in a few moments.</p>
                <button type="button" class="btn-relax-filter" onclick="window.location.reload();">🔄 Refresh Page</button>
            </div>
        `;
    }

    // Render Error State
    function renderErrorState(container, msg) {
        container.innerHTML = `
            <div class="empty-results-card">
                <div class="empty-icon">⚠️</div>
                <h3 class="empty-title">Something went wrong</h3>
                <p class="empty-desc">${window.escapeHTML ? window.escapeHTML(msg) : msg}</p>
                <button type="button" class="btn-relax-filter" id="retry-fetch-btn">🔄 Retry</button>
            </div>
        `;
        const retryBtn = document.getElementById("retry-fetch-btn");
        if (retryBtn) {
            retryBtn.addEventListener("click", fetchCafeRecommendations);
        }
    }

    function setupGatewayControls() {
        const slugInput = document.getElementById("gateway-slug-input");
        const slugBtn = document.getElementById("gateway-slug-btn");
        if (slugBtn && slugInput) {
            slugBtn.addEventListener("click", () => {
                const val = slugInput.value.trim().toLowerCase();
                if (val) {
                    window.location.search = `?cafe=${encodeURIComponent(val)}`;
                }
            });
            slugInput.addEventListener("keypress", (e) => {
                if (e.key === "Enter") {
                    slugBtn.click();
                }
            });
        }
    }

    // Tab Switcher between Collection Browser and Recommender
    function switchTab(tabName) {
        state.activeTab = tabName;
        const tabColBtn = document.getElementById("tab-btn-collection");
        const tabRecBtn = document.getElementById("tab-btn-recommender");
        const collectionView = document.getElementById("cafe-collection-view");
        const recommenderView = document.getElementById("cafe-recommender-view");

        if (tabName === "recommender") {
            if (tabColBtn) {
                tabColBtn.classList.remove("active");
                tabColBtn.setAttribute("aria-selected", "false");
            }
            if (tabRecBtn) {
                tabRecBtn.classList.add("active");
                tabRecBtn.setAttribute("aria-selected", "true");
            }
            if (collectionView) collectionView.style.display = "none";
            if (recommenderView) recommenderView.style.display = "block";
            const quizCard = document.getElementById("vibe-quiz-card");
            if (quizCard && typeof quizCard.scrollIntoView === "function") {
                quizCard.scrollIntoView({ behavior: "smooth", block: "start" });
            }
        } else {
            if (tabRecBtn) {
                tabRecBtn.classList.remove("active");
                tabRecBtn.setAttribute("aria-selected", "false");
            }
            if (tabColBtn) {
                tabColBtn.classList.add("active");
                tabColBtn.setAttribute("aria-selected", "true");
            }
            if (collectionView) collectionView.style.display = "block";
            if (recommenderView) recommenderView.style.display = "none";
        }
    }

    // Fetch Cafe Library for Collection Browser
    async function loadCafeCollection() {
        const grid = document.getElementById("cafe-collection-grid");
        const countBadge = document.getElementById("collection-count-badge");
        const resultsCount = document.getElementById("collection-results-count");

        if (state.isCollectionLoading) return;
        state.isCollectionLoading = true;

        if (grid) renderCafeSkeletons(grid, 6);
        if (resultsCount) resultsCount.textContent = "Loading library...";

        const targetCafe = (state.venueMeta && state.venueMeta.bgg_username) 
            ? state.venueMeta.bgg_username 
            : state.cafeId;

        const hasValidGames = (obj) => obj && ((Array.isArray(obj.collection) && obj.collection.length > 0) || (Array.isArray(obj.recommendations) && obj.recommendations.length > 0));

        // Fast path: Check sessionStorage for instant (0ms) library retrieval on repeated visits
        const sessionKey = `cafe_collection_${targetCafe}`;
        try {
            const cachedRaw = sessionStorage.getItem(sessionKey);
            if (cachedRaw) {
                const cachedData = JSON.parse(cachedRaw);
                if (hasValidGames(cachedData)) {
                    state.isCollectionLoading = false;
                    state.collection = (Array.isArray(cachedData.collection) && cachedData.collection.length > 0)
                        ? cachedData.collection 
                        : (cachedData.recommendations || []);
                    if (countBadge) countBadge.textContent = state.collection.length;
                    filterAndSortCollection();
                    return;
                }
            }
        } catch (storageErr) {
            // Ignore sessionStorage read errors (e.g. incognito/disabled)
        }

        let data = null;
        try {
            // Try collection endpoint first
            let resp = await window.fetchApi(`/cafe/collection?cafe_id=${encodeURIComponent(targetCafe)}`);
            if (resp && resp.ok) {
                data = await resp.json();
            }
        } catch (err) {
            console.warn("Failed fetching cafe collection, trying recommendations fallback:", err);
        }

        // Fallback to recommendations endpoint with vibe=any if collection endpoint failed, threw, or returned 0 games
        if (!hasValidGames(data)) {
            try {
                let resp = await window.fetchApi(`/recommendations?cafe_id=${encodeURIComponent(targetCafe)}&vibe=any`);
                if (resp && resp.ok) {
                    const fallbackData = await resp.json();
                    if (hasValidGames(fallbackData)) {
                        data = fallbackData;
                    }
                }
            } catch (fallbackErr) {
                console.warn("Failed fetching fallback cafe recommendations:", fallbackErr);
            }
        }

        state.isCollectionLoading = false;

        if (hasValidGames(data)) {
            state.collection = (Array.isArray(data.collection) && data.collection.length > 0) ? data.collection : (data.recommendations || []);
            try {
                sessionStorage.setItem(sessionKey, JSON.stringify({ collection: state.collection }));
            } catch (storageErr) {
                // Ignore sessionStorage quota errors
            }
            if (countBadge) countBadge.textContent = state.collection.length;
            filterAndSortCollection();
            return;
        }

        state.isCollectionLoading = false;
        state.collection = [];
        if (grid) {
            grid.innerHTML = `
                <div class="empty-results-card" style="grid-column: 1 / -1;">
                    <div class="empty-icon">⚠️</div>
                    <h3 class="empty-title">Could not load library</h3>
                    <p class="empty-desc">Failed to connect to this venue's collection.</p>
                    <button type="button" class="btn-relax-filter" id="retry-collection-btn">🔄 Retry</button>
                </div>
            `;
            const retry = document.getElementById("retry-collection-btn");
            if (retry) retry.addEventListener("click", loadCafeCollection);
        }
    }

    // Filter and Sort Collection Browser items
    function filterAndSortCollection() {
        const grid = document.getElementById("cafe-collection-grid");
        const resultsCount = document.getElementById("collection-results-count");
        if (!grid) return;

        let list = [...state.collection];
        const q = (state.searchQuery || "").trim().toLowerCase();

        // 1. Search Query Filter
        if (q) {
            list = list.filter(game => {
                const name = (game.name || "").toLowerCase();
                const mechs = Array.isArray(game.mechanics) ? game.mechanics.join(" ").toLowerCase() : "";
                const cats = Array.isArray(game.categories) ? game.categories.join(" ").toLowerCase() : "";
                const shelf = (game.shelf_location || game.shelf || "").toLowerCase();
                const year = String(game.year_published || "");
                return name.includes(q) || mechs.includes(q) || cats.includes(q) || shelf.includes(q) || year.includes(q);
            });
        }

        // 2. Chip Filter
        const f = state.activeFilter;
        if (f === "2p") {
            list = list.filter(g => (g.min_players <= 2 && g.max_players >= 2));
        } else if (f === "4p") {
            list = list.filter(g => (g.min_players <= 4 && g.max_players >= 4));
        } else if (f === "party") {
            list = list.filter(g => (g.max_players >= 5));
        } else if (f === "short") {
            list = list.filter(g => {
                const t = g.playing_time || g.min_playtime || 0;
                return t > 0 && t <= 30;
            });
        } else if (f === "strategy") {
            list = list.filter(g => (g.complexity >= 2.5));
        } else if (f === "coop") {
            list = list.filter(g => {
                const mechs = (Array.isArray(g.mechanics) ? g.mechanics.join(" ") : "").toLowerCase();
                const desc = (g.reason || "").toLowerCase();
                return mechs.includes("cooperative") || desc.includes("cooperative") || desc.includes("co-op");
            });
        } else if (f === "shelved") {
            list = list.filter(g => !!(g.shelf_location || g.shelf));
        }

        // 3. Sort
        const sort = state.sortBy;
        list.sort((a, b) => {
            if (sort === "name_asc") {
                return (a.name || "").localeCompare(b.name || "");
            } else if (sort === "rating_desc") {
                return (parseFloat(b.rating) || 0) - (parseFloat(a.rating) || 0);
            } else if (sort === "complexity_asc") {
                return (parseFloat(a.complexity) || 0) - (parseFloat(b.complexity) || 0);
            } else if (sort === "complexity_desc") {
                return (parseFloat(b.complexity) || 0) - (parseFloat(a.complexity) || 0);
            } else if (sort === "playtime_asc") {
                const ta = a.playing_time || a.min_playtime || 999;
                const tb = b.playing_time || b.min_playtime || 999;
                return ta - tb;
            }
            return 0;
        });

        state.filteredCollection = list;

        // Update counts
        if (resultsCount) {
            if (state.collection.length === 0) {
                resultsCount.textContent = "No games found in catalog";
            } else if (list.length === state.collection.length) {
                resultsCount.textContent = `Showing all ${list.length} games`;
            } else {
                resultsCount.textContent = `Showing ${list.length} of ${state.collection.length} games`;
            }
        }

        // Render Cards or Empty State
        if (list.length === 0) {
            const escape = window.escapeHTML || (s => s);
            grid.innerHTML = `
                <div class="empty-results-card" style="grid-column: 1 / -1;">
                    <div class="empty-icon">🔍</div>
                    <h3 class="empty-title">No games found</h3>
                    <p class="empty-desc">
                        ${q ? `No titles matching "<strong>${escape(q)}</strong>"` : "No games match the selected filters."}
                    </p>
                    <button type="button" class="btn-relax-filter" id="btn-reset-filters">
                        ✕ Clear Search &amp; Filters
                    </button>
                </div>
            `;
            const resetBtn = document.getElementById("btn-reset-filters");
            if (resetBtn) {
                resetBtn.addEventListener("click", () => {
                    const searchInput = document.getElementById("cafe-search-input");
                    const searchClear = document.getElementById("cafe-search-clear");
                    if (searchInput) searchInput.value = "";
                    if (searchClear) searchClear.style.display = "none";
                    state.searchQuery = "";
                    state.activeFilter = "all";
                    document.querySelectorAll(".cafe-filter-chip").forEach(c => {
                        c.classList.toggle("active", c.getAttribute("data-filter") === "all");
                    });
                    filterAndSortCollection();
                });
            }
        } else {
            renderCafeCards(grid, list, { isRecommendationView: false });
        }
    }

    // Set up Collection Browser controls & event handlers
    function setupCollectionControls() {
        // Tab switcher
        const tabColBtn = document.getElementById("tab-btn-collection");
        const tabRecBtn = document.getElementById("tab-btn-recommender");
        if (tabColBtn) tabColBtn.addEventListener("click", () => switchTab("collection"));
        if (tabRecBtn) tabRecBtn.addEventListener("click", () => switchTab("recommender"));

        // Launch recommender CTA button
        const launchBtn = document.getElementById("btn-launch-recommender");
        if (launchBtn) launchBtn.addEventListener("click", () => switchTab("recommender"));

        // Back to library buttons
        const backBtn = document.getElementById("btn-back-to-library");
        if (backBtn) backBtn.addEventListener("click", () => switchTab("collection"));
        const backFromResBtn = document.getElementById("btn-back-from-results");
        if (backFromResBtn) backFromResBtn.addEventListener("click", () => switchTab("collection"));

        // Search input
        const searchInput = document.getElementById("cafe-search-input");
        const searchClear = document.getElementById("cafe-search-clear");
        if (searchInput) {
            let debounceTimer = null;
            searchInput.addEventListener("input", (e) => {
                const val = e.target.value;
                state.searchQuery = val;
                if (searchClear) searchClear.style.display = val ? "inline-flex" : "none";
                clearTimeout(debounceTimer);
                debounceTimer = setTimeout(() => {
                    filterAndSortCollection();
                }, 150);
            });
        }
        if (searchClear) {
            searchClear.addEventListener("click", () => {
                if (searchInput) {
                    searchInput.value = "";
                    searchInput.focus();
                }
                searchClear.style.display = "none";
                state.searchQuery = "";
                filterAndSortCollection();
            });
        }

        // Quick filter chips
        const chips = document.querySelectorAll(".cafe-filter-chip");
        chips.forEach(chip => {
            chip.addEventListener("click", () => {
                chips.forEach(c => c.classList.remove("active"));
                chip.classList.add("active");
                state.activeFilter = chip.getAttribute("data-filter") || "all";
                filterAndSortCollection();
            });
        });

        // Sort select
        const sortSelect = document.getElementById("collection-sort-select");
        if (sortSelect) {
            sortSelect.addEventListener("change", (e) => {
                state.sortBy = e.target.value;
                filterAndSortCollection();
            });
        }
    }

    // Helper: Extract YouTube video ID
    function extractYouTubeId(url) {
        if (!url || typeof url !== "string") return null;
        const patterns = [
            /(?:v=|\/v\/|youtu\.be\/|\/embed\/|\/live\/)([a-zA-Z0-9_-]{11})/,
            /[?&]v=([a-zA-Z0-9_-]{11})/
        ];
        for (const p of patterns) {
            const match = url.match(p);
            if (match && match[1]) return match[1];
        }
        return null;
    }

    // Helper: Find game by ID in active state collections
    function findGameById(id) {
        if (!id) return null;
        const strId = String(id);
        if (state.collection && state.collection.length) {
            const found = state.collection.find(g => String(g.id) === strId);
            if (found) return found;
        }
        if (state.recommendations && state.recommendations.length) {
            const found = state.recommendations.find(g => String(g.id) === strId);
            if (found) return found;
        }
        return null;
    }

    // Open In-App Rules Video Modal
    function openRulesVideoModal(game) {
        if (!game) return;
        const modal = document.getElementById("rules-video-modal");
        const titleEl = document.getElementById("modal-game-title");
        const iframe = document.getElementById("rules-video-iframe");
        const videoContainer = document.getElementById("video-player-container");
        const fallbackNotice = document.getElementById("video-fallback-notice");
        const fallbackLink = document.getElementById("video-external-search-link");
        const teachTimeEl = document.getElementById("modal-teach-time");
        const compEl = document.getElementById("modal-complexity");
        const bggLink = document.getElementById("modal-bgg-link");

        if (!modal) return;

        if (titleEl) titleEl.textContent = game.name || "Game Rules";

        const teach = game.teach_time || estimateTeachTime(game.complexity);
        if (teachTimeEl) teachTimeEl.textContent = `⏱️ ${teach}`;
        if (compEl) {
            const comp = game.complexity ? `${parseFloat(game.complexity).toFixed(1)} / 5` : "Accessible";
            compEl.textContent = `⚙️ ${comp}`;
        }
        if (bggLink) {
            bggLink.href = game.id
                ? `https://boardgamegeek.com/boardgame/${game.id}`
                : `https://boardgamegeek.com/geeksearch.php?action=search&objecttype=boardgame&q=${encodeURIComponent(game.name)}`;
        }

        const ytId = game.rules_video_id || extractYouTubeId(game.rules_video_url);

        if (ytId && iframe && videoContainer && fallbackNotice) {
            iframe.src = `https://www.youtube-nocookie.com/embed/${encodeURIComponent(ytId)}?autoplay=1&rel=0`;
            videoContainer.style.display = "block";
            fallbackNotice.style.display = "none";
        } else {
            if (iframe) iframe.src = "";
            if (videoContainer) videoContainer.style.display = "none";
            if (fallbackNotice) fallbackNotice.style.display = "block";
            if (fallbackLink) {
                fallbackLink.href = `https://www.youtube.com/results?search_query=${encodeURIComponent((game.name || "") + " board game how to play rules")}`;
            }
        }

        modal.style.display = "flex";
        document.body.style.overflow = "hidden";

        const closeBtn = document.getElementById("btn-close-video-modal");
        if (closeBtn) closeBtn.focus();
    }

    // Close Rules Video Modal
    function closeRulesVideoModal() {
        const modal = document.getElementById("rules-video-modal");
        const iframe = document.getElementById("rules-video-iframe");
        if (modal) modal.style.display = "none";
        if (iframe) {
            iframe.src = "about:blank";
            iframe.removeAttribute("src");
        }
        document.body.style.overflow = "";
    }

    // Set up Video Modal Controls & Global Click Delegation
    function setupVideoModalControls() {
        const closeBtn = document.getElementById("btn-close-video-modal");
        const modal = document.getElementById("rules-video-modal");

        if (closeBtn) {
            closeBtn.addEventListener("click", closeRulesVideoModal);
        }

        if (modal) {
            modal.addEventListener("click", (e) => {
                if (e.target === modal) {
                    closeRulesVideoModal();
                }
            });
        }

        document.addEventListener("keydown", (e) => {
            if (e.key === "Escape") {
                closeRulesVideoModal();
            }
        });

        // Click delegation for all 🎬 Watch Rules buttons
        document.addEventListener("click", (e) => {
            const btn = e.target.closest(".btn-watch-rules");
            if (btn) {
                e.preventDefault();
                const gameId = btn.getAttribute("data-game-id");
                const game = findGameById(gameId);
                if (game) {
                    openRulesVideoModal(game);
                }
            }
        });
    }

    // ── Table Voting Integration (Milestone C7) ──
    async function startTableVote() {
        if (!state.recommendations || state.recommendations.length === 0) {
            alert("Please generate recommendations first to start a table vote!");
            return;
        }

        const topCandidates = state.recommendations.slice(0, 4).map(r => ({
            id: String(r.id),
            name: r.name,
            thumbnail: r.thumbnail || "",
            rating: r.rating || 0,
            complexity: r.complexity || 0,
            playing_time: r.playing_time || 0,
            shelf_location: r.shelf_location || ""
        }));

        const cafeName = (state.venueMeta && state.venueMeta.name) 
            ? state.venueMeta.name 
            : (state.cafeId ? state.cafeId.replace(/-/g, " ").replace(/\b\w/g, l => l.toUpperCase()) : "Cafe");

        const payload = {
            cafe_id: state.cafeId || "demo-cafe",
            cafe_name: cafeName,
            table: state.table || "1",
            candidates: topCandidates,
            duration_hours: 3.0,
            creator_name: `Table ${state.table || "1"}`
        };

        const modal = document.getElementById("cafe-table-vote-modal");
        const modalTitle = document.getElementById("vote-modal-title");
        const qrImg = document.getElementById("vote-modal-qr-img");
        const extLink = document.getElementById("btn-vote-open-external");
        const ballotSection = document.getElementById("vote-ballot-section");
        const consensusSection = document.getElementById("vote-consensus-section");
        const nameInput = document.getElementById("vote-voter-name-input");

        if (modalTitle) modalTitle.textContent = `${cafeName} - Table ${state.table} Vote`;
        if (modal) modal.style.display = "flex";
        if (ballotSection) ballotSection.style.display = "flex";
        if (consensusSection) consensusSection.style.display = "none";

        try {
            let resp = await window.fetchApi("/cafe/vote/start", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            // Fallback to /session if /cafe/vote/start fails or is 404
            if (!resp || !resp.ok) {
                resp = await window.fetchApi("/session", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        group_name: `${cafeName} - Table ${state.table}`,
                        creator_id: `cafe_${state.cafeId}_table_${state.table}`,
                        creator_name: `Table ${state.table}`,
                        candidates: topCandidates,
                        duration_hours: 3.0
                    })
                });
            }

            if (!resp || !resp.ok) {
                throw new Error("Failed to create table voting session");
            }

            const session = await resp.json();
            state.activeVoteSession = session;
            state.userBallot = {};

            // Default ballot selections
            topCandidates.forEach((c, idx) => {
                state.userBallot[c.id] = idx === 0 ? "yes" : "neutral";
            });

            // Resolve voter name
            if (nameInput) {
                const savedName = localStorage.getItem("bgg_cafe_voter_name") || `Table ${state.table} Patron`;
                nameInput.value = savedName;
            }

            // Configure QR Code & Share URL
            const voteUrl = `${window.location.origin}/vote/?session_id=${session.session_id}&cafe=${encodeURIComponent(state.cafeId)}&table=${encodeURIComponent(state.table)}`;
            if (qrImg) {
                qrImg.src = `https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=${encodeURIComponent(voteUrl)}`;
            }
            if (extLink) {
                extLink.href = voteUrl;
            }

            renderBallotCandidates(topCandidates);

        } catch (err) {
            console.error("Error creating table vote session:", err);
            // Fallback mock session for offline/mock test environments
            const mockSessId = "mock" + Math.random().toString(36).substring(2, 6);
            const fallbackSession = {
                session_id: mockSessId,
                group_name: `${cafeName} - Table ${state.table}`,
                candidates: topCandidates,
                votes: {},
                consensus: {
                    total_voters: 0,
                    winner: topCandidates[0],
                    rankings: topCandidates.map((c, i) => ({
                        candidate: c,
                        score: 0,
                        yes_count: 0,
                        neutral_count: 0,
                        veto_count: 0,
                        is_vetoed: false,
                        original_rank: i
                    })),
                    vetoed_games: []
                }
            };
            state.activeVoteSession = fallbackSession;
            state.userBallot = {};
            topCandidates.forEach((c, idx) => {
                state.userBallot[c.id] = idx === 0 ? "yes" : "neutral";
            });
            const voteUrl = `${window.location.origin}/vote/?session_id=${mockSessId}&cafe=${encodeURIComponent(state.cafeId)}&table=${encodeURIComponent(state.table)}`;
            if (qrImg) qrImg.src = `https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=${encodeURIComponent(voteUrl)}`;
            if (extLink) extLink.href = voteUrl;
            renderBallotCandidates(topCandidates);
        }
    }

    function renderBallotCandidates(candidates) {
        const list = document.getElementById("vote-candidates-list");
        if (!list) return;
        const escape = window.escapeHTML || (s => s);

        let html = "";
        candidates.forEach(cand => {
            const thumb = cand.thumbnail || "https://cf.geekdo-images.com/images/placeholder_thumb.png";
            const currentChoice = state.userBallot[cand.id] || "neutral";
            const shelf = (cand.shelf_location || "").trim();

            html += `
                <div class="vote-candidate-row" data-candidate-id="${escape(cand.id)}">
                    <div class="vote-cand-info">
                        <img class="vote-cand-thumb" src="${thumb}" alt="${escape(cand.name)}" onerror="this.onerror=null; this.src='https://cf.geekdo-images.com/images/placeholder_thumb.png';">
                        <div class="vote-cand-text">
                            <div class="vote-cand-name">${escape(cand.name)}</div>
                            <div class="vote-cand-sub">
                                ${shelf ? `📍 ${escape(shelf)} • ` : ""}⚙️ ${cand.complexity ? cand.complexity : '2.0'} / 5
                            </div>
                        </div>
                    </div>
                    <div class="vote-choice-group">
                        <button type="button" class="vote-pill-choice yes ${currentChoice === 'yes' ? 'active' : ''}" data-cand-id="${escape(cand.id)}" data-choice="yes" title="Love it (+2)">👍 +2</button>
                        <button type="button" class="vote-pill-choice neutral ${currentChoice === 'neutral' ? 'active' : ''}" data-cand-id="${escape(cand.id)}" data-choice="neutral" title="Okay (+1)">😐 +1</button>
                        <button type="button" class="vote-pill-choice veto ${currentChoice === 'veto' ? 'active' : ''}" data-cand-id="${escape(cand.id)}" data-choice="veto" title="Veto (Disqualify)">❌ Veto</button>
                    </div>
                </div>
            `;
        });

        list.innerHTML = html;

        list.querySelectorAll(".vote-pill-choice").forEach(btn => {
            btn.addEventListener("click", () => {
                const candId = btn.getAttribute("data-cand-id");
                const choice = btn.getAttribute("data-choice");
                state.userBallot[candId] = choice;

                const row = btn.closest(".vote-candidate-row");
                if (row) {
                    row.querySelectorAll(".vote-pill-choice").forEach(p => p.classList.remove("active"));
                    btn.classList.add("active");
                }
            });
        });
    }

    async function submitTableVoteBallot() {
        if (!state.activeVoteSession) return;
        const sessId = state.activeVoteSession.session_id;
        const nameInput = document.getElementById("vote-voter-name-input");
        const voterName = (nameInput && nameInput.value.trim()) ? nameInput.value.trim() : `Table ${state.table || "1"} Patron`;
        localStorage.setItem("bgg_cafe_voter_name", voterName);

        const submitBtn = document.getElementById("btn-submit-table-vote");
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = "⏳ Submitting Ballot...";
        }

        try {
            let resp = await window.fetchApi("/session/vote", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    session_id: sessId,
                    participant_name: voterName,
                    votes: state.userBallot
                })
            });

            if (resp && resp.ok) {
                const updated = await resp.json();
                state.activeVoteSession = updated;
                renderConsensusStandings(updated.consensus);
            } else {
                throw new Error("Vote submission failed");
            }
        } catch (err) {
            console.warn("Using local mock consensus for offline/test mode:", err);
            if (!state.activeVoteSession.votes) state.activeVoteSession.votes = {};
            state.activeVoteSession.votes[voterName] = state.userBallot;
            
            const candidates = state.activeVoteSession.candidates || [];
            const rankings = candidates.map((cand, idx) => {
                let score = 0;
                let yes_count = 0;
                let neutral_count = 0;
                let is_vetoed = false;

                Object.values(state.activeVoteSession.votes).forEach(ballot => {
                    const choice = ballot[cand.id];
                    if (choice === "yes") { score += 2; yes_count++; }
                    else if (choice === "neutral") { score += 1; neutral_count++; }
                    else if (choice === "veto") { score -= 99; is_vetoed = true; }
                });

                return {
                    candidate: cand,
                    score,
                    yes_count,
                    neutral_count,
                    is_vetoed,
                    original_rank: idx
                };
            });

            rankings.sort((a, b) => {
                if (a.is_vetoed !== b.is_vetoed) return a.is_vetoed ? 1 : -1;
                if (b.score !== a.score) return b.score - a.score;
                return a.original_rank - b.original_rank;
            });

            const consensus = {
                total_voters: Object.keys(state.activeVoteSession.votes).length,
                winner: rankings.length && !rankings[0].is_vetoed ? rankings[0].candidate : null,
                rankings,
                vetoed_games: rankings.filter(r => r.is_vetoed).map(r => r.candidate.id)
            };
            state.activeVoteSession.consensus = consensus;
            renderConsensusStandings(consensus);
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = "🗳️ Cast My Table Ballot";
            }
        }
    }

    function renderConsensusStandings(consensus) {
        const ballotSection = document.getElementById("vote-ballot-section");
        const consensusSection = document.getElementById("vote-consensus-section");
        const winnerBanner = document.getElementById("vote-winner-banner");
        const winnerTitle = document.getElementById("vote-winner-title");
        const tallyCount = document.getElementById("vote-tally-count");
        const rankingsList = document.getElementById("vote-rankings-list");

        if (ballotSection) ballotSection.style.display = "none";
        if (consensusSection) consensusSection.style.display = "flex";

        if (tallyCount) tallyCount.textContent = consensus ? consensus.total_voters : 0;

        if (winnerBanner && winnerTitle) {
            if (consensus && consensus.winner) {
                winnerBanner.style.display = "flex";
                winnerTitle.textContent = consensus.winner.name;
            } else {
                winnerBanner.style.display = "none";
            }
        }

        if (rankingsList && consensus && consensus.rankings) {
            const escape = window.escapeHTML || (s => s);
            let html = "";
            consensus.rankings.forEach((item, idx) => {
                const cand = item.candidate;
                const isVetoed = item.is_vetoed;
                const scoreLabel = isVetoed ? "VETOED" : `${item.score} pts`;

                html += `
                    <div class="vote-ranking-item ${isVetoed ? 'is-vetoed' : ''}">
                        <div class="ranking-left">
                            <span class="ranking-rank">#${idx + 1}</span>
                            <span class="ranking-name">${escape(cand.name)}</span>
                        </div>
                        <span class="ranking-score-badge ${isVetoed ? 'vetoed' : ''}">${scoreLabel}</span>
                    </div>
                `;
            });
            rankingsList.innerHTML = html;
        }
    }

    function setupTableVotingControls() {
        const startBtn = document.getElementById("btn-start-table-vote");
        const launchBtn = document.getElementById("btn-launch-table-vote");
        const closeBtn = document.getElementById("btn-close-vote-modal");
        const modal = document.getElementById("cafe-table-vote-modal");
        const submitBtn = document.getElementById("btn-submit-table-vote");
        const revoteBtn = document.getElementById("btn-revote-trigger");
        const refreshBtn = document.getElementById("btn-refresh-tally");
        const copyBtn = document.getElementById("btn-vote-copy-link");
        const shareBtn = document.getElementById("btn-vote-share-link");

        if (startBtn) startBtn.addEventListener("click", startTableVote);
        if (launchBtn) launchBtn.addEventListener("click", startTableVote);

        if (closeBtn && modal) {
            closeBtn.addEventListener("click", () => {
                modal.style.display = "none";
            });
        }

        if (modal) {
            modal.addEventListener("click", (e) => {
                if (e.target === modal) modal.style.display = "none";
            });
        }

        if (submitBtn) {
            submitBtn.addEventListener("click", submitTableVoteBallot);
        }

        if (revoteBtn) {
            revoteBtn.addEventListener("click", () => {
                const ballotSection = document.getElementById("vote-ballot-section");
                const consensusSection = document.getElementById("vote-consensus-section");
                if (ballotSection) ballotSection.style.display = "flex";
                if (consensusSection) consensusSection.style.display = "none";
            });
        }

        if (refreshBtn) {
            refreshBtn.addEventListener("click", async () => {
                if (!state.activeVoteSession) return;
                try {
                    const resp = await window.fetchApi(`/session?session_id=${state.activeVoteSession.session_id}`);
                    if (resp && resp.ok) {
                        const data = await resp.json();
                        state.activeVoteSession = data;
                        renderConsensusStandings(data.consensus);
                    }
                } catch (e) {
                    console.error("Failed to refresh session consensus:", e);
                }
            });
        }

        if (copyBtn) {
            copyBtn.addEventListener("click", () => {
                if (!state.activeVoteSession) return;
                const voteUrl = `${window.location.origin}/vote/?session_id=${state.activeVoteSession.session_id}&cafe=${encodeURIComponent(state.cafeId)}&table=${encodeURIComponent(state.table)}`;
                navigator.clipboard.writeText(voteUrl).then(() => {
                    const fb = document.getElementById("vote-copy-feedback");
                    if (fb) {
                        fb.style.display = "block";
                        setTimeout(() => { fb.style.display = "none"; }, 2500);
                    }
                }).catch(() => {
                    prompt("Copy this vote link:", voteUrl);
                });
            });
        }

        if (shareBtn) {
            shareBtn.addEventListener("click", () => {
                if (!state.activeVoteSession) return;
                const voteUrl = `${window.location.origin}/vote/?session_id=${state.activeVoteSession.session_id}&cafe=${encodeURIComponent(state.cafeId)}&table=${encodeURIComponent(state.table)}`;
                if (navigator.share) {
                    navigator.share({
                        title: state.activeVoteSession.group_name || "Table Board Game Vote",
                        text: `Vote on what board game to play at Table ${state.table}!`,
                        url: voteUrl
                    }).catch(() => {});
                } else if (copyBtn) {
                    copyBtn.click();
                }
            });
        }
    }

    // Export internal helpers for testing if module / test environment
    if (typeof window !== "undefined") {
        window.CafePortal = {
            state,
            parseVenueContext,
            loadVenueMetadata,
            loadCafeCollection,
            filterAndSortCollection,
            switchTab,
            estimateTeachTime,
            getDrinkPairing,
            fetchCafeRecommendations,
            renderCafeCards,
            extractYouTubeId,
            findGameById,
            openRulesVideoModal,
            closeRulesVideoModal,
            setupGatewayControls,
            setupCollectionControls,
            setupVideoModalControls,
            startTableVote,
            renderBallotCandidates,
            submitTableVoteBallot,
            renderConsensusStandings,
            setupTableVotingControls
        };
    }

    // Initialize when DOM is ready
    document.addEventListener("DOMContentLoaded", function () {
        const gatewayView = document.getElementById("cafe-gateway-view");
        const patronView = document.getElementById("cafe-patron-view");
        if (!gatewayView && !patronView && !document.getElementById("vibe-quiz-form")) return;

        const hasVenue = parseVenueContext();

        if (!hasVenue) {
            if (gatewayView) gatewayView.style.display = "block";
            if (patronView) patronView.style.display = "none";
            setupGatewayControls();
        } else {
            if (gatewayView) gatewayView.style.display = "none";
            if (patronView) patronView.style.display = "block";
            restoreQuizState();
            loadVenueMetadata();
            setupQuizControls();
            setupCollectionControls();
            setupVideoModalControls();
            setupTableVotingControls();
            loadCafeCollection();

            // Default view: Collection Browser!
            const urlParams = new URLSearchParams(window.location.search);
            if (urlParams.get("quiz") === "1" || urlParams.get("recommender") === "1") {
                switchTab("recommender");
            } else {
                switchTab("collection");
            }

            // If URL has auto=1, trigger recommendations
            if (urlParams.get("auto") === "1") {
                switchTab("recommender");
                fetchCafeRecommendations();
            }
        }
    });
})();

