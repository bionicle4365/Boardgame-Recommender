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
        table: "",
        activeTab: "collection",
        collection: [],
        filteredCollection: [],
        recommendations: [],
        searchQuery: "",
        activeFilter: "all",
        sortBy: "name_asc",
        isCollectionLoading: false,
        pollSelectedIds: new Set(),
        pollSearchQuery: "",
        recommendedIds: new Set(),
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
        
        // 1. Extract cafe ID & table from path segments
        let cafeId = urlParams.get("cafe") || urlParams.get("cafe_id") || urlParams.get("id");
        let tableFromPath = "";

        const pathParts = window.location.pathname.split("/").filter(Boolean);
        const cafeIdx = pathParts.indexOf("cafe");
        if (cafeIdx !== -1 && pathParts.length > cafeIdx + 1) {
            const seg = pathParts[cafeIdx + 1];
            if (seg !== "index.html" && seg !== "manage" && seg !== "onboard") {
                if (!cafeId) cafeId = seg;
                
                // Check if table is in the path: e.g. /cafe/malt-and-meeple/5 or /cafe/malt-and-meeple/table/5
                if (pathParts.length > cafeIdx + 2) {
                    if (pathParts[cafeIdx + 2] === "table" && pathParts.length > cafeIdx + 3) {
                        tableFromPath = pathParts[cafeIdx + 3];
                    } else if (pathParts[cafeIdx + 2] !== "table" && pathParts[cafeIdx + 2] !== "index.html") {
                        tableFromPath = pathParts[cafeIdx + 2];
                    }
                    if (tableFromPath) {
                        try { tableFromPath = decodeURIComponent(tableFromPath); } catch (e) {}
                    }
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
        let table = tableFromPath || urlParams.get("table") || urlParams.get("t");

        state.cafeId = cafeId.trim().toLowerCase();
        state.table = table ? table.trim() : "";

        // Persist in session
        try {
            sessionStorage.setItem("cafe_patron_cafe_id", state.cafeId);
            if (state.table) {
                sessionStorage.setItem("cafe_patron_table", state.table);
            } else {
                sessionStorage.removeItem("cafe_patron_table");
            }
        } catch (e) {}

        // Ensure browser address bar displays clean RESTful path: /cafe/:cafeId/:table or /cafe/:cafeId
        if (window.history && window.history.replaceState) {
            try {
                const targetPath = state.table 
                    ? `/cafe/${encodeURIComponent(state.cafeId)}/${encodeURIComponent(state.table)}`
                    : `/cafe/${encodeURIComponent(state.cafeId)}`;
                const remainingParams = new URLSearchParams(window.location.search);
                remainingParams.delete("cafe");
                remainingParams.delete("cafe_id");
                remainingParams.delete("id");
                remainingParams.delete("table");
                remainingParams.delete("t");
                const qs = remainingParams.toString();
                const targetUrl = targetPath + (qs ? `?${qs}` : "");

                if (window.location.pathname !== targetPath || (window.location.search && !qs)) {
                    window.history.replaceState(null, document.title, targetUrl);
                }
            } catch (e) {}
        }

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

    // Apply venue branding to DOM and components
    function applyVenueBranding(data) {
        if (!data) return;
        state.venueMeta = data;
        const titleEl = document.getElementById("venue-name-title");
        const taglineEl = document.getElementById("venue-tagline");
        const avatarEl = document.getElementById("venue-avatar-wrap");
        const wifiChip = document.getElementById("header-wifi-chip");
        const wifiSsid = document.getElementById("wifi-ssid-label");
        const wifiPass = document.getElementById("wifi-pass-label");
        const menuBtn = document.getElementById("header-menu-btn");

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

        // Digital Menu Button (Milestone C10)
        if (menuBtn) {
            if (data.menu_url && data.menu_url.trim()) {
                menuBtn.href = data.menu_url.trim();
                menuBtn.style.display = "inline-flex";
            } else {
                menuBtn.style.display = "none";
            }
        }

        // Venue Event Announcement Banner (Milestone C10)
        if (typeof window !== "undefined" && window.AnnouncementBanner) {
            if (data.announcement_banner && data.announcement_banner.trim()) {
                const bannerId = `cafe_${state.cafeId}_${data.announcement_banner.length}`;
                window.AnnouncementBanner.show({
                    id: bannerId,
                    text: data.announcement_banner.trim(),
                    type: "event",
                    icon: "🎉",
                    dismissible: true
                });
            } else {
                window.AnnouncementBanner.hide();
            }
        }

        // Render Guru Picks Carousel
        renderGuruPicks();
    }

    // Fetch Venue Metadata
    async function loadVenueMetadata() {
        if (!state.cafeId) return;

        const tableBadge = document.getElementById("header-table-badge");
        const ctaTableNum = document.getElementById("cta-table-num");
        const ctaSub = document.getElementById("recommender-cta-sub");

        if (state.table) {
            if (tableBadge) {
                tableBadge.textContent = /^\d+$/.test(state.table) ? `🪑 Table ${state.table}` : `🪑 ${state.table}`;
                tableBadge.style.display = "inline-flex";
            }
            if (ctaTableNum) ctaTableNum.textContent = state.table;
            if (ctaSub) {
                ctaSub.innerHTML = `Answer 3 quick taps to find recommendations tailored for Table <span class="cta-table-num">${window.escapeHTML ? window.escapeHTML(state.table) : state.table}</span>.`;
            }
        } else {
            if (tableBadge) {
                tableBadge.style.display = "none";
            }
            if (ctaSub) {
                ctaSub.textContent = "Answer 3 quick taps to find tailored game recommendations for your visit.";
            }
        }

        try {
            const resp = await window.fetchApi(`/cafe/meta?cafe_id=${encodeURIComponent(state.cafeId)}`);
            if (resp && resp.ok) {
                const data = await resp.json();
                applyVenueBranding(data);
                return;
            }
        } catch (err) {
            console.warn("Failed fetching venue metadata, using fallback:", err);
        }

        // Default fallback branding if venue not found
        const fallbackMeta = {
            cafe_id: state.cafeId,
            name: "The Malt & Meeple Cafe",
            tagline: "Craft brews & 500+ tabletop games on tap.",
            wifi_ssid: "MaltMeeple-Guest",
            wifi_password: "rollforinitiative",
            drink_pairings_enabled: true,
            bgg_username: "maltandmeeple",
            menu_url: "",
            announcement_banner: "",
            featured_game_ids: []
        };
        applyVenueBranding(fallbackMeta);
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
        const tableBadge = document.getElementById("header-table-badge");
        if (switchTableBtn) {
            switchTableBtn.textContent = state.table ? "Wrong table? Switch" : "Select table / room";
            switchTableBtn.addEventListener("click", () => {
                const newTable = prompt("Enter your table number or room name (e.g. 5 or The Vault):", state.table || "");
                if (newTable && newTable.trim()) {
                    state.table = newTable.trim();
                    try {
                        sessionStorage.setItem("cafe_patron_table", state.table);
                    } catch (e) {}
                    if (tableBadge) {
                        tableBadge.style.display = "inline-flex";
                        tableBadge.textContent = /^\d+$/.test(state.table) ? `🪑 Table ${state.table}` : `🪑 ${state.table}`;
                    }
                    switchTableBtn.textContent = "Wrong table? Switch";
                    const formattedLabel = /^\d+$/.test(state.table) ? `Table ${state.table}` : state.table;
                    const resTitle = document.getElementById("results-table-num");
                    if (resTitle) resTitle.textContent = formattedLabel;
                    const ctaTableEl = document.getElementById("cta-table-num");
                    if (ctaTableEl) ctaTableEl.textContent = formattedLabel;
                    const voteCtaTableEl = document.getElementById("vote-cta-table-num");
                    if (voteCtaTableEl) voteCtaTableEl.textContent = formattedLabel;
                    const ctaSub = document.getElementById("recommender-cta-sub");
                    if (ctaSub) {
                        ctaSub.innerHTML = `Answer 3 quick taps to find recommendations tailored for <span class="cta-table-num" id="cta-table-num">${formattedLabel}</span>.`;
                    }
                    state.activeVoteSession = null;
                    checkActiveTableVoteSession();
                }
            });
        }
        if (tableBadge) {
            tableBadge.addEventListener("click", () => {
                if (switchTableBtn) switchTableBtn.click();
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
            await checkActiveTableVoteSession();
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
            checkActiveTableVoteSession();
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
            renderGuruPicks();
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

    // Footprint Heuristic: Small Table Friendly (Milestone C10)
    function isSmallTableFriendly(g) {
        if (!g) return false;
        const cats = Array.isArray(g.categories) ? g.categories.map(c => String(c).toLowerCase()) : (g.categories ? [String(g.categories).toLowerCase()] : []);
        const mechs = Array.isArray(g.mechanics) ? g.mechanics.map(m => String(m).toLowerCase()) : (g.mechanics ? [String(g.mechanics).toLowerCase()] : []);
        const name = (g.name || "").toLowerCase();

        // Keywords in category or mechanics indicating compact tabletop footprint
        const compactKeywords = [
            "card game", "dice", "microgame", "pocket", "travel", "deduction", 
            "word game", "party game", "bluffing", "trivia", "take that", "hand management"
        ];

        const matchesKeyword = compactKeywords.some(kw => 
            cats.some(c => c.includes(kw)) || mechs.some(m => m.includes(kw))
        );

        // Specific notable small table titles
        const smallTitles = [
            "hive", "jaipur", "love letter", "sea salt & paper", "taco cat goat cheese pizza",
            "cockroach poker", "spot it", "coup", "hanabi", "scout", "skull", 
            "deep sea adventure", "the mind", "fox in the forest", "star realms", 
            "regicide", "similo", "bandido", "saboteur", "port royal", "point salad", 
            "exploding kittens", "sushi go", "splendor duel", "targi", "air, land, & sea"
        ];
        const matchesTitle = smallTitles.some(st => name.includes(st));

        // Footprint heuristic: small table games should not have sprawling playtime (>90m) or high weight (>3.6)
        const playtime = g.playing_time || g.max_playtime || 0;
        const complexity = g.complexity || 0;
        const isSprawling = (playtime > 90) || (complexity > 3.6);

        if (isSprawling) return false;

        return matchesKeyword || matchesTitle;
    }

    // "Featured Guru Picks" Spotlight Carousel (Milestone C10)
    function renderGuruPicks() {
        const section = document.getElementById("cafe-guru-picks-section");
        const carousel = document.getElementById("guru-picks-carousel");
        const countBadge = document.getElementById("guru-picks-count-badge");
        if (!section || !carousel) return;

        const featuredIds = (state.venueMeta && state.venueMeta.featured_game_ids) 
            ? state.venueMeta.featured_game_ids 
            : [];

        if (!Array.isArray(featuredIds) || featuredIds.length === 0) {
            section.style.display = "none";
            return;
        }

        const allGamesMap = new Map();
        (state.collection || []).forEach(g => allGamesMap.set(String(g.id), g));
        (state.recommendations || []).forEach(g => {
            if (!allGamesMap.has(String(g.id))) allGamesMap.set(String(g.id), g);
        });

        const featuredGames = [];
        featuredIds.forEach(id => {
            const found = allGamesMap.get(String(id));
            if (found) {
                featuredGames.push(found);
            }
        });

        if (featuredGames.length === 0) {
            section.style.display = "none";
            return;
        }

        if (countBadge) {
            countBadge.textContent = `${featuredGames.length} Featured`;
        }

        const escape = window.escapeHTML || (s => s);
        let html = "";
        featuredGames.forEach(g => {
            const thumb = g.thumbnail || "https://cf.geekdo-images.com/images/placeholder_thumb.png";
            const shelf = (g.shelf_location || g.shelf || "").trim();
            const rating = g.rating ? Number(g.rating).toFixed(1) : "—";
            const complexity = g.complexity ? Number(g.complexity).toFixed(1) : "2.0";
            const playtime = g.playing_time ? `${g.playing_time}m` : "30m";
            const bggUrl = `https://boardgamegeek.com/boardgame/${encodeURIComponent(g.id)}`;

            html += `
                <div class="guru-pick-card" data-game-id="${escape(String(g.id))}">
                    <span class="guru-pick-badge">⭐ House Pick</span>
                    <div class="guru-pick-thumb-wrap">
                        <img class="guru-pick-thumb" src="${thumb}" alt="${escape(g.name)}" onerror="this.onerror=null; this.src='https://cf.geekdo-images.com/images/placeholder_thumb.png';">
                    </div>
                    <div class="guru-pick-name" title="${escape(g.name)}">${escape(g.name)}</div>
                    <div class="guru-pick-meta-row">
                        ${shelf ? `<span class="guru-pick-shelf">📍 ${escape(shelf)}</span>` : ""}
                        <span>★ ${rating}</span>
                        <span>⚙️ ${complexity} / 5</span>
                        <span>⏱️ ${playtime}</span>
                    </div>
                    <div class="guru-pick-actions">
                        <button type="button" class="btn-guru-pick-action primary btn-watch-rules" data-game-id="${escape(String(g.id))}">
                            ▶ Watch Rules
                        </button>
                        <a href="${bggUrl}" target="_blank" rel="noopener" class="btn-guru-pick-action" title="View on BoardGameGeek">
                            BGG ↗
                        </a>
                    </div>
                </div>
            `;
        });

        carousel.innerHTML = html;
        section.style.display = "block";

        setupVideoModalControls();
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
        if (f === "small_table") {
            list = list.filter(g => isSmallTableFriendly(g));
        } else if (f === "2p") {
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

    // ── Table Voting & Poll Creation Integration (Milestone C7 Expansion) ──
    async function openPollCreationModal() {
        const modal = document.getElementById("cafe-table-vote-modal");
        const modalTitle = document.getElementById("vote-modal-title");
        const setupSection = document.getElementById("vote-setup-section");
        const activeSection = document.getElementById("vote-active-section");

        const cafeName = (state.venueMeta && state.venueMeta.name) 
            ? state.venueMeta.name 
            : (state.cafeId ? state.cafeId.replace(/-/g, " ").replace(/\b\w/g, l => l.toUpperCase()) : "Cafe");

        if (modalTitle) {
            modalTitle.textContent = state.table 
                ? `${cafeName} - ${/^\d+$/.test(state.table) ? 'Table ' + state.table : state.table} Vote`
                : `${cafeName} - Table Vote`;
        }
        if (modal) modal.style.display = "flex";
        if (setupSection) setupSection.style.display = "flex";
        if (activeSection) activeSection.style.display = "none";

        // Load collection if needed
        if ((!state.collection || state.collection.length === 0) && (!state.recommendations || state.recommendations.length === 0)) {
            await loadCafeCollection();
        }

        // Determine recommended candidate IDs
        let recIds = [];
        if (state.recommendations && state.recommendations.length > 0) {
            recIds = state.recommendations.slice(0, 4).map(r => String(r.id));
        } else if (state.collection && state.collection.length > 0) {
            // Pick top 4 by rating as default recommendations
            const sorted = [...state.collection].sort((a, b) => (b.rating || 0) - (a.rating || 0));
            recIds = sorted.slice(0, 4).map(r => String(r.id));
        }

        state.recommendedIds = new Set(recIds);
        // Pre-select recommended games
        state.pollSelectedIds = new Set(recIds);
        state.pollSearchQuery = "";

        const searchInp = document.getElementById("poll-search-input");
        if (searchInp) searchInp.value = "";
        const searchClear = document.getElementById("poll-search-clear");
        if (searchClear) searchClear.style.display = "none";
        const errEl = document.getElementById("poll-setup-error");
        if (errEl) errEl.style.display = "none";

        renderPollCandidatePicker();
    }

    function renderPollCandidatePicker() {
        const container = document.getElementById("poll-candidates-picker");
        const countChip = document.getElementById("poll-selected-count-chip");
        if (!container) return;

        if (countChip) {
            countChip.textContent = `${state.pollSelectedIds.size} selected`;
        }

        const query = (state.pollSearchQuery || "").trim().toLowerCase();
        const allGamesMap = new Map();
        (state.collection || []).forEach(g => allGamesMap.set(String(g.id), g));
        (state.recommendations || []).forEach(g => {
            if (!allGamesMap.has(String(g.id))) allGamesMap.set(String(g.id), g);
        });
        const games = Array.from(allGamesMap.values());
        const escape = window.escapeHTML || (s => s);

        // Filter games by search query
        let filtered = games.filter(g => {
            if (!query) return true;
            const name = (g.name || "").toLowerCase();
            const mechs = Array.isArray(g.mechanics) ? g.mechanics.join(" ").toLowerCase() : (g.mechanics || "").toLowerCase();
            const cats = Array.isArray(g.categories) ? g.categories.join(" ").toLowerCase() : (g.categories || "").toLowerCase();
            return name.includes(query) || mechs.includes(query) || cats.includes(query);
        });

        // Sort: Selected games moved to the top!
        filtered.sort((a, b) => {
            const aSel = state.pollSelectedIds.has(String(a.id)) ? 1 : 0;
            const bSel = state.pollSelectedIds.has(String(b.id)) ? 1 : 0;
            if (aSel !== bSel) return bSel - aSel; // Selected first

            const aRec = state.recommendedIds && state.recommendedIds.has(String(a.id)) ? 1 : 0;
            const bRec = state.recommendedIds && state.recommendedIds.has(String(b.id)) ? 1 : 0;
            if (aRec !== bRec) return bRec - aRec; // Recommended next

            return (a.name || "").localeCompare(b.name || "");
        });

        if (filtered.length === 0) {
            container.innerHTML = `
                <div style="text-align: center; padding: 24px; color: var(--text-muted); font-size: 0.9rem;">
                    No games found matching "${escape(query)}".
                </div>
            `;
            return;
        }

        let html = "";
        filtered.forEach(g => {
            const gid = String(g.id);
            const isSelected = state.pollSelectedIds.has(gid);
            const isRec = state.recommendedIds && state.recommendedIds.has(gid);
            const thumb = g.thumbnail || "https://cf.geekdo-images.com/images/placeholder_thumb.png";
            const shelf = (g.shelf_location || "").trim();

            html += `
                <div class="poll-candidate-item ${isSelected ? 'is-selected' : ''}" data-game-id="${escape(gid)}">
                    <input type="checkbox" class="poll-cand-checkbox" data-game-id="${escape(gid)}" ${isSelected ? 'checked' : ''} aria-label="Select ${escape(g.name)}">
                    <img class="poll-cand-thumb" src="${thumb}" alt="${escape(g.name)}" onerror="this.onerror=null; this.src='https://cf.geekdo-images.com/images/placeholder_thumb.png';">
                    <div class="poll-cand-info">
                        <div class="poll-cand-title">${escape(g.name)}</div>
                        <div class="poll-cand-meta">
                            ${isRec ? '<span class="poll-rec-badge">⭐ Recommended</span>' : ''}
                            ${shelf ? `<span>📍 ${escape(shelf)}</span> • ` : ""}
                            <span>★ ${(g.rating ? Number(g.rating).toFixed(1) : '—')}</span> • 
                            <span>⚙️ ${(g.complexity ? Number(g.complexity).toFixed(1) : '2.0')}</span> • 
                            <span>⏱️ ${g.playing_time ? g.playing_time + 'm' : '30m'}</span>
                        </div>
                    </div>
                </div>
            `;
        });

        container.innerHTML = html;

        // Bind clicks on rows and checkboxes
        container.querySelectorAll(".poll-candidate-item").forEach(item => {
            item.addEventListener("click", (e) => {
                const gid = item.getAttribute("data-game-id");
                const checkbox = item.querySelector(".poll-cand-checkbox");

                if (state.pollSelectedIds.has(gid)) {
                    state.pollSelectedIds.delete(gid);
                    if (checkbox) checkbox.checked = false;
                    item.classList.remove("is-selected");
                } else {
                    state.pollSelectedIds.add(gid);
                    if (checkbox) checkbox.checked = true;
                    item.classList.add("is-selected");
                }

                if (countChip) {
                    countChip.textContent = `${state.pollSelectedIds.size} selected`;
                }

                const errEl = document.getElementById("poll-setup-error");
                if (errEl && state.pollSelectedIds.size >= 2) {
                    errEl.style.display = "none";
                }

                if (e.target !== checkbox) {
                    renderPollCandidatePicker();
                }
            });
        });

        container.querySelectorAll(".poll-cand-checkbox").forEach(cb => {
            cb.addEventListener("change", (e) => {
                e.stopPropagation();
                const gid = cb.getAttribute("data-game-id");
                if (cb.checked) {
                    state.pollSelectedIds.add(gid);
                } else {
                    state.pollSelectedIds.delete(gid);
                }
                renderPollCandidatePicker();
            });
        });
    }

    async function launchConfiguredTablePoll() {
        const errEl = document.getElementById("poll-setup-error");
        if (state.pollSelectedIds.size < 2) {
            if (errEl) {
                errEl.textContent = "⚠️ Please select at least 2 games to start a table vote.";
                errEl.style.display = "block";
            }
            return;
        }
        if (errEl) errEl.style.display = "none";

        // Prompt for table if not set
        if (!state.table) {
            const entered = prompt("Enter your table number or room name (e.g. 5 or The Vault):", "1");
            state.table = (entered && entered.trim()) ? entered.trim() : "1";
            try { sessionStorage.setItem("cafe_patron_table", state.table); } catch (e) {}
            const tableBadge = document.getElementById("header-table-badge");
            if (tableBadge) {
                tableBadge.style.display = "inline-flex";
                tableBadge.textContent = /^\d+$/.test(state.table) ? `🪑 Table ${state.table}` : `🪑 ${state.table}`;
            }
        }

        const launchBtn = document.getElementById("btn-launch-configured-poll");
        if (launchBtn) {
            launchBtn.disabled = true;
            launchBtn.textContent = "⏳ Creating Table Poll...";
        }

        try {
            // Find selected game objects
            const selectedCandidates = [];
            const allGamesMap = new Map();
            (state.collection || []).forEach(g => allGamesMap.set(String(g.id), g));
            (state.recommendations || []).forEach(g => {
                if (!allGamesMap.has(String(g.id))) allGamesMap.set(String(g.id), g);
            });
            state.pollSelectedIds.forEach(id => {
                const found = allGamesMap.get(String(id));
                if (found) {
                    selectedCandidates.push({
                        id: String(found.id),
                        name: found.name,
                        thumbnail: found.thumbnail || "",
                        rating: found.rating || 0,
                        complexity: found.complexity || 0,
                        playing_time: found.playing_time || 0,
                        shelf_location: found.shelf_location || ""
                    });
                }
            });

            const cafeName = (state.venueMeta && state.venueMeta.name) 
                ? state.venueMeta.name 
                : (state.cafeId ? state.cafeId.replace(/-/g, " ").replace(/\b\w/g, l => l.toUpperCase()) : "Cafe");

            const tableName = /^\d+$/.test(state.table) ? `Table ${state.table}` : state.table;
            const payload = {
                cafe_id: state.cafeId || "demo-cafe",
                cafe_name: cafeName,
                table: state.table || "1",
                candidates: selectedCandidates,
                duration_hours: 0.25,
                creator_name: tableName
            };

            const qrImg = document.getElementById("vote-modal-qr-img");
            const extLink = document.getElementById("btn-vote-open-external");
            const nameInput = document.getElementById("vote-voter-name-input");

            let session = null;
            try {
                let resp = await window.fetchApi("/cafe/vote/start", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });
                if (!resp || !resp.ok) {
                    resp = await window.fetchApi("/session", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            group_name: `${cafeName} - ${tableName}`,
                            creator_id: `cafe_${state.cafeId}_table_${state.table}`,
                            creator_name: tableName,
                            candidates: selectedCandidates,
                            duration_hours: 0.25
                        })
                    });
                }
                if (resp && resp.ok) {
                    session = await resp.json();
                }
            } catch (netErr) {
                console.warn("API poll creation failed, falling back to mock session:", netErr);
            }

            if (!session) {
                // Mock session fallback
                const mockSessId = "mock" + Math.random().toString(36).substring(2, 6);
                const now = new Date();
                const closesAt = new Date(now.getTime() + 15 * 60 * 1000).toISOString();
                session = {
                    session_id: mockSessId,
                    group_name: `${cafeName} - ${tableName}`,
                    candidates: selectedCandidates,
                    created_at: now.toISOString(),
                    closes_at: closesAt,
                    duration_hours: 0.25,
                    votes: {},
                    consensus: {
                        total_voters: 0,
                        winner: selectedCandidates[0],
                        rankings: selectedCandidates.map((c, i) => ({
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
            }

            state.activeVoteSession = session;
            state.userBallot = {};
            selectedCandidates.forEach((c, idx) => {
                state.userBallot[c.id] = idx === 0 ? "yes" : "neutral";
            });

            if (nameInput) {
                const savedName = localStorage.getItem("bgg_cafe_voter_name") || `${tableName} Patron`;
                nameInput.value = savedName;
            }

            const voteUrl = `${window.location.origin}/vote/?session_id=${session.session_id}&cafe=${encodeURIComponent(state.cafeId)}&table=${encodeURIComponent(state.table)}`;
            if (qrImg) {
                qrImg.src = `https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=${encodeURIComponent(voteUrl)}`;
            }
            if (extLink) {
                extLink.href = voteUrl;
            }

            // Transition modal from setup view to active ballot view
            const setupSection = document.getElementById("vote-setup-section");
            const activeSection = document.getElementById("vote-active-section");
            if (setupSection) setupSection.style.display = "none";
            if (activeSection) activeSection.style.display = "block";

            renderBallotCandidates(selectedCandidates);

            try {
                localStorage.setItem(`cafe_active_vote_${state.cafeId}_${state.table}`, JSON.stringify(session));
            } catch (e) {}
            scheduleVoteTtlTimer(session);
            updateTableVoteUI();

        } finally {
            if (launchBtn) {
                launchBtn.disabled = false;
                launchBtn.textContent = "🚀 Launch 15-Min Table Poll";
            }
        }
    }

    async function startTableVote() {
        await openPollCreationModal();
        await launchConfiguredTablePoll();
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
                try {
                    localStorage.setItem(`cafe_active_vote_${state.cafeId}_${state.table}`, JSON.stringify(updated));
                } catch (e) {}
                updateTableVoteUI();
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
            try {
                localStorage.setItem(`cafe_active_vote_${state.cafeId}_${state.table}`, JSON.stringify(state.activeVoteSession));
            } catch (e) {}
            updateTableVoteUI();
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

    let voteTtlTimer = null;

    function scheduleVoteTtlTimer(session) {
        if (voteTtlTimer) {
            clearTimeout(voteTtlTimer);
            voteTtlTimer = null;
        }
        if (!session || !session.closes_at) return;
        const remainingMs = new Date(session.closes_at).getTime() - Date.now();
        if (remainingMs > 0) {
            voteTtlTimer = setTimeout(() => {
                checkActiveTableVoteSession();
            }, remainingMs + 500);
        }
    }

    function updateTableVoteUI() {
        const startVoteBtn = document.getElementById("btn-start-table-vote");
        const voteCtaCard = document.getElementById("table-vote-cta-card");

        const now = new Date();
        const hasActiveVote = !!(
            state.activeVoteSession &&
            !state.activeVoteSession.is_closed &&
            (!state.activeVoteSession.closes_at || now < new Date(state.activeVoteSession.closes_at))
        );

        if (hasActiveVote) {
            // A vote has started: show "Vote with Table" button, take option to start new vote away
            if (startVoteBtn) startVoteBtn.style.display = "inline-flex";
            if (voteCtaCard) voteCtaCard.style.display = "none";
        } else {
            // No active vote: hide "Vote with Table" button, show option to start table vote
            if (startVoteBtn) startVoteBtn.style.display = "none";
            if (voteCtaCard) voteCtaCard.style.display = "flex";
        }

        const bannerPollBtn = document.getElementById("btn-banner-start-poll");
        if (bannerPollBtn) {
            bannerPollBtn.textContent = hasActiveVote ? "🗳️ Vote with Table" : "🗳️ Start Table Vote";
        }
    }

    function openActiveTableVoteModal() {
        if (!state.activeVoteSession) {
            startTableVote();
            return;
        }

        const cafeName = (state.venueMeta && state.venueMeta.name) 
            ? state.venueMeta.name 
            : (state.cafeId ? state.cafeId.replace(/-/g, " ").replace(/\b\w/g, l => l.toUpperCase()) : "Cafe");

        const modal = document.getElementById("cafe-table-vote-modal");
        const modalTitle = document.getElementById("vote-modal-title");
        const setupSection = document.getElementById("vote-setup-section");
        const activeSection = document.getElementById("vote-active-section");
        const qrImg = document.getElementById("vote-modal-qr-img");
        const extLink = document.getElementById("btn-vote-open-external");
        const ballotSection = document.getElementById("vote-ballot-section");
        const consensusSection = document.getElementById("vote-consensus-section");
        const nameInput = document.getElementById("vote-voter-name-input");

        if (modalTitle) {
            modalTitle.textContent = state.table 
                ? `${cafeName} - ${/^\d+$/.test(state.table) ? 'Table ' + state.table : state.table} Vote`
                : `${cafeName} - Table Vote`;
        }
        if (modal) modal.style.display = "flex";
        if (setupSection) setupSection.style.display = "none";
        if (activeSection) activeSection.style.display = "block";

        if (nameInput) {
            const savedName = localStorage.getItem("bgg_cafe_voter_name") || `Table ${state.table} Patron`;
            nameInput.value = savedName;
        }

        const voteUrl = `${window.location.origin}/vote/?session_id=${state.activeVoteSession.session_id}&cafe=${encodeURIComponent(state.cafeId)}&table=${encodeURIComponent(state.table)}`;
        if (qrImg) {
            qrImg.src = `https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=${encodeURIComponent(voteUrl)}`;
        }
        if (extLink) {
            extLink.href = voteUrl;
        }

        const voterName = (nameInput && nameInput.value.trim()) ? nameInput.value.trim() : `Table ${state.table || "1"} Patron`;
        const hasVoted = state.activeVoteSession.votes && state.activeVoteSession.votes[voterName];

        if (hasVoted && state.activeVoteSession.consensus) {
            if (ballotSection) ballotSection.style.display = "none";
            if (consensusSection) consensusSection.style.display = "flex";
            renderConsensusStandings(state.activeVoteSession.consensus);
        } else {
            if (ballotSection) ballotSection.style.display = "flex";
            if (consensusSection) consensusSection.style.display = "none";
            if (state.activeVoteSession.candidates) {
                renderBallotCandidates(state.activeVoteSession.candidates);
            }
        }
    }

    async function checkActiveTableVoteSession() {
        if (!state.cafeId || !state.table) {
            updateTableVoteUI();
            return null;
        }

        const tableNum = String(state.table).trim();
        const creatorId = `cafe_${state.cafeId}_table_${tableNum}`;
        const now = new Date();

        // 1. Check in-memory state
        if (state.activeVoteSession) {
            const closesAt = state.activeVoteSession.closes_at ? new Date(state.activeVoteSession.closes_at) : null;
            if (state.activeVoteSession.is_closed || (closesAt && now >= closesAt)) {
                state.activeVoteSession = null;
                try {
                    localStorage.removeItem(`cafe_active_vote_${state.cafeId}_${tableNum}`);
                } catch (e) {}
            } else {
                scheduleVoteTtlTimer(state.activeVoteSession);
                updateTableVoteUI();
                return state.activeVoteSession;
            }
        }

        // 2. Check localStorage cache
        try {
            const cachedStr = localStorage.getItem(`cafe_active_vote_${state.cafeId}_${tableNum}`);
            if (cachedStr) {
                const cached = JSON.parse(cachedStr);
                const closesAt = cached.closes_at ? new Date(cached.closes_at) : null;
                if (cached && !cached.is_closed && (!closesAt || now < closesAt)) {
                    state.activeVoteSession = cached;
                    scheduleVoteTtlTimer(cached);
                    updateTableVoteUI();
                } else {
                    localStorage.removeItem(`cafe_active_vote_${state.cafeId}_${tableNum}`);
                }
            }
        } catch (e) {}

        // 3. Query API for live active sessions
        try {
            const resp = await window.fetchApi(`/sessions?creator_id=${encodeURIComponent(creatorId)}`);
            if (resp && resp.ok) {
                const data = await resp.json();
                const sessionsList = data.sessions || (Array.isArray(data) ? data : []);
                const currTime = new Date();
                const active = sessionsList.find(s => {
                    if (s.is_closed) return false;
                    const closesAt = s.closes_at ? new Date(s.closes_at) : null;
                    return !closesAt || currTime < closesAt;
                });

                if (active) {
                    state.activeVoteSession = active;
                    try {
                        localStorage.setItem(`cafe_active_vote_${state.cafeId}_${tableNum}`, JSON.stringify(active));
                    } catch (e) {}
                    scheduleVoteTtlTimer(active);
                } else if (state.activeVoteSession) {
                    const closesAt = state.activeVoteSession.closes_at ? new Date(state.activeVoteSession.closes_at) : null;
                    if (!closesAt || currTime >= closesAt) {
                        state.activeVoteSession = null;
                        try {
                            localStorage.removeItem(`cafe_active_vote_${state.cafeId}_${tableNum}`);
                        } catch (e) {}
                    }
                }
            }
        } catch (e) {
            console.warn("Could not check active table vote sessions:", e);
        }

        updateTableVoteUI();
        return state.activeVoteSession;
    }

    function setupTableVotingControls() {
        const startBtn = document.getElementById("btn-start-table-vote");
        const launchBtn = document.getElementById("btn-launch-table-vote");
        const bannerPollBtn = document.getElementById("btn-banner-start-poll");
        const closeBtn = document.getElementById("btn-close-vote-modal");
        const modal = document.getElementById("cafe-table-vote-modal");
        const submitBtn = document.getElementById("btn-submit-table-vote");
        const revoteBtn = document.getElementById("btn-revote-trigger");
        const refreshBtn = document.getElementById("btn-refresh-tally");
        const copyBtn = document.getElementById("btn-vote-copy-link");
        const shareBtn = document.getElementById("btn-vote-share-link");
        const btnLaunchConfigured = document.getElementById("btn-launch-configured-poll");
        const btnPollSelectRec = document.getElementById("btn-poll-select-rec");
        const btnPollClearAll = document.getElementById("btn-poll-clear-all");
        const pollSearchInput = document.getElementById("poll-search-input");
        const pollSearchClear = document.getElementById("poll-search-clear");

        if (startBtn) {
            startBtn.addEventListener("click", () => {
                const now = new Date();
                const hasActive = !!(
                    state.activeVoteSession &&
                    !state.activeVoteSession.is_closed &&
                    (!state.activeVoteSession.closes_at || now < new Date(state.activeVoteSession.closes_at))
                );
                if (hasActive) {
                    openActiveTableVoteModal();
                } else {
                    openPollCreationModal();
                }
            });
        }
        if (launchBtn) launchBtn.addEventListener("click", openPollCreationModal);
        if (bannerPollBtn) bannerPollBtn.addEventListener("click", openPollCreationModal);

        if (btnLaunchConfigured) {
            btnLaunchConfigured.addEventListener("click", launchConfiguredTablePoll);
        }

        if (btnPollSelectRec) {
            btnPollSelectRec.addEventListener("click", () => {
                state.pollSelectedIds = new Set(state.recommendedIds || []);
                renderPollCandidatePicker();
            });
        }

        if (btnPollClearAll) {
            btnPollClearAll.addEventListener("click", () => {
                state.pollSelectedIds = new Set();
                renderPollCandidatePicker();
            });
        }

        if (pollSearchInput) {
            pollSearchInput.addEventListener("input", (e) => {
                state.pollSearchQuery = e.target.value;
                if (pollSearchClear) {
                    pollSearchClear.style.display = e.target.value ? "block" : "none";
                }
                renderPollCandidatePicker();
            });
        }

        if (pollSearchClear) {
            pollSearchClear.addEventListener("click", () => {
                if (pollSearchInput) pollSearchInput.value = "";
                state.pollSearchQuery = "";
                pollSearchClear.style.display = "none";
                renderPollCandidatePicker();
            });
        }

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
            openPollCreationModal,
            renderPollCandidatePicker,
            launchConfiguredTablePoll,
            startTableVote,
            renderBallotCandidates,
            submitTableVoteBallot,
            renderConsensusStandings,
            setupTableVotingControls,
            openActiveTableVoteModal,
            updateTableVoteUI,
            checkActiveTableVoteSession,
            scheduleVoteTtlTimer,
            isSmallTableFriendly,
            renderGuruPicks,
            applyVenueBranding
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
            checkActiveTableVoteSession();

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

