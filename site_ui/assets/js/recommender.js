document.addEventListener("DOMContentLoaded", function () {
    const form = document.getElementById("recommender-form");
    const statusCard = document.getElementById("status-card");
    const statusMessage = document.getElementById("status-message");
    const resultsContainer = document.getElementById("recommendations-results");
    const submitBtn = document.getElementById("submit-btn");
    const refreshBtn = document.getElementById("refresh-btn");

    // Slider Elements
    const wMechInput = document.getElementById("w_mech");
    const wCatInput = document.getElementById("w_cat");
    const wPopInput = document.getElementById("w_pop");
    const wHotInput = document.getElementById("w_hot");

    const wMechVal = document.getElementById("w_mech_val");
    const wCatVal = document.getElementById("w_cat_val");
    const wPopVal = document.getElementById("w_pop_val");
    const wHotVal = document.getElementById("w_hot_val");

    // Preset Configurations
    const PRESETS = {
        balanced: {
            desc: "A balanced blend of mechanics similarity, theme/categories, and community popularity (each weighted at 50/100).",
            weights: { mech: 50, cat: 50, pop: 50, hot: 0 }
        },
        thematic: {
            desc: "Prioritizes games sharing similar themes, settings, and genres (categories weighted at 90/100, mechanics at 30/100).",
            weights: { mech: 30, cat: 90, pop: 40, hot: 10 }
        },
        strategy: {
            desc: "Prioritizes games with similar mechanics, rule systems, and strategic depth (mechanics weighted at 90/100, categories at 30/100).",
            weights: { mech: 90, cat: 30, pop: 40, hot: 0 }
        },
        trending: {
            desc: "Biases recommendations heavily towards new releases and trending games currently hot on BGG (hotness weighted at 90/100).",
            weights: { mech: 40, cat: 40, pop: 40, hot: 90 }
        },
        crowd_pleaser: {
            desc: "Focuses on highly-rated, widely-acclaimed community favorites (popularity weighted at 90/100).",
            weights: { mech: 30, cat: 30, pop: 90, hot: 0 }
        },
        custom: {
            desc: "Manually adjust weights to your exact preferences.",
            weights: null
        }
    };

    const presetSelect = document.getElementById("preset_profile");
    const presetDesc = document.getElementById("preset_desc");
    const customSlidersGroup = document.getElementById("custom-sliders-group");

    function saveSlidersToStorage() {
        const weights = {
            mech: wMechInput.value,
            cat: wCatInput.value,
            pop: wPopInput.value,
            hot: wHotInput.value
        };
        localStorage.setItem("bgg_rec_weights", JSON.stringify(weights));
        syncPreferencesToBackend();
    }

    function applyPreset(presetKey, updateSliders = true) {
        const preset = PRESETS[presetKey];
        if (!preset) return;

        presetDesc.textContent = preset.desc;

        if (presetKey === "custom") {
            customSlidersGroup.style.display = "block";
        } else {
            customSlidersGroup.style.display = "none";
            if (updateSliders && preset.weights) {
                wMechInput.value = preset.weights.mech;
                wCatInput.value = preset.weights.cat;
                wPopInput.value = preset.weights.pop;
                wHotInput.value = preset.weights.hot;
                
                // Update badges
                wMechVal.textContent = `${preset.weights.mech}%`;
                wCatVal.textContent = `${preset.weights.cat}%`;
                wPopVal.textContent = `${preset.weights.pop}%`;
                wHotVal.textContent = `${preset.weights.hot}%`;
                
                saveSlidersToStorage();
            }
        }
        localStorage.setItem("bgg_rec_preset", presetKey);
    }

    // Initialize & Sync from localStorage
    function initializeWeightsAndPresets() {
        // Clear any old manual onboarding quiz data from previous sessions
        localStorage.removeItem("manual_onboarding_ratings");
        localStorage.removeItem("manual_personality_weights");

        const storedPreset = localStorage.getItem("bgg_rec_preset") || "balanced";
        presetSelect.value = storedPreset;

        const storedWeights = localStorage.getItem("bgg_rec_weights");
        if (storedWeights) {
            try {
                const weights = JSON.parse(storedWeights);
                if (weights.mech !== undefined) wMechInput.value = weights.mech;
                if (weights.cat !== undefined) wCatInput.value = weights.cat;
                if (weights.pop !== undefined) wPopInput.value = weights.pop;
                if (weights.hot !== undefined) wHotInput.value = weights.hot;
            } catch (e) {
                console.error("Error reading stored weights:", e);
            }
        }

        // Load and restore duration and complexity preferences
        const durationPref = localStorage.getItem("bgg_rec_duration_pref") || "any";
        const complexityPref = localStorage.getItem("bgg_rec_complexity_pref") || "any";
        document.getElementById("duration_pref").value = durationPref;
        document.getElementById("complexity_pref").value = complexityPref;

        // Sync visual text badges
        wMechVal.textContent = `${wMechInput.value}%`;
        wCatVal.textContent = `${wCatInput.value}%`;
        wPopVal.textContent = `${wPopInput.value}%`;
        wHotVal.textContent = `${wHotInput.value}%`;

        // Apply preset and toggle visibility (do not overwrite if custom values were loaded)
        applyPreset(storedPreset, false);
    }

    [wMechInput, wCatInput, wPopInput, wHotInput].forEach(input => {
        input.addEventListener("input", function() {
            const valSpan = document.getElementById(`${input.id}_val`);
            if (valSpan) valSpan.textContent = `${input.value}%`;
            saveSlidersToStorage();
        });
    });

    presetSelect.addEventListener("change", function () {
        applyPreset(presetSelect.value, true);
    });

    document.getElementById("duration_pref").addEventListener("change", function() {
        localStorage.setItem("bgg_rec_duration_pref", this.value);
    });
    document.getElementById("complexity_pref").addEventListener("change", function() {
        localStorage.setItem("bgg_rec_complexity_pref", this.value);
    });

    // Preferences Sync functions
    async function syncPreferencesToBackend() {
        if (typeof Auth === 'undefined' || !Auth.isLoggedIn()) return;
        
        // Fetch current preferences first so we don't clobber fields like bgg_username
        let currentPrefs = {};
        try {
            const getRes = await fetchApi('/preferences');
            if (getRes.ok) currentPrefs = await getRes.json();
        } catch (e) {
            console.error("Failed fetching current preferences:", e);
        }
        
        const weights = {
            mech: wMechInput.value,
            cat: wCatInput.value,
            pop: wPopInput.value,
            hot: wHotInput.value
        };
        
        try {
            // Note: playgroups is defined globally on the window in playgroup integrations
            const playgroups = window.playgroups || [];
            await fetchApi('/preferences', {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    ...currentPrefs,
                    playgroups: playgroups,
                    saved_weights: weights,
                    user_preferences: {}
                })
            });
        } catch (e) {
            console.error("Error syncing preferences to backend:", e);
        }
    }

    async function loadPreferencesFromBackend() {
        if (typeof Auth === 'undefined' || !Auth.isLoggedIn()) return;
        
        try {
            const response = await fetchApi('/preferences');
            if (response.ok) {
                const data = await response.json();
                if (data.bgg_username) {
                    document.getElementById("username").value = data.bgg_username;
                }
                if (data.playgroups && Array.isArray(data.playgroups)) {
                    localStorage.setItem("bgg_playgroups", JSON.stringify(data.playgroups));
                }
                if (data.saved_weights) {
                    const weights = data.saved_weights;
                    if (weights.mech !== undefined) wMechInput.value = weights.mech;
                    if (weights.cat !== undefined) wCatInput.value = weights.cat;
                    if (weights.pop !== undefined) wPopInput.value = weights.pop;
                    if (weights.hot !== undefined) wHotInput.value = weights.hot;
                    localStorage.setItem("bgg_rec_weights", JSON.stringify(weights));
                    
                    wMechVal.textContent = `${wMechInput.value}%`;
                    wCatVal.textContent = `${wCatInput.value}%`;
                    wPopVal.textContent = `${wPopInput.value}%`;
                    wHotVal.textContent = `${wHotInput.value}%`;
                }
            }
        } catch (e) {
            console.error("Error loading preferences from backend:", e);
        }
    }

    // Fetch active conventions and populate dropdown
    async function loadConventions() {
        try {
            const response = await fetchApi('/conventions');
            if (response.ok) {
                const conventions = await response.json();
                if (conventions && conventions.length > 0) {
                    const select = document.getElementById("conventionSelect");
                    const group = document.getElementById("convention-group");
                    
                    // Clear any existing options except the first "All Games" one
                    select.innerHTML = '<option value="">All Games</option>';
                    
                    conventions.forEach(conv => {
                        const opt = document.createElement("option");
                        opt.value = conv.convention_id;
                        opt.textContent = `${conv.name} (${conv.game_count} games)`;
                        select.appendChild(opt);
                    });
                    
                    // Update label to show active count
                    const label = group.querySelector("label");
                    if (label) {
                        label.innerHTML = `Upcoming Convention Filter <span style="color: var(--success); font-weight: 800; font-size: 0.7rem; background: rgba(16, 185, 129, 0.1); padding: 2px 6px; border-radius: 4px; margin-left: 6px; vertical-align: middle; text-transform: uppercase;">${conventions.length} Active</span>`;
                    }
                    
                    group.style.display = "flex";
                }
            }
        } catch (e) {
            console.error("Error loading active conventions:", e);
        }
    }

    // Initialize weights and presets
    initializeWeightsAndPresets();
    loadPreferencesFromBackend();
    loadConventions();

    // Listen to custom login event to load preferences immediately upon login
    document.addEventListener("bgg_login_success", function() {
        loadPreferencesFromBackend();
    });

    let pollingTimeout = null;
    let isPollingActive = false;
    let activeSearchKey = null;

    const SEED_CATALOG = [
        {
            id: "174430",
            name: "Gloomhaven",
            image: "https://cf.geekdo-images.com/OBUTs8Upox1__rHIsg6ViA__small/img/NkxnU-s0bRNGwgi8dqAKKEopMzU=/fit-in/200x150/filters:strip_icc()/pic9662755.jpg",
            mechanics: ["Cooperative Game", "Grid Movement", "Campaign / Scenario / Mission Lvg"]
        },
        {
            id: "13",
            name: "Catan",
            image: "https://cf.geekdo-images.com/rg6OOR55B9fV3MCDfgdNdg__small/img/ql8oE9UE4UDjI_JUyaIstGkqGYg=/fit-in/200x150/filters:strip_icc()/pic9674480.jpg",
            mechanics: ["Trading", "Dice Rolling", "Network and Route Building"]
        },
        {
            id: "178900",
            name: "Codenames",
            image: "https://cf.geekdo-images.com/GNw7rg1uFhdSowcjQZ4F5g__small/img/pWnrQZJJqjp3EGnmNMYNukNvXZ0=/fit-in/200x150/filters:strip_icc()/pic9608422.png",
            mechanics: ["Deduction", "Team-Based Game", "Communication Limits"]
        },
        {
            id: "9209",
            name: "Ticket to Ride",
            image: "https://cf.geekdo-images.com/eoCGMPqtOPZSHEACZkWwHw__small/img/rsVQLCKn9dJV5BjUNaA6ruzKeDg=/fit-in/200x150/filters:strip_icc()/pic9653788.jpg",
            mechanics: ["Card Drafting", "Set Collection", "Network and Route Building"]
        },
        {
            id: "30549",
            name: "Pandemic",
            image: "https://cf.geekdo-images.com/QsCBY10yJ6VbNq8odEkFvQ__small/img/he9ngCPfm75d3pa3X1KNw19WzZ4=/fit-in/200x150/filters:strip_icc()/pic9641990.png",
            mechanics: ["Cooperative Game", "Action Points", "Point to Point Movement"]
        },
        {
            id: "68448",
            name: "7 Wonders",
            image: "https://cf.geekdo-images.com/UDflrZeOvVizJe-ZcRrp6g__small/img/O22_OSjC57JUKmZxIyGWQu2AkAY=/fit-in/200x150/filters:strip_icc()/pic9299348.jpg",
            mechanics: ["Card Drafting", "Hand Management", "Simultaneous Action Selection"]
        },
        {
            id: "230802",
            name: "Azul",
            image: "https://cf.geekdo-images.com/yQM6mW8QvXg0DzZLLh0dCQ__small/img/wlWi5ffB-WEmWKobN-IjDjSgH2g=/fit-in/200x150/filters:strip_icc()/pic9660979.jpg",
            mechanics: ["Tile Placement", "Drafting", "Pattern Building"]
        },
        {
            id: "266192",
            name: "Wingspan",
            image: "https://cf.geekdo-images.com/fqqlSn7nGpGXAdoNQEHuYQ__small/img/hrOSJ1rShe8jygMrckpAk6S3lXk=/fit-in/200x150/filters:strip_icc()/pic9678251.jpg",
            mechanics: ["Drafting", "Set Collection", "Dice Rolling"]
        },
        {
            id: "36218",
            name: "Dominion",
            image: "https://cf.geekdo-images.com/IoozL860MR2CebKgPWQi6w__small/img/ykuymRXuCC1B73PVVNAuPpkB3OQ=/fit-in/200x150/filters:strip_icc()/pic9683981.jpg",
            mechanics: ["Deck, Bag, and Pool Building", "Hand Management", "Delayed Purchase"]
        },
        {
            id: "169786",
            name: "Scythe",
            image: "https://cf.geekdo-images.com/zjm1LW5RV57N3S2hX-EcRw__small/img/ERIt9VMMVlOWXH0cA91cnTg5BFQ=/fit-in/200x150/filters:strip_icc()/pic9662313.png",
            mechanics: ["Area Majority / Influence", "Resource Management", "Asymmetric Games"]
        },
        {
            id: "131357",
            name: "Coup",
            image: "https://cf.geekdo-images.com/AwfXpPn8IwghSkUI-Ebhvg__small/img/6ONRvgwNmopzgZXDkiSyu_q9LLY=/fit-in/200x150/filters:strip_icc()/pic9687331.jpg",
            mechanics: ["Bluffing", "Player Elimination", "Hidden Roles"]
        },
        {
            id: "39856",
            name: "Dixit",
            image: "https://cf.geekdo-images.com/sCn9y6PtmRkIMIGYgcFjXA__small/img/IiyzLjBnom0BHaCifwlkE1SaepM=/fit-in/200x150/filters:strip_icc()/pic9572269.jpg",
            mechanics: ["Creativity", "Simultaneous Action Selection", "Voting"]
        },
        {
            id: "31260",
            name: "Agricola",
            image: "https://cf.geekdo-images.com/ylVEa2gIveavIzoA_8gXJQ__small/img/Byawbf78dJqbXGZkbM_Ff89IejQ=/fit-in/200x150/filters:strip_icc()/pic9647458.jpg",
            mechanics: ["Worker Placement", "Resource Management", "Turn Order: Progressive"]
        },
        {
            id: "237182",
            name: "Root",
            image: "https://cf.geekdo-images.com/kK-LrmAyfOU_gB5b8O-ccw__small/img/Sr0719wl9U1fAxCEXmG3bc0XzAY=/fit-in/200x150/filters:strip_icc()/pic9686574.jpg",
            mechanics: ["Asymmetric Games", "Area Majority / Influence", "Hand Management"]
        }
    ];

    function getRecommendations(forceRefresh = false, inlineProfile = null, inlineWeights = null) {
        // Clear existing states and cancel active polling
        isPollingActive = false;
        if (pollingTimeout) {
            clearTimeout(pollingTimeout);
        }
        if (window.renderSkeletonCards) {
            window.renderSkeletonCards(resultsContainer, 4);
        } else {
            resultsContainer.innerHTML = "";
        }
        
        const spinner = statusCard.querySelector(".spinner");
        if (spinner) spinner.style.display = "none";

        statusCard.style.display = "flex";
        statusMessage.textContent = "Connecting to backend recommender engine...";
        submitBtn.disabled = true;
        if (refreshBtn) {
            refreshBtn.disabled = true;
            refreshBtn.style.display = "flex";
        }

        const username = document.getElementById("username").value.trim();
        const own_status = document.getElementById("own_status").value;
        const year_start = document.getElementById("year_start").value;
        const year_end = document.getElementById("year_end").value;
        const durationPref = document.getElementById("duration_pref").value;
        const complexityPref = document.getElementById("complexity_pref").value;

        // Normalize weights for query parameter and cache key
        const w_mech = (wMechInput.value / 100).toFixed(2);
        const w_cat = (wCatInput.value / 100).toFixed(2);
        const w_pop = (wPopInput.value / 100).toFixed(2);
        const w_hot = (wHotInput.value / 100).toFixed(2);

        const conventionSelect = document.getElementById("conventionSelect");
        const convention_id = conventionSelect ? conventionSelect.value : "";

        const isInline = (inlineProfile !== null) || (inlineWeights !== null);

        // Build unique cache key including weights, preferences and convention filter
        const cacheKey = `bgg_rec_${username.toLowerCase() || 'manual'}_${own_status}_${year_start || 'any'}_${year_end || 'any'}_${durationPref}_${complexityPref}_${convention_id || 'any'}_${w_mech}_${w_cat}_${w_pop}_${w_hot}`;
        activeSearchKey = cacheKey;

        // Check if fresh cache exists (TTL = 7 days) - skip for inline profiles
        if (!forceRefresh && !isInline) {
            const cachedDataStr = localStorage.getItem(cacheKey);
            if (cachedDataStr) {
                try {
                    const cachedData = JSON.parse(cachedDataStr);
                    const ageMs = Date.now() - cachedData.timestamp;
                    const sevenDaysMs = 7 * 24 * 60 * 60 * 1000;
                    if (ageMs < sevenDaysMs) {
                        console.log("Serving recommendations from local storage cache.");
                        statusCard.style.display = "none";
                        submitBtn.disabled = false;
                        if (refreshBtn) {
                            refreshBtn.disabled = false;
                        }
                        renderRecommendations(cachedData.recommendations, false); // narration is complete in cache
                        return; // Exit and skip calling backend
                    } else {
                        console.log("Cached recommendations are stale. Requesting fresh data.");
                        localStorage.removeItem(cacheKey);
                    }
                } catch (e) {
                    console.error("Error reading from local cache:", e);
                    localStorage.removeItem(cacheKey);
                }
            }
        } else if (!isInline) {
            localStorage.removeItem(cacheKey);
        }

        // Build query params
        let queryParams = new URLSearchParams({
            username: username,
            own_status: own_status,
            w_mech: w_mech,
            w_cat: w_cat,
            w_pop: w_pop,
            w_hot: w_hot,
            narrate: 'true'
        });
        if (year_start) queryParams.append("year_start", year_start);
        if (year_end) queryParams.append("year_end", year_end);
        if (durationPref && durationPref !== 'any') queryParams.append('duration_pref', durationPref);
        if (complexityPref && complexityPref !== 'any') queryParams.append('complexity_pref', complexityPref);
        if (convention_id) queryParams.append('convention_id', convention_id);
        if (forceRefresh) queryParams.append('refresh', 'true');

        const url = `/recommendations?${queryParams.toString()}`;
        isPollingActive = true;

        // Build POST body if inline
        const bodyPayload = {
            own_status: own_status,
            w_mech: parseFloat(w_mech),
            w_cat: parseFloat(w_cat),
            w_pop: parseFloat(w_pop),
            w_hot: parseFloat(w_hot),
            narrate: true
        };
        if (year_start) bodyPayload.year_start = parseInt(year_start);
        if (year_end) bodyPayload.year_end = parseInt(year_end);
        if (durationPref && durationPref !== 'any') bodyPayload.duration_pref = durationPref;
        if (complexityPref && complexityPref !== 'any') bodyPayload.complexity_pref = complexityPref;
        if (convention_id) bodyPayload.convention_id = convention_id;
        
        if (inlineProfile) bodyPayload.inline_profile = inlineProfile;
        if (inlineWeights) bodyPayload.inline_weights = inlineWeights;

        function pollRecommendations() {
            if (!isPollingActive) return;

            let requestPromise;
            if (isInline) {
                requestPromise = fetchApi('/recommendations', {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify(bodyPayload)
                });
            } else {
                requestPromise = fetchApi(url);
            }

            requestPromise
                .then(response => {
                    if (!response.ok) {
                        throw new Error("Network response error");
                    }
                    return response.json();
                })
                .then(data => {
                    if (!isPollingActive) return;

                    if (data.status === "scraping") {
                        statusMessage.textContent = "First time search! We are currently scraping your collection from BGG. This takes about 30 seconds...";
                        pollingTimeout = setTimeout(pollRecommendations, 5000);
                    } else if (data.status === "cold_start_required") {
                        isPollingActive = false;
                        statusCard.style.display = "none";
                        submitBtn.disabled = false;
                        if (refreshBtn) refreshBtn.disabled = false;
                        
                        // Launch the wizard!
                        launchWizardFromRedirect(data.reason);
                    } else if (data.status === "ready") {
                        statusCard.style.display = "none";
                        submitBtn.disabled = false;
                        if (refreshBtn) {
                            refreshBtn.disabled = false;
                        }
                        isPollingActive = false;

                        renderRecommendations(data.recommendations, false);

                        // Trigger soft warning banner if they have between 5 and 12 liked/owned games
                        const ratingsCount = data.ratings_count || 0;
                        const banner = document.getElementById("sparse-profile-banner");
                        if (!isInline && ratingsCount > 0 && ratingsCount < 12) {
                            if (banner) banner.style.display = "flex";
                        } else {
                            if (banner) banner.style.display = "none";
                        }

                        if (!isInline) {
                            try {
                                const cacheVal = {
                                    timestamp: Date.now(),
                                    recommendations: data.recommendations
                                };
                                localStorage.setItem(cacheKey, JSON.stringify(cacheVal));
                            } catch (cacheErr) {
                                console.error("Error writing to cache:", cacheErr);
                            }
                        }
                    } else {
                        throw new Error("Unexpected response status");
                    }
                })
                .catch(error => {
                    if (!isPollingActive) return;
                    console.error("Fetch error:", error);
                    isPollingActive = false;
                    statusCard.style.display = "none";
                    submitBtn.disabled = false;
                    if (refreshBtn) {
                        refreshBtn.disabled = false;
                    }
                    resultsContainer.innerHTML = `<div style="color: var(--danger); font-weight: bold; padding: 20px; background: var(--danger-bg); border: 1px solid var(--danger-border); border-radius: 8px; margin: 0 auto; text-align: center;">Error: Failed to fetch recommendations. Ensure that API Gateway CORS and the Lambda function are running correctly.</div>`;
                });
        }

        // Trigger initial call
        pollRecommendations();
    }

    form.addEventListener("submit", function (e) {
        e.preventDefault();
        getRecommendations(false);
    });

    if (refreshBtn) {
        refreshBtn.addEventListener("click", function () {
            getRecommendations(true);
        });
    }

    // ==========================================
    // NEW USER WIZARD CONTROLLER LOGIC
    // ==========================================
    const wizardModal = document.getElementById("wizard-modal");
    const launchWizardBtn = document.getElementById("launch-wizard-btn");
    const emptyStateWizardBtn = document.getElementById("empty-state-wizard-btn");
    const sparseLaunchWizard = document.getElementById("sparse-launch-wizard");
    const closeWizardBtn = document.getElementById("close-wizard-btn");
    const sparseBanner = document.getElementById("sparse-profile-banner");
    const closeSparseBanner = document.getElementById("close-sparse-banner");

    // Screen References
    const welcomeScreen = document.getElementById("wizard-welcome-screen");
    const tasteTestScreen = document.getElementById("wizard-taste-test-screen");
    const personalityScreen = document.getElementById("wizard-personality-screen");

    // Buttons
    const pathGamerBtn = document.getElementById("path-gamer-btn");
    const pathCasualBtn = document.getElementById("path-casual-btn");

    // Taste Test State & Elements
    const tasteGameImg = document.getElementById("taste-game-img");
    const tasteGameTitle = document.getElementById("taste-game-title");
    const tasteGameMechanics = document.getElementById("taste-game-mechanics");
    const rateLikeBtn = document.getElementById("rate-like-btn");
    const rateDislikeBtn = document.getElementById("rate-dislike-btn");
    const rateSkipBtn = document.getElementById("rate-skip-btn");
    const wizardProgressBar = document.getElementById("wizard-progress-bar");
    const wizardProgressText = document.getElementById("wizard-progress-text");
    const tasteTestBackBtn = document.getElementById("taste-test-back-btn");
    const tasteTestRecommendBtn = document.getElementById("taste-test-recommend-btn");

    let tasteRatings = [];
    let tasteRoundGames = [];
    let tasteGameIndex = 0;

    // Personality Elements
    const personalityQuestionSlides = document.querySelectorAll(".personality-question-slide");
    const personalityProgressBar = document.getElementById("personality-progress-bar");
    const personalityProgressText = document.getElementById("personality-progress-text");
    const personalityBackBtn = document.getElementById("personality-back-btn");
    const personalityNextBtn = document.getElementById("personality-next-btn");
    const personalityRecommendBtn = document.getElementById("personality-recommend-btn");

    let personalityIndex = 1;

    function openModal() {
        if (wizardModal) {
            wizardModal.style.display = "flex";
            document.body.style.overflow = "hidden";
            showScreen(welcomeScreen);
        }
    }

    function closeModal() {
        if (wizardModal) {
            wizardModal.style.display = "none";
            document.body.style.overflow = "";
        }
    }

    if (launchWizardBtn) launchWizardBtn.addEventListener("click", (e) => { e.preventDefault(); openModal(); });
    if (emptyStateWizardBtn) emptyStateWizardBtn.addEventListener("click", openModal);
    if (sparseLaunchWizard) sparseLaunchWizard.addEventListener("click", (e) => { e.preventDefault(); openModal(); });
    if (closeWizardBtn) closeWizardBtn.addEventListener("click", closeModal);
    if (closeSparseBanner) closeSparseBanner.addEventListener("click", () => {
        if (sparseBanner) sparseBanner.style.display = "none";
    });

    function showScreen(screenEl) {
        [welcomeScreen, tasteTestScreen, personalityScreen].forEach(el => {
            if (el) el.classList.remove("active");
        });
        if (screenEl) screenEl.classList.add("active");
    }

    function launchWizardFromRedirect(reason) {
        openModal();
        let headingText = "Welcome to Boardgame Recommender!";
        let bodyText = "To get personalized recommendations, we need to know your taste. Choose one of the options below to get started:";
        if (reason === "no_profile") {
            headingText = "BGG Username Not Found / Empty";
            bodyText = "We couldn't retrieve a collection for that BoardGameGeek username. Let's create your taste profile manually using one of the options below:";
        } else if (reason === "insufficient_data") {
            headingText = "Sparse BGG Profile";
            bodyText = "Your BoardGameGeek profile has very few rated games. Let's supplement your profile manually using one of the options below:";
        }
        
        const welcomeTitle = welcomeScreen.querySelector("h2");
        const welcomeText = welcomeScreen.querySelector("p");
        if (welcomeTitle) welcomeTitle.textContent = headingText;
        if (welcomeText) welcomeText.textContent = bodyText;
    }

    if (pathGamerBtn) pathGamerBtn.addEventListener("click", () => {
        showScreen(tasteTestScreen);
        initTasteTest();
    });

    if (pathCasualBtn) pathCasualBtn.addEventListener("click", () => {
        showScreen(personalityScreen);
        initPersonalityTest();
    });

    // PATH 1: QUICK TASTE TEST LOGIC
    function initTasteTest() {
        tasteRatings = [];
        tasteGameIndex = 0;

        // Restore elements visibility for new taste test
        const carousel = document.querySelector(".taste-test-carousel");
        const actions = document.querySelector(".taste-test-actions");
        const progressContainer = document.querySelector(".wizard-progress-container");
        const backBtn = document.getElementById("taste-test-back-btn");
        const recommendBtn = document.getElementById("taste-test-recommend-btn");

        if (carousel) carousel.style.display = "";
        if (actions) actions.style.display = "";
        if (progressContainer) progressContainer.style.display = "";
        if (backBtn) backBtn.style.display = "";
        if (recommendBtn) {
            recommendBtn.style.width = "";
            recommendBtn.style.margin = "";
            recommendBtn.disabled = true;
        }

        const summaryContainer = document.querySelector(".taste-test-summary-container");
        if (summaryContainer) {
            summaryContainer.style.display = "none";
            summaryContainer.innerHTML = "";
        }

        const round1Ids = ["13", "9209", "30549", "178900", "230802", "266192"];
        tasteRoundGames = SEED_CATALOG.filter(game => round1Ids.includes(game.id));

        loadTasteTestGame();
    }

    function loadTasteTestGame() {
        if (tasteGameIndex < tasteRoundGames.length) {
            const game = tasteRoundGames[tasteGameIndex];
            
            if (tasteGameImg) tasteGameImg.src = game.image;
            if (tasteGameTitle) tasteGameTitle.textContent = game.name;
            
            if (tasteGameMechanics) {
                tasteGameMechanics.innerHTML = "";
                game.mechanics.forEach(mech => {
                    const tag = document.createElement("span");
                    tag.textContent = mech;
                    tasteGameMechanics.appendChild(tag);
                });
            }
            
            updateTasteTestProgress();
        } else {
            if (tasteRoundGames.length === 6) {
                buildAdaptiveRound2();
            } else {
                console.log("Completed rating all available seeds! Total ratings collected:", tasteRatings.length, JSON.stringify(tasteRatings));
                // Update the progress UI one last time to include the final game's rating
                updateTasteTestProgress();
                
                // Create or find summary container
                let summaryContainer = document.querySelector(".taste-test-summary-container");
                if (!summaryContainer) {
                    summaryContainer = document.createElement("div");
                    summaryContainer.className = "taste-test-summary-container";
                    const footer = document.querySelector("#wizard-taste-test-screen .wizard-footer-actions");
                    if (footer) {
                        footer.parentNode.insertBefore(summaryContainer, footer);
                    }
                }

                // Populate liked games summary
                const likedGames = tasteRatings.filter(r => r.rating === 9.0);
                let summaryHtml = "";
                if (likedGames.length > 0) {
                    summaryHtml += `
                        <div class="liked-games-summary" style="margin-top: 5px; margin-bottom: 20px; text-align: left; background: rgba(255,255,255,0.03); border: 1px solid var(--border); border-radius: 12px; padding: 18px; animation: fadeIn 0.3s ease;">
                            <h3 style="margin-top: 0; margin-bottom: 12px; font-size: 1.05rem; display: flex; align-items: center; gap: 8px; font-family: 'Outfit', sans-serif;">
                                <span style="font-size: 1.2rem;">👍</span> Your Saved Liked Games (${likedGames.length})
                            </h3>
                            <div class="liked-games-list" style="display: flex; flex-direction: column; gap: 8px;">
                    `;
                    likedGames.forEach(liked => {
                        const seedGame = SEED_CATALOG.find(g => g.id === liked.id);
                        if (seedGame) {
                            summaryHtml += `
                                <div style="display: flex; align-items: center; gap: 12px; padding: 6px 12px; background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); border-radius: 8px;">
                                    <img src="${seedGame.image}" alt="${seedGame.name}" style="width: 32px; height: 32px; object-fit: cover; border-radius: 4px;">
                                    <span style="font-weight: 600; font-size: 0.95rem; color: var(--text-main);">${seedGame.name}</span>
                                </div>
                            `;
                        }
                    });
                    summaryHtml += `
                            </div>
                        </div>
                    `;
                } else {
                    summaryHtml += `
                        <div class="liked-games-summary" style="margin-top: 5px; margin-bottom: 20px; text-align: center; background: rgba(255,255,255,0.03); border: 1px solid var(--border); border-radius: 12px; padding: 18px; animation: fadeIn 0.3s ease;">
                            <p style="margin: 0; color: var(--text-muted); font-size: 0.95rem;">You didn't thumbs-up any games in the test.</p>
                        </div>
                    `;
                }
                
                if (summaryContainer) {
                    summaryContainer.innerHTML = summaryHtml;
                    summaryContainer.style.display = "block";
                }

                // Hide everything except the recommend button
                const carousel = document.querySelector(".taste-test-carousel");
                const actions = document.querySelector(".taste-test-actions");
                const progressContainer = document.querySelector(".wizard-progress-container");
                const backBtn = document.getElementById("taste-test-back-btn");
                const recommendBtn = document.getElementById("taste-test-recommend-btn");

                if (carousel) carousel.style.display = "none";
                if (actions) actions.style.display = "none";
                if (progressContainer) progressContainer.style.display = "none";
                if (backBtn) backBtn.style.display = "none";
                if (recommendBtn) {
                    recommendBtn.disabled = false; // Ensure it's enabled since we reached the end
                    recommendBtn.style.display = "inline-flex";
                    recommendBtn.style.width = "100%";
                    recommendBtn.style.justifyContent = "center";
                }
            }
        }
    }

    function buildAdaptiveRound2() {
        const ratedMechs = new Set();
        tasteRatings.forEach(r => {
            const seedGame = SEED_CATALOG.find(g => g.id === r.id);
            if (seedGame) {
                seedGame.mechanics.forEach(m => ratedMechs.add(m));
            }
        });

        const round1Ids = ["13", "9209", "30549", "178900", "230802", "266192"];
        const remainingGames = SEED_CATALOG.filter(game => !round1Ids.includes(game.id));

        remainingGames.sort((gA, gB) => {
            const overlapA = gA.mechanics.filter(m => ratedMechs.has(m)).length;
            const overlapB = gB.mechanics.filter(m => ratedMechs.has(m)).length;
            return overlapA - overlapB;
        });

        const round2Games = remainingGames.slice(0, 5);
        tasteRoundGames = tasteRoundGames.concat(round2Games);
        
        loadTasteTestGame();
    }

    function rateGame(ratingValue) {
        const game = tasteRoundGames[tasteGameIndex];
        
        tasteRatings = tasteRatings.filter(r => r.id !== game.id);
        
        if (ratingValue !== null) {
            tasteRatings.push({ id: game.id, rating: ratingValue });
        }
        
        console.log(`[Taste Test] Rated ${game.name} (${game.id}) -> ${ratingValue}. Total ratings: ${tasteRatings.length}`);
        
        tasteGameIndex++;
        loadTasteTestGame();
    }

    function updateTasteTestProgress() {
        const count = tasteRatings.length;
        const target = 5;
        const progressPct = Math.min(100, (count / target) * 100);
        
        if (wizardProgressBar) wizardProgressBar.style.width = `${progressPct}%`;
        if (wizardProgressText) {
            wizardProgressText.textContent = `${count} of ${target} ratings collected ${count >= target ? '— Ready!' : ''}`;
        }
        
        if (tasteTestRecommendBtn) {
            tasteTestRecommendBtn.disabled = count < target;
        }
    }

    if (rateLikeBtn) rateLikeBtn.addEventListener("click", () => rateGame(9.0));
    if (rateDislikeBtn) rateDislikeBtn.addEventListener("click", () => rateGame(3.0));
    if (rateSkipBtn) rateSkipBtn.addEventListener("click", () => rateGame(null));
    if (tasteTestBackBtn) tasteTestBackBtn.addEventListener("click", () => showScreen(welcomeScreen));
    
    if (tasteTestRecommendBtn) tasteTestRecommendBtn.addEventListener("click", () => {
        closeModal();
        
        syncManualPreferencesToBackend(tasteRatings, null);
        getRecommendations(true, tasteRatings, null);
    });

    // PATH 2: PERSONALITY TEST LOGIC
    function initPersonalityTest() {
        personalityIndex = 1;
        // Uncheck all radio buttons in the personality slides to start fresh
        document.querySelectorAll(".personality-option-card input[type='radio']").forEach(radio => {
            radio.checked = false;
        });
        showPersonalitySlide();
    }

    function showPersonalitySlide() {
        personalityQuestionSlides.forEach(slide => {
            const qNum = parseInt(slide.getAttribute("data-question"));
            if (qNum === personalityIndex) {
                slide.style.display = "block";
                slide.classList.add("active");
            } else {
                slide.style.display = "none";
                slide.classList.remove("active");
            }
        });

        const progressPct = (personalityIndex / 7) * 100;
        if (personalityProgressBar) personalityProgressBar.style.width = `${progressPct}%`;
        if (personalityProgressText) personalityProgressText.textContent = `Question ${personalityIndex} of 7`;

        checkQuestionAnswered();

        if (personalityIndex === 7) {
            if (personalityNextBtn) personalityNextBtn.style.display = "none";
            if (personalityRecommendBtn) personalityRecommendBtn.style.display = "inline-flex";
        } else {
            if (personalityNextBtn) personalityNextBtn.style.display = "inline-flex";
            if (personalityRecommendBtn) personalityRecommendBtn.style.display = "none";
        }
    }

    function checkQuestionAnswered() {
        const activeSlide = document.querySelector(".personality-question-slide.active");
        if (!activeSlide) return;

        const inputs = activeSlide.querySelectorAll("input[type='radio']");
        let answered = false;
        inputs.forEach(input => {
            if (input.checked) answered = true;
        });

        if (personalityIndex === 7) {
            if (personalityRecommendBtn) personalityRecommendBtn.disabled = !answered;
        } else {
            if (personalityNextBtn) personalityNextBtn.disabled = !answered;
        }
    }

    document.querySelectorAll(".personality-option-card input[type='radio']").forEach(radio => {
        radio.addEventListener("change", checkQuestionAnswered);
    });

    if (personalityNextBtn) personalityNextBtn.addEventListener("click", () => {
        if (personalityIndex < 7) {
            personalityIndex++;
            showPersonalitySlide();
        }
    });

    if (personalityBackBtn) personalityBackBtn.addEventListener("click", () => {
        if (personalityIndex > 1) {
            personalityIndex--;
            showPersonalitySlide();
        } else {
            showScreen(welcomeScreen);
        }
    });

    if (personalityRecommendBtn) personalityRecommendBtn.addEventListener("click", () => {
        closeModal();
        const inlineWeights = compilePersonalityWeights();

        syncManualPreferencesToBackend(null, inlineWeights);
        getRecommendations(true, null, inlineWeights);
    });

    function compilePersonalityWeights() {
        const getRadioVal = (name) => {
            const selected = document.querySelector(`input[name="${name}"]:checked`);
            return selected ? selected.value : null;
        };

        const q1 = getRadioVal("q1");
        const q2 = getRadioVal("q2");
        const q3 = getRadioVal("q3");
        const q4 = getRadioVal("q4");
        const q5 = getRadioVal("q5");
        const q6 = getRadioVal("q6");
        const q7 = getRadioVal("q7");

        const mech_weights = {};
        const cat_weights = {};
        const complexity_weights = {
            "Light": 0.0,
            "Medium-Light": 0.0,
            "Medium-Heavy": 0.0,
            "Heavy": 0.0
        };

        if (q1 === "cooperative") {
            mech_weights["Cooperative Game"] = 10.0;
        }

        if (q2 === "light") {
            complexity_weights["Light"] = 1.0;
            document.getElementById("complexity_pref").value = "light";
            localStorage.setItem("bgg_rec_complexity_pref", "light");
        } else if (q2 === "medium") {
            complexity_weights["Medium-Light"] = 1.0;
            complexity_weights["Medium-Heavy"] = 1.0;
            document.getElementById("complexity_pref").value = "medium";
            localStorage.setItem("bgg_rec_complexity_pref", "medium");
        } else if (q2 === "heavy") {
            complexity_weights["Heavy"] = 1.0;
            document.getElementById("complexity_pref").value = "heavy";
            localStorage.setItem("bgg_rec_complexity_pref", "heavy");
        }

        if (q3 === "short") {
            mech_weights["Real-time"] = 5.0;
            document.getElementById("duration_pref").value = "short";
            localStorage.setItem("bgg_rec_duration_pref", "short");
        } else if (q3 === "medium") {
            document.getElementById("duration_pref").value = "medium";
            localStorage.setItem("bgg_rec_duration_pref", "medium");
        } else if (q3 === "long") {
            document.getElementById("duration_pref").value = "long";
            localStorage.setItem("bgg_rec_duration_pref", "long");
        }

        if (q4 === "nature") {
            cat_weights["Animals"] = 10.0;
            cat_weights["Environmental"] = 8.0;
        } else if (q4 === "scifi") {
            cat_weights["Sci-Fi"] = 10.0;
            cat_weights["Fantasy"] = 10.0;
            cat_weights["Adventure"] = 8.0;
        } else if (q4 === "economic") {
            cat_weights["Economic"] = 10.0;
            cat_weights["Industry / Manufacturing"] = 8.0;
        }

        if (q5 === "high") {
            mech_weights["Dice Rolling"] = 10.0;
        } else if (q5 === "low") {
            mech_weights["Grid Movement"] = 8.0;
            cat_weights["Abstract Strategy"] = 10.0;
        }

        if (q6 === "engine") {
            mech_weights["Deck, Bag, and Pool Building"] = 10.0;
            mech_weights["Set Collection"] = 8.0;
        } else if (q6 === "worker") {
            mech_weights["Worker Placement"] = 10.0;
            mech_weights["Area Majority / Influence"] = 8.0;
        }

        if (q7 === "conflict") {
            mech_weights["Take That"] = 8.0;
            mech_weights["Area Majority / Influence"] = 8.0;
        } else if (q7 === "social") {
            mech_weights["Trading"] = 8.0;
            mech_weights["Negotiation"] = 8.0;
            mech_weights["Bluffing"] = 5.0;
        } else if (q7 === "solitaire") {
            mech_weights["Hand Management"] = 5.0;
            mech_weights["Set Collection"] = 5.0;
        }

        const weightsObj = {
            mech_weights: mech_weights,
            cat_weights: cat_weights,
            complexity_weights: complexity_weights,
            designer_weights: {},
            publisher_weights: {}
        };

        return weightsObj;
    }

    async function syncManualPreferencesToBackend(onboardingRatings = null, onboardingWeights = null) {
        if (typeof Auth === 'undefined' || !Auth.isLoggedIn()) return;

        let currentPrefs = {};
        try {
            const getRes = await fetchApi('/preferences');
            if (getRes.ok) currentPrefs = await getRes.json();
        } catch (e) {
            console.error("Failed fetching current preferences:", e);
        }

        const updatedPrefs = {
            ...currentPrefs,
            playgroups: window.playgroups || [],
            user_preferences: currentPrefs.user_preferences || {}
        };

        if (onboardingRatings) {
            updatedPrefs.onboarding_ratings = onboardingRatings;
        }
        if (onboardingWeights) {
            updatedPrefs.user_preferences.personality_weights = onboardingWeights;
        }

        try {
            await fetchApi('/preferences', {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(updatedPrefs)
            });
            console.log("Successfully synced manual onboarding preferences to DynamoDB.");
        } catch (e) {
            console.error("Error syncing manual onboarding preferences:", e);
        }
    }

    function renderRecommendations(recs, isPending = false) {
        if (!recs || recs.length === 0) {
            resultsContainer.innerHTML = `<div style="text-align: center; padding: 40px; color: var(--text-muted); font-size: 1.1rem; border: 1px dashed var(--border); border-radius: 12px; background: var(--card-bg);">No recommendations found matching those criteria. Try relaxing your year filters!</div>`;
            return;
        }

        let html = '';
        const conventionSelect = document.getElementById("conventionSelect");
        if (conventionSelect && conventionSelect.value) {
            const selectedText = conventionSelect.options[conventionSelect.selectedIndex].text;
            html += `
                <div style="grid-column: 1 / -1; display: flex; align-items: center; gap: 10px; margin-bottom: 20px; padding: 12px 18px; background: var(--info-bg); border: 1.5px solid var(--info-border); border-radius: 12px; width: 100%; box-sizing: border-box;">
                    <span style="display: inline-block; background-color: var(--primary); color: white; padding: 4px 8px; border-radius: 6px; font-size: 0.85rem; font-weight: bold; text-transform: uppercase; letter-spacing: 0.05em;">Convention Filter</span>
                    <span style="font-weight: 600; color: var(--text-main);">${selectedText}</span>
                </div>
            `;
        }

        recs.forEach((rec, index) => {
            html += window.renderRecommendationCard(rec, index, isPending);
        });
        resultsContainer.innerHTML = html;
    }

    function updateNarrationReasons(recs) {
        recs.forEach(rec => {
            const gameId = rec.id;
            if (!gameId) return;
            const reasonEl = document.querySelector(`.rec-reason[data-game-id="${gameId}"]`);
            if (reasonEl) {
                reasonEl.style.transition = "opacity 0.25s ease";
                reasonEl.style.opacity = "0";
                setTimeout(() => {
                    reasonEl.textContent = rec.reason;
                    reasonEl.classList.remove('loading');
                    reasonEl.style.opacity = "1";
                }, 250);
            }
        });
    }
});
