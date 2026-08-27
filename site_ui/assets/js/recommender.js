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
                "id": "13",
                "name": "Catan",
                "image": "https://cf.geekdo-images.com/0XODRpReiZBFUffEcqT5-Q__original/img/oRc0AomWA9ZtFqQDZiZbIyKE1j0=/0x0/filters:format(png)/pic9156909.png",
                "mechanics": [
                        "Chaining",
                        "Dice Rolling",
                        "Hand Management",
                        "Hexagon Grid",
                        "Hidden Victory Points"
                ]
        },
        {
                "id": "9209",
                "name": "Ticket to Ride",
                "image": "https://cf.geekdo-images.com/kdWYkW-7AqG63HhqPL6ekA__original/img/rWF8r4JXXCQQ7QhiWHhmT-rQ3Pc=/0x0/filters:format(jpeg)/pic8937637.jpg",
                "mechanics": [
                        "Connections",
                        "Contracts",
                        "End Game Bonuses",
                        "Hand Management",
                        "Network and Route Building"
                ]
        },
        {
                "id": "30549",
                "name": "Pandemic",
                "image": "https://cf.geekdo-images.com/S3ybV1LAp-8SnHIXLLjVqA__original/img/IsrvRLpUV1TEyZsO5rC-btXaPz0=/0x0/filters:format(jpeg)/pic1534148.jpg",
                "mechanics": [
                        "Action Points",
                        "Chaining",
                        "Contracts",
                        "Cooperative Game",
                        "Events"
                ]
        },
        {
                "id": "178900",
                "name": "Codenames",
                "image": "https://cf.geekdo-images.com/nC6ifPCDnAItwoKSKXVrnw__original/img/Id-jjIer_61ZbvI2_RVRCeBZFY4=/0x0/filters:format(jpeg)/pic8907965.jpg",
                "mechanics": [
                        "Communication Limits",
                        "Deduction",
                        "Memory",
                        "Race",
                        "Team-Based Game"
                ]
        },
        {
                "id": "230802",
                "name": "Azul",
                "image": "https://cf.geekdo-images.com/aPSHJO0d0XOpQR5X-wJonw__original/img/AkbtYVc6xXJF3c9EUrakklcclKw=/0x0/filters:format(png)/pic6973671.png",
                "mechanics": [
                        "Chaining",
                        "End Game Bonuses",
                        "Grid Coverage",
                        "Open Drafting",
                        "Pattern Building"
                ]
        },
        {
                "id": "266192",
                "name": "Wingspan",
                "image": "https://cf.geekdo-images.com/yLZJCVLlIx4c7eJEWUNJ7w__original/img/cI782Zis9cT66j2MjSHKJGnFPNw=/0x0/filters:format(jpeg)/pic4458123.jpg",
                "mechanics": [
                        "Action Queue",
                        "Dice Rolling",
                        "End Game Bonuses",
                        "Hand Management",
                        "Once-Per-Game Abilities"
                ]
        },
        {
                "id": "363622",
                "name": "The Castles of Burgundy: Special Edition",
                "image": "https://cf.geekdo-images.com/JUrmY8GgFPQlENiPT7BGZw__original/img/whCMdZhta-uXHgNJfVnetnjZueU=/0x0/filters:format(jpeg)/pic6884563.jpg",
                "mechanics": [
                        "Dice Rolling",
                        "End Game Bonuses",
                        "Grid Movement",
                        "Set Collection",
                        "Solo / Solitaire Game"
                ]
        },
        {
                "id": "224517",
                "name": "Brass: Birmingham",
                "image": "https://cf.geekdo-images.com/x3zxjr-Vw5iU4yDPg70Jgw__original/img/FpyxH41Y6_ROoePAilPNEhXnzO8=/0x0/filters:format(jpeg)/pic3490053.jpg",
                "mechanics": [
                        "Chaining",
                        "End Game Bonuses",
                        "Hand Management",
                        "Income",
                        "Loans"
                ]
        },
        {
                "id": "342942",
                "name": "Ark Nova",
                "image": "https://cf.geekdo-images.com/SoU8p28Sk1s8MSvoM4N8pQ__original/img/g4S18szTdrXCdIwVKzMKrZrYAcM=/0x0/filters:format(jpeg)/pic6293412.jpg",
                "mechanics": [
                        "Contracts",
                        "End Game Bonuses",
                        "Events",
                        "Grid Coverage",
                        "Hand Management"
                ]
        },
        {
                "id": "161936",
                "name": "Pandemic Legacy: Season 1",
                "image": "https://cf.geekdo-images.com/-Qer2BBPG7qGGDu6KcVDIw__original/img/PlzAH7swN1nsFxOXbfUvE3TkE5w=/0x0/filters:format(png)/pic2452831.png",
                "mechanics": [
                        "Action Points",
                        "Cooperative Game",
                        "Hand Management",
                        "Legacy Game",
                        "Multi-Use Cards"
                ]
        },
        {
                "id": "174430",
                "name": "Gloomhaven",
                "image": "https://cf.geekdo-images.com/sZYp_3BTDGjh2unaZfZmuA__original/img/7d-lj5Gd1e8PFnD97LYFah2c45M=/0x0/filters:format(jpeg)/pic2437871.jpg",
                "mechanics": [
                        "Action Queue",
                        "Action Retrieval",
                        "Campaign / Battle Card Driven",
                        "Card Play Conflict Resolution",
                        "Communication Limits"
                ]
        },
        {
                "id": "397598",
                "name": "Dune: Imperium \u2013 Uprising",
                "image": "https://cf.geekdo-images.com/UVUkjMV_Q2paVUIUP30Vvw__original/img/BoUtCkd1NRO0bR1R5EwL51xIuXA=/0x0/filters:format(jpeg)/pic7664424.jpg",
                "mechanics": [
                        "Automatic Resource Growth",
                        "Card Play Conflict Resolution",
                        "Contracts",
                        "Deck, Bag, and Pool Building",
                        "Delayed Purchase"
                ]
        },
        {
                "id": "316554",
                "name": "Dune: Imperium",
                "image": "https://cf.geekdo-images.com/PhjygpWSo-0labGrPBMyyg__original/img/mZzaBAEEJpMlHWWmC0R6Su0OibQ=/0x0/filters:format(jpeg)/pic5666597.jpg",
                "mechanics": [
                        "Card Play Conflict Resolution",
                        "Deck, Bag, and Pool Building",
                        "Delayed Purchase",
                        "Force Commitment",
                        "Increase Value of Unchosen Resources"
                ]
        },
        {
                "id": "233078",
                "name": "Twilight Imperium: Fourth Edition",
                "image": "https://cf.geekdo-images.com/_Ppn5lssO5OaildSE-FgFA__original/img/kVpZ0Maa_LeQGWxOqsYKP3N4KUY=/0x0/filters:format(jpeg)/pic3727516.jpg",
                "mechanics": [
                        "Action Drafting",
                        "Area-Impulse",
                        "Dice Rolling",
                        "Follow",
                        "Grid Movement"
                ]
        },
        {
                "id": "115746",
                "name": "War of the Ring: Second Edition",
                "image": "https://cf.geekdo-images.com/ImPgGag98W6gpV1KV812aA__original/img/38jB7fN07DwlrGKYAf-J0vsNdgs=/0x0/filters:format(jpeg)/pic1215633.jpg",
                "mechanics": [
                        "Area Majority / Influence",
                        "Area Movement",
                        "Campaign / Battle Card Driven",
                        "Card Play Conflict Resolution",
                        "Dice Rolling"
                ]
        },
        {
                "id": "167791",
                "name": "Terraforming Mars",
                "image": "https://cf.geekdo-images.com/wg9oOLcsKvDesSUdZQ4rxw__original/img/thIqWDnH9utKuoKVEUqveDixprI=/0x0/filters:format(jpeg)/pic3536616.jpg",
                "mechanics": [
                        "Closed Drafting",
                        "Contracts",
                        "End Game Bonuses",
                        "Hand Management",
                        "Hexagon Grid"
                ]
        },
        {
                "id": "187645",
                "name": "Star Wars: Rebellion",
                "image": "https://cf.geekdo-images.com/7SrPNGBKg9IIsP4UQpOi8g__original/img/GKueTbkCk2Ramf6ai8mDj-BP6cI=/0x0/filters:format(jpeg)/pic4325841.jpg",
                "mechanics": [
                        "Area Majority / Influence",
                        "Area Movement",
                        "Card Play Conflict Resolution",
                        "Contracts",
                        "Delayed Purchase"
                ]
        },
        {
                "id": "162886",
                "name": "Spirit Island",
                "image": "https://cf.geekdo-images.com/kjCm4ZvPjIZxS-mYgSPy1g__original/img/9uLd9C3XAvInLCLhAoXqKVk56zs=/0x0/filters:format(jpeg)/pic7013651.jpg",
                "mechanics": [
                        "Action Retrieval",
                        "Area Majority / Influence",
                        "Automatic Resource Growth",
                        "Campaign / Battle Card Driven",
                        "Cooperative Game"
                ]
        },
        {
                "id": "291457",
                "name": "Gloomhaven: Jaws of the Lion",
                "image": "https://cf.geekdo-images.com/_HhIdavYW-hid20Iq3hhmg__original/img/PBzsLRqNKQKJxGnzpb7o3qLWPQM=/0x0/filters:format(jpeg)/pic5055631.jpg",
                "mechanics": [
                        "Action Queue",
                        "Action Retrieval",
                        "Campaign / Battle Card Driven",
                        "Communication Limits",
                        "Cooperative Game"
                ]
        },
        {
                "id": "220308",
                "name": "Gaia Project",
                "image": "https://cf.geekdo-images.com/hGWFm3hbMlCDsfCsauOQ4g__original/img/tjlflQtUPFiTpLpwk1NCVCS29Ic=/0x0/filters:format(png)/pic5375625.png",
                "mechanics": [
                        "End Game Bonuses",
                        "Hexagon Grid",
                        "Income",
                        "Modular Board",
                        "Network and Route Building"
                ]
        },
        {
                "id": "12333",
                "name": "Twilight Struggle",
                "image": "https://cf.geekdo-images.com/pNCiUUphnoeWOYfsWq0kng__original/img/Iae47UtAd_RXVd5tJ3YzbDHOv4E=/0x0/filters:format(jpeg)/pic3530661.jpg",
                "mechanics": [
                        "Action / Event",
                        "Advantage Token",
                        "Area Majority / Influence",
                        "Campaign / Battle Card Driven",
                        "Dice Rolling"
                ]
        },
        {
                "id": "418059",
                "name": "SETI: Search for Extraterrestrial Intelligence",
                "image": "https://cf.geekdo-images.com/_BUXOVRDU9g_eRwgpR5ZZw__original/img/28ob2JiASW8iX8XoVzp5Y25-h24=/0x0/filters:format(jpeg)/pic8160466.jpg",
                "mechanics": [
                        "Area Majority / Influence",
                        "End Game Bonuses",
                        "Income",
                        "Multi-Use Cards",
                        "Resource to Move"
                ]
        },
        {
                "id": "338960",
                "name": "Slay the Spire: The Board Game",
                "image": "https://cf.geekdo-images.com/PQzVclEoOQ_wr4e1V86kxA__original/img/KXOf1hP1cIJQLabKhZulWP-e9wI=/0x0/filters:format(png)/pic8157856.png",
                "mechanics": [
                        "Cooperative Game",
                        "Deck, Bag, and Pool Building",
                        "Dice Rolling",
                        "Hand Management",
                        "Simultaneous Action Selection"
                ]
        },
        {
                "id": "84876",
                "name": "The Castles of Burgundy",
                "image": "https://cf.geekdo-images.com/sH2YTQ10dHj1ibfS-KKtGA__original/img/L_gsMsuhbAe0kyq1QLAmyeKOeSs=/0x0/filters:format(jpeg)/pic8745814.jpg",
                "mechanics": [
                        "Delayed Purchase",
                        "Dice Rolling",
                        "End Game Bonuses",
                        "Grid Coverage",
                        "Hexagon Grid"
                ]
        },
        {
                "id": "271320",
                "name": "The Castles of Burgundy",
                "image": "https://cf.geekdo-images.com/EXvERyhT9ta6LrPR0Un7wA__original/img/-OPQd4l4QQL1y4NB08IV7euVQbA=/0x0/filters:format(jpeg)/pic8573872.jpg",
                "mechanics": [
                        "Dice Rolling",
                        "End Game Bonuses",
                        "Grid Coverage",
                        "Hexagon Grid",
                        "Pattern Building"
                ]
        },
        {
                "id": "182028",
                "name": "Through the Ages: A New Story of Civilization",
                "image": "https://cf.geekdo-images.com/fVwPntkJKgaEo0rIC0RwpA__original/img/1jawNpljTXwnT4km_2CjGwoUPR8=/0x0/filters:format(jpeg)/pic2663291.jpg",
                "mechanics": [
                        "Action Points",
                        "Auction / Bidding",
                        "Auction: Dutch",
                        "Events",
                        "Income"
                ]
        },
        {
                "id": "421006",
                "name": "The Lord of the Rings: Duel for Middle-earth",
                "image": "https://cf.geekdo-images.com/EybxJlUc9rz7F7HVFLqsdw__original/img/Ts4M5eOW38r2oTvJmkx0uwNodv4=/0x0/filters:format(jpeg)/pic8378939.jpg",
                "mechanics": [
                        "Area Majority / Influence",
                        "Hand Management",
                        "Income",
                        "Layering",
                        "Market"
                ]
        },
        {
                "id": "248562",
                "name": "Mage Knight: Ultimate Edition",
                "image": "https://cf.geekdo-images.com/jgsT5y5qKlOR08CuHG7xfw__original/img/mnPgX4nM_l1JnXFE16dAZjGS8sw=/0x0/filters:format(jpeg)/pic4411189.jpg",
                "mechanics": [
                        "Card Play Conflict Resolution",
                        "Cooperative Game",
                        "Deck, Bag, and Pool Building",
                        "Dice Rolling",
                        "Grid Movement"
                ]
        },
        {
                "id": "295770",
                "name": "Frosthaven",
                "image": "https://cf.geekdo-images.com/cwUgf-f-qwri8UHBUnifuQ__original/img/Tk7wFDJuaU8RPjNkmyC3AWYOPpU=/0x0/filters:format(png)/pic5092291.png",
                "mechanics": [
                        "Campaign / Battle Card Driven",
                        "Communication Limits",
                        "Cooperative Game",
                        "Deck Construction",
                        "Deck, Bag, and Pool Building"
                ]
        },
        {
                "id": "193738",
                "name": "Great Western Trail",
                "image": "https://cf.geekdo-images.com/u1l0gH7sb_vnvDvoO_QHqA__original/img/2zv_XMQoPFWk9Dn0oS4JY1IeFzw=/0x0/filters:format(jpeg)/pic4887376.jpg",
                "mechanics": [
                        "Contracts",
                        "Deck, Bag, and Pool Building",
                        "Hand Management",
                        "Income",
                        "Ownership"
                ]
        },
        {
                "id": "28720",
                "name": "Brass: Lancashire",
                "image": "https://cf.geekdo-images.com/tHVtPzu82mBpeQbbZkV6EA__original/img/3ffdJj5Pz6HQrg09Kh8ecTen-TY=/0x0/filters:format(jpeg)/pic3469216.jpg",
                "mechanics": [
                        "Chaining",
                        "End Game Bonuses",
                        "Hand Management",
                        "Income",
                        "Loans"
                ]
        },
        {
                "id": "246900",
                "name": "Eclipse: Second Dawn for the Galaxy",
                "image": "https://cf.geekdo-images.com/Oh3kHw6lweg6ru71Q16h2Q__original/img/yW7d4RNfU1ndISCaPlfGYUyxnRU=/0x0/filters:format(jpeg)/pic5235277.jpg",
                "mechanics": [
                        "Alliances",
                        "Area Majority / Influence",
                        "Area-Impulse",
                        "Dice Rolling",
                        "Grid Movement"
                ]
        },
        {
                "id": "173346",
                "name": "7 Wonders Duel",
                "image": "https://cf.geekdo-images.com/zdagMskTF7wJBPjX74XsRw__original/img/Ju836WNSaW7Mab9Vjq2TJ_FqhWQ=/0x0/filters:format(jpeg)/pic2576399.jpg",
                "mechanics": [
                        "End Game Bonuses",
                        "Income",
                        "Melding and Splaying",
                        "Modular Board",
                        "Multi-Use Cards"
                ]
        },
        {
                "id": "167355",
                "name": "Nemesis",
                "image": "https://cf.geekdo-images.com/4KSmlm59w0GwLIlgDnJDAQ__original/img/f0VmAKrPrMRQOUcOJHekRvuysDE=/0x0/filters:format(png)/pic8211747.png",
                "mechanics": [
                        "Campaign / Battle Card Driven",
                        "Cooperative Game",
                        "Dice Rolling",
                        "Hand Management",
                        "Hidden Roles"
                ]
        },
        {
                "id": "169786",
                "name": "Scythe",
                "image": "https://cf.geekdo-images.com/7k_nOxpO9OGIjhLq2BUZdA__original/img/HlDb9F365w0tSP8uD1vf1pfniQE=/0x0/filters:format(jpeg)/pic3163924.jpg",
                "mechanics": [
                        "Area Majority / Influence",
                        "Card Play Conflict Resolution",
                        "Contracts",
                        "End Game Bonuses",
                        "Force Commitment"
                ]
        },
        {
                "id": "177736",
                "name": "A Feast for Odin",
                "image": "https://cf.geekdo-images.com/s9oGMCo1fcfV4Dk3EnqLZw__original/img/N1X-0JB1GapFVhl98nP4tNFXMcM=/0x0/filters:format(png)/pic3146943.png",
                "mechanics": [
                        "Action Points",
                        "Automatic Resource Growth",
                        "Dice Rolling",
                        "Enclosure",
                        "Grid Coverage"
                ]
        },
        {
                "id": "266507",
                "name": "Clank! Legacy: Acquisitions Incorporated",
                "image": "https://cf.geekdo-images.com/hc2NDafu5c24iLJh_IZmyg__original/img/1Fpyz7j7rTvMPRiDdPjn0Vf0m2k=/0x0/filters:format(png)/pic4885780.png",
                "mechanics": [
                        "Deck, Bag, and Pool Building",
                        "Delayed Purchase",
                        "End Game Bonuses",
                        "Events",
                        "Legacy Game"
                ]
        },
        {
                "id": "124361",
                "name": "Concordia",
                "image": "https://cf.geekdo-images.com/CzwSm8i7tkLz6cBnrILZBg__original/img/BhJ3sB3uk-eSdR1iW4EP3cu0Wi0=/0x0/filters:format(jpeg)/pic3453267.jpg",
                "mechanics": [
                        "Action Retrieval",
                        "Advantage Token",
                        "Auction: Dutch",
                        "Deck, Bag, and Pool Building",
                        "End Game Bonuses"
                ]
        },
        {
                "id": "312484",
                "name": "Lost Ruins of Arnak",
                "image": "https://cf.geekdo-images.com/6GqH14TJJhza86BX5HCLEQ__original/img/CXqwimJPonWy1oyXEMgPN_ZVmUI=/0x0/filters:format(jpeg)/pic5674958.jpg",
                "mechanics": [
                        "Area Movement",
                        "Contracts",
                        "Deck, Bag, and Pool Building",
                        "Delayed Purchase",
                        "End Game Bonuses"
                ]
        },
        {
                "id": "341169",
                "name": "Great Western Trail: Second Edition",
                "image": "https://cf.geekdo-images.com/gDn7AhrDlmfCLSz9ZqoNFQ__original/img/yecB1xO32nnjBAyskVOTq9LBuLo=/0x0/filters:format(jpeg)/pic5988511.jpg",
                "mechanics": [
                        "Deck, Bag, and Pool Building",
                        "Hand Management",
                        "Ownership",
                        "Set Collection",
                        "Solo / Solitaire Game"
                ]
        },
        {
                "id": "373106",
                "name": "Sky Team",
                "image": "https://cf.geekdo-images.com/uXMeQzNenHb3zK7Hoa6b2w__original/img/mWOQnkpyYBorh_Y1-0Y2o-ew17k=/0x0/filters:format(jpeg)/pic7398904.jpg",
                "mechanics": [
                        "Communication Limits",
                        "Cooperative Game",
                        "Dice Rolling",
                        "Scenario / Mission / Campaign Game",
                        "Turn Order: Progressive"
                ]
        },
        {
                "id": "205637",
                "name": "Arkham Horror: The Card Game",
                "image": "https://cf.geekdo-images.com/B5F5ulz0UivNgrI9Ky0euA__original/img/guEKCewM_2e5ugltSN3dTSwdZJI=/0x0/filters:format(jpeg)/pic3122349.jpg",
                "mechanics": [
                        "Action Points",
                        "Area Movement",
                        "Communication Limits",
                        "Cooperative Game",
                        "Deck Construction"
                ]
        },
        {
                "id": "237182",
                "name": "Root",
                "image": "https://cf.geekdo-images.com/JUAUWaVUzeBgzirhZNmHHw__original/img/E0s2LvtFA1L5YKk-_44D4u2VD2s=/0x0/filters:format(jpeg)/pic4254509.jpg",
                "mechanics": [
                        "Action Points",
                        "Action Queue",
                        "Action Retrieval",
                        "Area Majority / Influence",
                        "Area Movement"
                ]
        },
        {
                "id": "164928",
                "name": "Orl\u00e9ans",
                "image": "https://cf.geekdo-images.com/nagl1li6kYt9elV9jbfVQw__original/img/Qn6vlBaTUaHNFsqohIUjd0EA4z0=/0x0/filters:format(jpeg)/pic6228507.jpg",
                "mechanics": [
                        "Contracts",
                        "Deck, Bag, and Pool Building",
                        "End Game Bonuses",
                        "Events",
                        "Kill Steal"
                ]
        },
        {
                "id": "120677",
                "name": "Terra Mystica",
                "image": "https://cf.geekdo-images.com/bre12I1YiXkZr7elvriz4A__original/img/_dZS7fVfdc4DhJPbqnDpwTT4uF0=/0x0/filters:format(jpeg)/pic5375624.jpg",
                "mechanics": [
                        "Chaining",
                        "End Game Bonuses",
                        "Hexagon Grid",
                        "Income",
                        "Increase Value of Unchosen Resources"
                ]
        },
        {
                "id": "192135",
                "name": "Too Many Bones",
                "image": "https://cf.geekdo-images.com/wKwRk0wYBcrtLAfgn4PCdg__original/img/Wpp0vzsVe4HxXGUqiZ1hDvwAHZU=/0x0/filters:format(png)/pic6624445.png",
                "mechanics": [
                        "Cooperative Game",
                        "Dice Rolling",
                        "Die Icon Resolution",
                        "Grid Movement",
                        "Narrative Choice / Paragraph"
                ]
        },
        {
                "id": "251247",
                "name": "Barrage",
                "image": "https://cf.geekdo-images.com/jEPmWvvYpqkWrKOzqIHFsg__original/img/rkHKwkUqpQC7PAGG7n2gbrcQiUY=/0x0/filters:format(png)/pic4336469.png",
                "mechanics": [
                        "Contracts",
                        "End Game Bonuses",
                        "Income",
                        "Network and Route Building",
                        "Ownership"
                ]
        },
        {
                "id": "96848",
                "name": "Mage Knight Board Game",
                "image": "https://cf.geekdo-images.com/DUO2hz9AlLOH8p9ED-lCWg__original/img/PDDH38Vf9NEB_4ODURxcJKNBfVQ=/0x0/filters:format(jpeg)/pic1083380.jpg",
                "mechanics": [
                        "Card Play Conflict Resolution",
                        "Cooperative Game",
                        "Deck, Bag, and Pool Building",
                        "Dice Rolling",
                        "Grid Movement"
                ]
        },
        {
                "id": "321608",
                "name": "Hegemony: Lead Your Class to Victory",
                "image": "https://cf.geekdo-images.com/DCLgJlrvB-EqL6A3WgQLMQ__original/img/vGpYcxjDBCOVcI0BcWOevspTQMQ=/0x0/filters:format(jpeg)/pic5715770.jpg",
                "mechanics": [
                        "Action / Event",
                        "Hand Management",
                        "Simulation",
                        "Variable Player Powers",
                        "Voting"
                ]
        },
        {
                "id": "284378",
                "name": "Kanban EV",
                "image": "https://cf.geekdo-images.com/L2Wn-zUqkcHgqvwvY212Ig__original/img/Htra4hvxjBlejtNEIUns_B3CNNc=/0x0/filters:format(jpeg)/pic4924232.jpg",
                "mechanics": [
                        "Action Points",
                        "Hand Management",
                        "Variable Phase Order",
                        "Worker Placement"
                ]
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

    // ==========================================
    // AUTOCOMPLETE COMPONENT FOR GAME SEARCH
    // ==========================================
    let gameNamesCache = null;
    let isFetchingGameNames = false;
    let gameNamesFetchPromise = null;

    async function getGameNames() {
        if (gameNamesCache) return gameNamesCache;
        if (gameNamesFetchPromise) return gameNamesFetchPromise;

        const url = window.BGG_GAME_NAMES_URL || "/Boardgame-Recommender/assets/data/game_names.json";
        isFetchingGameNames = true;
        gameNamesFetchPromise = fetch(url)
            .then(res => {
                if (!res.ok) throw new Error("Failed loading game_names.json: " + res.status);
                return res.json();
            })
            .then(data => {
                gameNamesCache = data;
                isFetchingGameNames = false;
                return gameNamesCache;
            })
            .catch(err => {
                console.error("Autocomplete game list fetch error:", err);
                isFetchingGameNames = false;
                gameNamesFetchPromise = null;
                return [];
            });
        return gameNamesFetchPromise;
    }

    function initGameAutocomplete(inputEl, dropdownEl, clearBtnEl) {
        if (!inputEl || !dropdownEl) return;
        if (inputEl._autocompleteInitialized) return;
        inputEl._autocompleteInitialized = true;

        let debounceTimer = null;
        let highlightedIndex = -1;
        let currentMatches = [];

        // Pre-fetch on focus
        inputEl.addEventListener("focus", () => {
            getGameNames();
        });

        function renderDropdown(matches, query) {
            dropdownEl.innerHTML = "";
            highlightedIndex = -1;
            currentMatches = matches;

            if (!matches || matches.length === 0) {
                dropdownEl.classList.remove("active");
                return;
            }

            const lowerQuery = query.toLowerCase();
            matches.forEach((item, idx) => {
                const itemEl = document.createElement("div");
                itemEl.className = "autocomplete-item";
                
                // Highlight query substring
                const nameLower = item.name.toLowerCase();
                const matchPos = nameLower.indexOf(lowerQuery);
                if (matchPos >= 0) {
                    const before = item.name.substring(0, matchPos);
                    const matchText = item.name.substring(matchPos, matchPos + query.length);
                    const after = item.name.substring(matchPos + query.length);
                    itemEl.innerHTML = `<span>${escapeHtml(before)}<mark>${escapeHtml(matchText)}</mark>${escapeHtml(after)}</span>`;
                } else {
                    itemEl.textContent = item.name;
                }

                itemEl.addEventListener("mousedown", (e) => {
                    e.preventDefault(); // Prevent blur before selection
                    selectItem(item);
                });

                dropdownEl.appendChild(itemEl);
            });

            dropdownEl.classList.add("active");
        }

        function selectItem(item) {
            inputEl.value = item.name;
            inputEl.dataset.gameId = item.id;
            inputEl.classList.add("locked");
            if (clearBtnEl) clearBtnEl.style.display = "flex";
            dropdownEl.classList.remove("active");
            dropdownEl.innerHTML = "";
            currentMatches = [];
            highlightedIndex = -1;
        }

        function clearSelection() {
            inputEl.value = "";
            delete inputEl.dataset.gameId;
            inputEl.classList.remove("locked");
            if (clearBtnEl) clearBtnEl.style.display = "none";
            dropdownEl.classList.remove("active");
            dropdownEl.innerHTML = "";
            currentMatches = [];
            highlightedIndex = -1;
            inputEl.focus();
        }

        if (clearBtnEl) {
            clearBtnEl.addEventListener("click", (e) => {
                e.preventDefault();
                clearSelection();
            });
        }

        inputEl.addEventListener("input", () => {
            const query = inputEl.value.trim();
            delete inputEl.dataset.gameId;
            inputEl.classList.remove("locked");
            if (clearBtnEl) clearBtnEl.style.display = query.length > 0 ? "flex" : "none";

            if (debounceTimer) clearTimeout(debounceTimer);

            if (query.length < 2) {
                dropdownEl.classList.remove("active");
                dropdownEl.innerHTML = "";
                currentMatches = [];
                return;
            }

            debounceTimer = setTimeout(async () => {
                const list = await getGameNames();
                if (!list || list.length === 0) return;

                const lowerQuery = query.toLowerCase();
                const prefixMatches = [];
                const substringMatches = [];

                for (let i = 0; i < list.length; i++) {
                    const item = list[i];
                    const nameLower = item.name.toLowerCase();
                    if (nameLower.startsWith(lowerQuery)) {
                        prefixMatches.push(item);
                    } else if (nameLower.includes(lowerQuery)) {
                        substringMatches.push(item);
                    }
                    if (prefixMatches.length >= 8) break;
                }

                const combined = prefixMatches.concat(substringMatches).slice(0, 8);
                renderDropdown(combined, query);
            }, 150);
        });

        inputEl.addEventListener("keydown", (e) => {
            const items = dropdownEl.querySelectorAll(".autocomplete-item");
            if (e.key === "ArrowDown") {
                if (items.length > 0) {
                    e.preventDefault();
                    highlightedIndex = (highlightedIndex + 1) % items.length;
                    updateHighlight(items);
                }
            } else if (e.key === "ArrowUp") {
                if (items.length > 0) {
                    e.preventDefault();
                    highlightedIndex = (highlightedIndex - 1 + items.length) % items.length;
                    updateHighlight(items);
                }
            } else if (e.key === "Enter") {
                if (highlightedIndex >= 0 && highlightedIndex < currentMatches.length) {
                    e.preventDefault();
                    selectItem(currentMatches[highlightedIndex]);
                }
            } else if (e.key === "Escape") {
                dropdownEl.classList.remove("active");
            }
        });

        function updateHighlight(items) {
            items.forEach((it, idx) => {
                if (idx === highlightedIndex) {
                    it.classList.add("highlighted");
                    it.scrollIntoView({ block: "nearest" });
                } else {
                    it.classList.remove("highlighted");
                }
            });
        }

        document.addEventListener("click", (e) => {
            if (!inputEl.contains(e.target) && !dropdownEl.contains(e.target)) {
                dropdownEl.classList.remove("active");
            }
        });
    }

    function escapeHtml(str) {
        return str
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
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

                // Populate liked games summary & write-in fields
                const likedGames = tasteRatings.filter(r => r.rating === 9.0);
                let summaryHtml = "";
                if (likedGames.length > 0) {
                    summaryHtml += `
                        <div class="liked-games-summary" style="margin-top: 5px; margin-bottom: 15px; text-align: left; background: rgba(255,255,255,0.03); border: 1px solid var(--border); border-radius: 12px; padding: 16px; animation: fadeIn 0.3s ease;">
                            <h3 style="margin-top: 0; margin-bottom: 10px; font-size: 1.05rem; display: flex; align-items: center; gap: 8px; font-family: 'Outfit', sans-serif;">
                                <span style="font-size: 1.2rem;">👍</span> Your Saved Liked Games (${likedGames.length})
                            </h3>
                            <div class="liked-games-list" style="display: flex; flex-direction: column; gap: 6px; max-height: 160px; overflow-y: auto;">
                    `;
                    likedGames.forEach(liked => {
                        const seedGame = SEED_CATALOG.find(g => g.id === liked.id);
                        if (seedGame) {
                            summaryHtml += `
                                <div style="display: flex; align-items: center; gap: 12px; padding: 5px 10px; background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); border-radius: 6px;">
                                    <img src="${seedGame.image}" alt="${seedGame.name}" style="width: 28px; height: 28px; object-fit: cover; border-radius: 4px;">
                                    <span style="font-weight: 600; font-size: 0.9rem; color: var(--text-main);">${seedGame.name}</span>
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
                        <div class="liked-games-summary" style="margin-top: 5px; margin-bottom: 15px; text-align: center; background: rgba(255,255,255,0.03); border: 1px solid var(--border); border-radius: 12px; padding: 14px; animation: fadeIn 0.3s ease;">
                            <p style="margin: 0; color: var(--text-muted); font-size: 0.9rem;">You didn't thumbs-up any games in the test.</p>
                        </div>
                    `;
                }

                // Add write-in section
                summaryHtml += `
                    <div class="taste-test-writein-section">
                        <h3 style="margin-top: 0; margin-bottom: 4px; font-size: 1.05rem; font-family: 'Outfit', sans-serif; display: flex; align-items: center; gap: 8px;">
                            <span>Add More Favorite Games</span>
                        </h3>
                        <p style="margin: 0 0 14px 0; font-size: 0.85rem; color: var(--text-muted);">
                            Optionally type up to 3 more board games you love to further customize your recommendations:
                        </p>
                        <div class="wizard-writein-container" style="margin-bottom: 0;">
                            <div class="wizard-writein-group">
                                <label for="taste-writein-1">Favorite Game 1 <span class="optional-badge">Optional</span></label>
                                <div class="autocomplete-wrapper">
                                    <input type="text" id="taste-writein-1" class="wizard-writein-input" placeholder="e.g. Terraforming Mars..." autocomplete="off">
                                    <button type="button" class="autocomplete-clear-btn" style="display: none;" title="Clear">&times;</button>
                                    <div class="autocomplete-dropdown" id="taste-writein-1-dropdown"></div>
                                </div>
                            </div>
                            <div class="wizard-writein-group">
                                <label for="taste-writein-2">Favorite Game 2 <span class="optional-badge">Optional</span></label>
                                <div class="autocomplete-wrapper">
                                    <input type="text" id="taste-writein-2" class="wizard-writein-input" placeholder="e.g. Scythe..." autocomplete="off">
                                    <button type="button" class="autocomplete-clear-btn" style="display: none;" title="Clear">&times;</button>
                                    <div class="autocomplete-dropdown" id="taste-writein-2-dropdown"></div>
                                </div>
                            </div>
                            <div class="wizard-writein-group">
                                <label for="taste-writein-3">Favorite Game 3 <span class="optional-badge">Optional</span></label>
                                <div class="autocomplete-wrapper">
                                    <input type="text" id="taste-writein-3" class="wizard-writein-input" placeholder="e.g. 7 Wonders Duel..." autocomplete="off">
                                    <button type="button" class="autocomplete-clear-btn" style="display: none;" title="Clear">&times;</button>
                                    <div class="autocomplete-dropdown" id="taste-writein-3-dropdown"></div>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
                
                if (summaryContainer) {
                    summaryContainer.innerHTML = summaryHtml;
                    summaryContainer.style.display = "block";

                    // Bind autocomplete to taste write-in inputs
                    [1, 2, 3].forEach(num => {
                        const inputEl = document.getElementById(`taste-writein-${num}`);
                        const dropdownEl = document.getElementById(`taste-writein-${num}-dropdown`);
                        const clearBtnEl = inputEl ? inputEl.parentElement.querySelector(".autocomplete-clear-btn") : null;
                        if (inputEl && dropdownEl) {
                            initGameAutocomplete(inputEl, dropdownEl, clearBtnEl);
                        }
                    });
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

        const round2Games = remainingGames.slice(0, 9);
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
        
        // Collect any write-in games from summary screen
        [1, 2, 3].forEach(num => {
            const inputEl = document.getElementById(`taste-writein-${num}`);
            if (inputEl && inputEl.dataset.gameId) {
                const writeInId = inputEl.dataset.gameId;
                tasteRatings = tasteRatings.filter(r => r.id !== writeInId);
                tasteRatings.push({ id: writeInId, rating: 9.0 });
            }
        });

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
        // Reset personality write-in inputs
        [1, 2, 3].forEach(num => {
            const inputEl = document.getElementById(`personality-writein-${num}`);
            if (inputEl) {
                inputEl.value = "";
                delete inputEl.dataset.gameId;
                inputEl.classList.remove("locked");
                const clearBtn = inputEl.parentElement.querySelector(".autocomplete-clear-btn");
                if (clearBtn) clearBtn.style.display = "none";
            }
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

        if (personalityIndex <= 7) {
            const progressPct = (personalityIndex / 7) * 100;
            if (personalityProgressBar) personalityProgressBar.style.width = `${progressPct}%`;
            if (personalityProgressText) personalityProgressText.textContent = `Question ${personalityIndex} of 7`;
        } else {
            if (personalityProgressBar) personalityProgressBar.style.width = `100%`;
            if (personalityProgressText) personalityProgressText.textContent = `Step 2 of 2: Add Favorite Games (Optional)`;
        }

        checkQuestionAnswered();

        if (personalityIndex === 8) {
            if (personalityNextBtn) personalityNextBtn.style.display = "none";
            if (personalityRecommendBtn) {
                personalityRecommendBtn.style.display = "inline-flex";
                personalityRecommendBtn.disabled = false;
            }

            // Bind autocomplete inputs for slide 8
            [1, 2, 3].forEach(num => {
                const inputEl = document.getElementById(`personality-writein-${num}`);
                const dropdownEl = document.getElementById(`personality-writein-${num}-dropdown`);
                const clearBtnEl = inputEl ? inputEl.parentElement.querySelector(".autocomplete-clear-btn") : null;
                if (inputEl && dropdownEl) {
                    initGameAutocomplete(inputEl, dropdownEl, clearBtnEl);
                }
            });
        } else {
            if (personalityNextBtn) personalityNextBtn.style.display = "inline-flex";
            if (personalityRecommendBtn) personalityRecommendBtn.style.display = "none";
        }
    }

    function checkQuestionAnswered() {
        if (personalityIndex === 8) {
            if (personalityRecommendBtn) personalityRecommendBtn.disabled = false;
            return;
        }

        const activeSlide = document.querySelector(".personality-question-slide.active");
        if (!activeSlide) return;

        const inputs = activeSlide.querySelectorAll("input[type='radio']");
        let answered = false;
        inputs.forEach(input => {
            if (input.checked) answered = true;
        });

        if (personalityNextBtn) personalityNextBtn.disabled = !answered;
    }

    document.querySelectorAll(".personality-option-card input[type='radio']").forEach(radio => {
        radio.addEventListener("change", checkQuestionAnswered);
    });

    if (personalityNextBtn) personalityNextBtn.addEventListener("click", () => {
        if (personalityIndex < 8) {
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

        // Collect write-in games from slide 8
        const inlineProfile = [];
        [1, 2, 3].forEach(num => {
            const inputEl = document.getElementById(`personality-writein-${num}`);
            if (inputEl && inputEl.dataset.gameId) {
                inlineProfile.push({ id: inputEl.dataset.gameId, rating: 9.0 });
            }
        });

        const profileToSend = inlineProfile.length > 0 ? inlineProfile : null;
        syncManualPreferencesToBackend(profileToSend, inlineWeights);
        getRecommendations(true, profileToSend, inlineWeights);
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
