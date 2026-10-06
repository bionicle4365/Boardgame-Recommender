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
        quiz: {
            playerCount: "4",
            duration: "medium",
            vibe: "casual_strategy",
            hobbyistUsers: ""
        },
        isLoading: false
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
        if (!cafeId) {
            cafeId = sessionStorage.getItem("cafe_patron_cafe_id") || "the-malt-and-meeple";
        }

        // 2. Extract table
        let table = urlParams.get("table");
        if (!table) {
            table = sessionStorage.getItem("cafe_patron_table") || "1";
        }

        state.cafeId = cafeId.trim().toLowerCase();
        state.table = table.trim();

        // Persist in session
        try {
            sessionStorage.setItem("cafe_patron_cafe_id", state.cafeId);
            sessionStorage.setItem("cafe_patron_table", state.table);
        } catch (e) {}
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
            tableBadge.textContent = `🪑 Table ${state.table}`;
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

        if (resTableNum) resTableNum.textContent = state.table;
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
            table: state.table
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

    // Render Game Cards
    function renderCafeCards(container, recs) {
        const escape = window.escapeHTML || (s => s ? String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])) : "");
        let html = "";

        recs.forEach((rec, idx) => {
            const thumb = rec.thumbnail || "https://cf.geekdo-images.com/images/placeholder_thumb.png";
            const bggUrl = rec.id ? `https://boardgamegeek.com/boardgame/${rec.id}` : `https://boardgamegeek.com/geeksearch.php?action=search&objecttype=boardgame&q=${encodeURIComponent(rec.name)}`;
            const videoUrl = `https://www.youtube.com/results?search_query=${encodeURIComponent(rec.name + " board game how to play rules")}`;

            // Prominent Shelf Location
            const shelf = rec.shelf_location || rec.shelf || `Shelf ${String.fromCharCode(65 + (idx % 5))}-${(idx % 4) + 1}`;
            
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

            // Sommelier Quote
            const reasonText = rec.reason || `Perfect for Table ${state.table}! High engagement with clean rules and satisfying decisions.`;

            // Drink Pairing
            const drinkTag = (state.venueMeta && state.venueMeta.drink_pairings_enabled !== false) 
                ? `<div class="drink-pairing-tag">${escape(getDrinkPairing(state.quiz.vibe))}</div>` 
                : "";

            html += `
                <div class="cafe-game-card" style="animation-delay: ${idx * 0.06}s;">
                    <div class="cafe-card-top">
                        <div class="cafe-card-thumb-wrap">
                            <img class="cafe-card-thumb" src="${thumb}" alt="${escape(rec.name)}" loading="lazy" onerror="this.onerror=null; this.src='https://cf.geekdo-images.com/images/placeholder_thumb.png';">
                        </div>
                        <div class="cafe-card-info">
                            <div class="cafe-card-title-row">
                                <a href="${bggUrl}" target="_blank" class="cafe-card-title">${escape(rec.name)}</a>
                                ${rec.year_published ? `<span class="cafe-card-year">(${rec.year_published})</span>` : ''}
                            </div>

                            <!-- Prominent Shelf Location & Teach Time -->
                            <div class="cafe-prominent-badges">
                                <span class="shelf-location-badge" title="Physical shelf location in cafe">
                                    📍 ${escape(shelf)}
                                </span>
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
                        </div>
                    </div>

                    <!-- AI Sommelier Guru Bubble -->
                    <div class="sommelier-quote-bubble">
                        <div class="sommelier-header">
                            <span>🍷 Cafe Guru Recommendation</span>
                        </div>
                        <p class="sommelier-quote-text">"${escape(reasonText)}"</p>
                    </div>

                    ${drinkTag}

                    <!-- Actions -->
                    <div class="cafe-card-actions">
                        <a href="${videoUrl}" target="_blank" class="btn-card-action primary">
                            🎬 Watch Rules (3-5m)
                        </a>
                        <a href="${bggUrl}" target="_blank" class="btn-card-action">
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

    // Export internal helpers for testing if module / test environment
    if (typeof window !== "undefined") {
        window.CafePortal = {
            state,
            parseVenueContext,
            loadVenueMetadata,
            estimateTeachTime,
            getDrinkPairing,
            fetchCafeRecommendations,
            renderCafeCards
        };
    }

    // Initialize when DOM is ready
    document.addEventListener("DOMContentLoaded", function () {
        // Only run on cafe patron portal
        if (!document.getElementById("vibe-quiz-form")) return;

        parseVenueContext();
        restoreQuizState();
        loadVenueMetadata();
        setupQuizControls();

        // If URL has auto=1, trigger automatically
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.get("auto") === "1") {
            fetchCafeRecommendations();
        }
    });
})();
