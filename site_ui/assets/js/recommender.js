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

    function getRecommendations(forceRefresh = false) {
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

        // Build unique cache key including weights, preferences and convention filter
        const cacheKey = `bgg_rec_${username.toLowerCase()}_${own_status}_${year_start || 'any'}_${year_end || 'any'}_${durationPref}_${complexityPref}_${convention_id || 'any'}_${w_mech}_${w_cat}_${w_pop}_${w_hot}`;
        activeSearchKey = cacheKey;

        // Check if fresh cache exists (TTL = 7 days)
        if (!forceRefresh) {
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
        } else {
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

        function pollRecommendations() {
            if (!isPollingActive) return;

            fetchApi(url)
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
                    } else if (data.status === "ready") {
                        statusCard.style.display = "none";
                        submitBtn.disabled = false;
                        if (refreshBtn) {
                            refreshBtn.disabled = false;
                        }
                        isPollingActive = false;

                        renderRecommendations(data.recommendations, false);

                        try {
                            const cacheVal = {
                                timestamp: Date.now(),
                                recommendations: data.recommendations
                            };
                            localStorage.setItem(cacheKey, JSON.stringify(cacheVal));
                        } catch (cacheErr) {
                            console.error("Error writing to cache:", cacheErr);
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
