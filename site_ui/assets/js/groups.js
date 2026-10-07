---
layout: null
---
document.addEventListener("DOMContentLoaded", function () {
        // Elements
        const showCreateFormBtn = document.getElementById("show-create-form-btn");
        const groupFormCard = document.getElementById("group-form-card");
        const groupForm = document.getElementById("group-form");
        const cancelFormBtn = document.getElementById("cancel-form-btn");
        const groupNameInput = document.getElementById("group-name-input");
        const groupMembersInput = document.getElementById("group-members-input");
        const editGroupId = document.getElementById("edit-group-id");
        const saveGroupBtn = document.getElementById("save-group-btn");
        const formTitle = document.getElementById("form-title");
        const groupListContainer = document.getElementById("group-list-container");

        const plannerActiveView = document.getElementById("planner-active-view");
        const plannerEmptyState = document.getElementById("planner-empty-state");
        const activeGroupName = document.getElementById("active-group-name");
        const selectAllBtn = document.getElementById("selectAll-btn") || document.getElementById("select-all-btn");
        const selectNoneBtn = document.getElementById("select-none-btn");
        const memberCheckboxesContainer = document.getElementById("member-checkboxes-container");
        const attendanceCountBadge = document.getElementById("attendance-count-badge");
        const generatePlanBtn = document.getElementById("generate-plan-btn");
        const statusCard = document.getElementById("status-card");
        const statusMessage = document.getElementById("status-message");
        const resultsContainer = document.getElementById("recommendations-results");

        // Weights Sliders
        const weightsToggleBar = document.getElementById("weights-toggle-bar");
        const weightsExpandableContent = document.getElementById("weights-expandable-content");
        const weightsCaret = document.getElementById("weights-caret");

        const wMechInput = document.getElementById("w_mech");
        const wCatInput = document.getElementById("w_cat");
        const wPopInput = document.getElementById("w_pop");
        const wHotInput = document.getElementById("w_hot");

        const wMechVal = document.getElementById("w_mech_val");
        const wCatVal = document.getElementById("w_cat_val");
        const wPopVal = document.getElementById("w_pop_val");
        const wHotVal = document.getElementById("w_hot_val");

        // API Endpoint setup
        const apiUrl = "{{ site.api_url }}";
        let activeGroup = null;
        let isPollingActive = false;
        let pollingTimeout = null;

        // Playgroup caching and chart objects
        const collectionXmlCache = {};
        const attendeeProfileCache = {};
        let chartGroupMechanics = null;
        let chartGroupCategories = null;
        let chartGroupComplexity = null;
        let chartGroupDurations = null;

        // Chart.js Theme Defaults & Dynamic Theme Updating
        function updateChartTheme() {
            const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
            const textColor = isDark ? '#f8fafc' : '#0f172a';
            const mutedColor = isDark ? '#94a3b8' : '#64748b';
            const gridColor = isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(15, 23, 42, 0.08)';

            if (typeof Chart !== 'undefined') {
                Chart.defaults.color = mutedColor;
                Chart.defaults.font.family = "'Outfit', 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
                Chart.defaults.font.size = 11;
                Chart.defaults.plugins.tooltip.backgroundColor = isDark ? "rgba(15, 23, 42, 0.95)" : "rgba(15, 23, 42, 0.9)";
                Chart.defaults.plugins.tooltip.titleFont = { family: "'Outfit', sans-serif", weight: 'bold' };
                Chart.defaults.plugins.tooltip.bodyFont = { family: "'Inter', sans-serif" };
                Chart.defaults.plugins.tooltip.padding = 8;
                Chart.defaults.plugins.tooltip.cornerRadius = 6;
            }

            const activeCharts = [chartGroupMechanics, chartGroupCategories, chartGroupComplexity, chartGroupDurations];
            activeCharts.forEach(chart => {
                if (chart) {
                    if (chart.options.scales) {
                        Object.keys(chart.options.scales).forEach(scaleKey => {
                            const scale = chart.options.scales[scaleKey];
                            if (scale.ticks) {
                                scale.ticks.color = mutedColor;
                            }
                            if (scale.grid) {
                                scale.grid.color = gridColor;
                            }
                            if (scale.angleLines) {
                                scale.angleLines.color = gridColor;
                            }
                            if (scale.pointLabels) {
                                scale.pointLabels.color = textColor;
                            }
                        });
                    }
                    if (chart.options.plugins && chart.options.plugins.legend) {
                        if (!chart.options.plugins.legend.labels) chart.options.plugins.legend.labels = {};
                        chart.options.plugins.legend.labels.color = textColor;
                    }
                    chart.update();
                }
            });
        }

        if (typeof Chart !== 'undefined') {
            updateChartTheme();
        }

        const themeObserver = new MutationObserver(updateChartTheme);
        themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

        // 1. Saved groups crud (stored in localStorage)
        let playgroups = [];
        try {
            const stored = localStorage.getItem("bgg_playgroups");
            if (stored) playgroups = JSON.parse(stored);
        } catch (e) {
            console.error("Failed loading playgroups from local storage:", e);
        }

        function renderGroupList() {
            if (playgroups.length === 0) {
                groupListContainer.innerHTML = `<div style="text-align: center; color: var(--text-muted); font-size: 0.85rem; padding: 20px; border: 1px dashed var(--border); border-radius: 8px;">No playgroups saved. Create one above!</div>`;
                return;
            }

            let html = "";
            playgroups.forEach(g => {
                const isActive = activeGroup && activeGroup.id === g.id;
                html += `
                    <div class="group-item ${isActive ? 'active' : ''}" data-id="${g.id}" onclick="selectGroup('${g.id}')">
                        <div class="group-info">
                            <span class="group-name">${escapeHTML(g.name)}</span>
                            <span class="group-meta">${g.members.length} members</span>
                        </div>
                        <div class="group-actions">
                            <button class="group-action-btn" onclick="event.stopPropagation(); editGroup('${g.id}')" title="Edit Group">✎</button>
                            <button class="group-action-btn delete" onclick="event.stopPropagation(); deleteGroup('${g.id}')" title="Delete Group">🗑</button>
                        </div>
                    </div>
                `;
            });
            groupListContainer.innerHTML = html;
        }

        function getMemberAvatarColor(name) {
            const palette = [
                'linear-gradient(135deg, #6366f1, #4f46e5)', // Indigo
                'linear-gradient(135deg, #3b82f6, #1d4ed8)', // Blue
                'linear-gradient(135deg, #0ea5e9, #0284c7)', // Sky
                'linear-gradient(135deg, #10b981, #059669)', // Emerald
                'linear-gradient(135deg, #14b8a6, #0f766e)', // Teal
                'linear-gradient(135deg, #8b5cf6, #6d28d9)', // Purple
                'linear-gradient(135deg, #ec4899, #be185d)', // Pink
                'linear-gradient(135deg, #f59e0b, #d97706)', // Amber
                'linear-gradient(135deg, #f97316, #c2410c)', // Orange
            ];
            let hash = 0;
            for (let i = 0; i < name.length; i++) {
                hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
            }
            return palette[hash % palette.length];
        }

        window.selectGroup = function (id) {
            // Cancel any active polling
            isPollingActive = false;
            if (pollingTimeout) clearTimeout(pollingTimeout);
            statusCard.style.display = "none";
            resultsContainer.innerHTML = "";

            // Reset active tab to Recommendations
            if (window.switchTab) {
                window.switchTab("recommendations");
            }

            activeGroup = playgroups.find(g => g.id === id);
            renderGroupList(); // Update active highlights

            if (activeGroup) {
                plannerEmptyState.style.display = "none";
                plannerActiveView.style.display = "block";
                activeGroupName.textContent = activeGroup.name;

                const activeGroupMemberCount = document.getElementById("active-group-member-count");
                if (activeGroupMemberCount) {
                    const count = activeGroup.members ? activeGroup.members.length : 0;
                    activeGroupMemberCount.textContent = `${count} member${count !== 1 ? 's' : ''}`;
                }

                // Load interactive member avatar chips
                let html = "";
                activeGroup.members.forEach(member => {
                    const safeMember = escapeHTML(member);
                    const safeId = escapeHTML(member.toLowerCase());
                    const initial = safeMember.trim().charAt(0).toUpperCase() || '?';
                    const avatarColor = getMemberAvatarColor(member);
                    html += `
                        <label class="member-chip active checked" id="label-for-${safeId}" data-username="${safeMember}" title="Toggle attendance for ${safeMember}">
                            <input type="checkbox" class="member-checkbox visually-hidden" value="${safeMember}" checked onchange="toggleMemberChecked('${safeId}')">
                            <span class="chip-avatar" style="background: ${avatarColor};">${initial}</span>
                            <span class="chip-username">${safeMember}</span>
                            <span class="chip-indicator" aria-hidden="true">
                                <svg class="chip-check-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                                    <polyline points="20 6 9 17 4 12"></polyline>
                                </svg>
                            </span>
                        </label>
                    `;
                });
                memberCheckboxesContainer.innerHTML = html;
                updateAttendanceCount();
                updateGroupAnalytics();
            }
        };

        window.toggleMemberChecked = function (memberId) {
            const label = document.getElementById(`label-for-${memberId}`);
            if (!label) return;
            const checkbox = label.querySelector("input");
            if (checkbox.checked) {
                label.classList.add("active");
                label.classList.add("checked");
            } else {
                label.classList.remove("active");
                label.classList.remove("checked");
            }
            updateAttendanceCount();
            updateGroupAnalytics();
        };

        function updateAttendanceCount() {
            const checkedCount = getCheckedUsernames().length;
            if (attendanceCountBadge) {
                attendanceCountBadge.textContent = `${checkedCount} attending`;
            }
        }

        selectAllBtn.addEventListener("click", function () {
            document.querySelectorAll(".member-checkbox").forEach(cb => {
                cb.checked = true;
                if (cb.parentElement) {
                    cb.parentElement.classList.add("active");
                    cb.parentElement.classList.add("checked");
                }
            });
            updateAttendanceCount();
            updateGroupAnalytics();
        });

        selectNoneBtn.addEventListener("click", function () {
            document.querySelectorAll(".member-checkbox").forEach(cb => {
                cb.checked = false;
                if (cb.parentElement) {
                    cb.parentElement.classList.remove("active");
                    cb.parentElement.classList.remove("checked");
                }
            });
            updateAttendanceCount();
            updateGroupAnalytics();
        });

        // Active Group Header Edit / Delete actions
        const headerEditGroupBtn = document.getElementById("header-edit-group-btn");
        const headerDeleteGroupBtn = document.getElementById("header-delete-group-btn");
        if (headerEditGroupBtn) {
            headerEditGroupBtn.addEventListener("click", function () {
                if (activeGroup) editGroup(activeGroup.id);
            });
        }
        if (headerDeleteGroupBtn) {
            headerDeleteGroupBtn.addEventListener("click", function () {
                if (activeGroup) deleteGroup(activeGroup.id);
            });
        }

        function getCheckedUsernames() {
            const names = [];
            document.querySelectorAll(".member-checkbox:checked").forEach(cb => {
                names.push(cb.value.trim());
            });
            return names;
        }

        window.deleteGroup = function (id) {
            if (confirm("Are you sure you want to delete this playgroup?")) {
                playgroups = playgroups.filter(g => g.id !== id);
                localStorage.setItem("bgg_playgroups", JSON.stringify(playgroups));
                syncPreferencesToBackend();

                if (activeGroup && activeGroup.id === id) {
                    activeGroup = null;
                    plannerActiveView.style.display = "none";
                    plannerEmptyState.style.display = "block";
                }

                renderGroupList();
            }
        };

        window.editGroup = function (id) {
            const g = playgroups.find(g => g.id === id);
            if (g) {
                const formError = document.getElementById("group-form-error");
                if (formError) formError.style.display = "none";
                editGroupId.value = g.id;
                groupNameInput.value = g.name;
                groupMembersInput.value = g.members.join(", ");
                formTitle.textContent = "Edit Playgroup";
                groupFormCard.style.display = "flex";
                showCreateFormBtn.style.display = "none";
            }
        };

        showCreateFormBtn.addEventListener("click", function () {
            const formError = document.getElementById("group-form-error");
            if (formError) formError.style.display = "none";
            editGroupId.value = "";
            groupNameInput.value = "";
            groupMembersInput.value = "";
            formTitle.textContent = "Create Playgroup";
            groupFormCard.style.display = "flex";
            showCreateFormBtn.style.display = "none";
        });

        cancelFormBtn.addEventListener("click", function () {
            const formError = document.getElementById("group-form-error");
            if (formError) formError.style.display = "none";
            groupFormCard.style.display = "none";
            showCreateFormBtn.style.display = "block";
        });

        async function validateBggUsername(username) {
            const trimmed = username.trim();
            if (!trimmed) {
                return { valid: false, username: trimmed, reason: "Username cannot be empty" };
            }
            if (!/^[a-zA-Z0-9_]{1,25}$/.test(trimmed)) {
                return { valid: false, username: trimmed, reason: "Invalid format (must be 1–25 letters, numbers, or underscores)" };
            }

            try {
                const xmlDoc = await fetchUserXml(trimmed);
                if (!xmlDoc) {
                    return { valid: false, username: trimmed, reason: "Account not found on BoardGameGeek" };
                }

                // Check for errors tag in BGG XML response
                const errors = xmlDoc.getElementsByTagName('errors');
                if (errors.length > 0) {
                    const errMsg = errors[0].getElementsByTagName('error')[0]?.textContent || "User not found on BoardGameGeek";
                    return { valid: false, username: trimmed, reason: errMsg };
                }

                return { valid: true, username: trimmed };
            } catch (e) {
                console.warn(`Validation failed for BGG username ${trimmed}:`, e);
                return { valid: false, username: trimmed, reason: "Account does not exist on BoardGameGeek" };
            }
        }

        groupForm.addEventListener("submit", async function (e) {
            e.preventDefault();
            const formError = document.getElementById("group-form-error");
            if (formError) formError.style.display = "none";

            const name = groupNameInput.value.trim();
            const membersRaw = groupMembersInput.value;
            const members = Array.from(new Set(membersRaw.split(",").map(m => m.trim()).filter(m => m.length > 0)));

            if (!name) {
                if (formError) {
                    formError.innerHTML = "⚠️ Please enter a group name.";
                    formError.style.display = "block";
                }
                return;
            }

            if (members.length === 0) {
                if (formError) {
                    formError.innerHTML = "⚠️ Please enter at least 1 BGG username.";
                    formError.style.display = "block";
                }
                return;
            }

            const saveBtn = document.getElementById("save-group-btn");
            const originalBtnText = saveBtn.textContent;
            saveBtn.disabled = true;
            saveBtn.textContent = "🔍 Verifying BGG accounts...";

            try {
                // Validate all usernames in parallel
                const validationResults = await Promise.all(members.map(m => validateBggUsername(m)));
                const invalidUsers = validationResults.filter(r => !r.valid);

                if (invalidUsers.length > 0) {
                    saveBtn.disabled = false;
                    saveBtn.textContent = originalBtnText;

                    if (formError) {
                        const listHtml = invalidUsers.map(u => `<li><strong>${escapeHTML(u.username || 'empty')}</strong>: ${escapeHTML(u.reason)}</li>`).join("");
                        formError.innerHTML = `
                            <strong>⚠️ Invalid BGG Account${invalidUsers.length > 1 ? 's' : ''}:</strong>
                            <ul style="margin: 6px 0 6px 16px; padding: 0;">${listHtml}</ul>
                            <span style="font-size: 0.8rem; opacity: 0.9;">Please correct any typos before saving this playgroup.</span>
                        `;
                        formError.style.display = "block";
                    }
                    return;
                }

                // If all valid, save the group
                const id = editGroupId.value;
                if (id) {
                    // Update
                    const g = playgroups.find(g => g.id === id);
                    if (g) {
                        g.name = name;
                        g.members = members;
                    }
                } else {
                    // Create
                    const newGroup = {
                        id: Date.now().toString(),
                        name: name,
                        members: members
                    };
                    playgroups.push(newGroup);
                }

                localStorage.setItem("bgg_playgroups", JSON.stringify(playgroups));
                syncPreferencesToBackend();
                groupFormCard.style.display = "none";
                showCreateFormBtn.style.display = "block";
                renderGroupList();

                // Re-select if updated active group or newly created
                if (id && activeGroup && activeGroup.id === id) {
                    selectGroup(id);
                } else if (!id && playgroups.length > 0) {
                    selectGroup(playgroups[playgroups.length - 1].id);
                }
            } catch (err) {
                console.error("Error saving playgroup:", err);
                if (formError) {
                    formError.innerHTML = "⚠️ An error occurred while validating usernames. Please try again.";
                    formError.style.display = "block";
                }
            } finally {
                saveBtn.disabled = false;
                saveBtn.textContent = originalBtnText;
            }
        });

        // Initialize group list
        renderGroupList();

        // 2. Weights sliders sync
        function updateSlidersFromStorage() {
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
            wMechVal.textContent = `${wMechInput.value}%`;
            wCatVal.textContent = `${wCatInput.value}%`;
            wPopVal.textContent = `${wPopInput.value}%`;
            wHotVal.textContent = `${wHotInput.value}%`;
        }

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

        [wMechInput, wCatInput, wPopInput, wHotInput].forEach(input => {
            input.addEventListener("input", function () {
                const valSpan = document.getElementById(`${input.id}_val`);
                if (valSpan) valSpan.textContent = `${input.value}%`;
                saveSlidersToStorage();
            });
        });

        // Preferences Sync functions
        async function syncPreferencesToBackend() {
            if (typeof Auth === 'undefined' || !Auth.isLoggedIn()) return;

            const weights = {
                mech: wMechInput.value,
                cat: wCatInput.value,
                pop: wPopInput.value,
                hot: wHotInput.value
            };

            try {
                // Atomic partial update: only sync playgroups and saved_weights; never overwrite user_preferences or bgg_username
                await fetchApi('/preferences', {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        playgroups: playgroups,
                        saved_weights: weights
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
                        if (window.Auth && window.Auth.setBggUsername) window.Auth.setBggUsername(data.bgg_username);
                        else {
                            localStorage.setItem("bgg_username", data.bgg_username);
                            localStorage.setItem("bgg_last_username", data.bgg_username);
                        }
                    }
                    if (data.playgroups && Array.isArray(data.playgroups)) {
                        if (data.playgroups.length > 0) {
                            playgroups = data.playgroups;
                            localStorage.setItem("bgg_playgroups", JSON.stringify(playgroups));
                            renderGroupList();
                        } else if (playgroups.length > 0) {
                            // Backend returned empty list, but local storage has playgroups.
                            // Safeguard: sync local playgroups to backend instead of destroying local data.
                            syncPreferencesToBackend();
                        } else {
                            playgroups = [];
                            localStorage.setItem("bgg_playgroups", JSON.stringify(playgroups));
                            renderGroupList();
                        }
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

        updateSlidersFromStorage();
        loadPreferencesFromBackend();
        loadPastPolls();

        // Listen to custom login event to load preferences immediately upon login
        document.addEventListener("bgg_login_success", function () {
            loadPreferencesFromBackend();
            loadPastPolls();
        });

        // Tab Switching Logic
        const tabRecsBtn = document.getElementById("tab-recommendations-btn");
        const tabAnalBtn = document.getElementById("tab-analytics-btn");
        const tabPollsBtn = document.getElementById("tab-polls-btn");
        const tabRecsContent = document.getElementById("tab-recommendations-content");
        const tabAnalContent = document.getElementById("tab-analytics-content");
        const tabPollsContent = document.getElementById("tab-polls-content");

        window.switchTab = function (targetTab) {
            const tabRecsBtn = document.getElementById("tab-recommendations-btn");
            const tabAnalBtn = document.getElementById("tab-analytics-btn");
            const tabPollsBtn = document.getElementById("tab-polls-btn");
            const tabRecsContent = document.getElementById("tab-recommendations-content");
            const tabAnalContent = document.getElementById("tab-analytics-content");
            const tabPollsContent = document.getElementById("tab-polls-content");

            const allContents = [
                { id: "recommendations", btn: tabRecsBtn, content: tabRecsContent },
                { id: "analytics", btn: tabAnalBtn, content: tabAnalContent },
                { id: "polls", btn: tabPollsBtn, content: tabPollsContent }
            ];

            allContents.forEach(item => {
                if (!item.btn || !item.content) return;
                if (item.id === targetTab) {
                    item.btn.classList.add("active");
                    item.content.style.display = "block";
                    item.content.offsetHeight; // reflow
                    item.content.classList.add("active");
                } else {
                    item.btn.classList.remove("active");
                    item.content.classList.remove("active");
                    item.content.style.display = "none";
                }
            });

            if (targetTab === "analytics") {
                const activeCharts = [chartGroupMechanics, chartGroupCategories, chartGroupComplexity, chartGroupDurations];
                activeCharts.forEach(chart => {
                    if (chart) chart.resize();
                });
            } else if (targetTab === "polls") {
                if (typeof loadPastPolls === 'function') {
                    loadPastPolls();
                }
            }
        };

        if (tabRecsBtn) tabRecsBtn.addEventListener("click", () => window.switchTab("recommendations"));
        if (tabAnalBtn) tabAnalBtn.addEventListener("click", () => window.switchTab("analytics"));
        if (tabPollsBtn) tabPollsBtn.addEventListener("click", () => window.switchTab("polls"));

        let currentActiveRecs = [];

        let modalCandidatePool = [];
        let modalSelectedCandidateIds = new Set();

        // Helper to fetch all unique owned games across active playgroup members
        async function fetchGroupOwnedGames(usernames) {
            if (!usernames || usernames.length === 0) return [];
            const allUniqueMap = new Map();

            for (const username of usernames) {
                try {
                    const xmlDoc = await fetchUserXml(username);
                    if (xmlDoc) {
                        const userGames = parseXmlGames(xmlDoc);
                        userGames.forEach(g => {
                            if (g.own || userGames.every(x => !x.own)) {
                                const key = String(g.id || g.name.toLowerCase());
                                if (!allUniqueMap.has(key)) {
                                    allUniqueMap.set(key, {
                                        id: g.id || key,
                                        name: g.name,
                                        thumbnail: g.thumbnail || 'https://cf.geekdo-images.com/images/placeholder_thumb.png',
                                        rating: g.rating || g.bggRating || null,
                                        yearPublished: g.yearPublished,
                                        minPlayers: g.minPlayers,
                                        maxPlayers: g.maxPlayers,
                                        playingTime: g.playingTime,
                                        owners: [username]
                                    });
                                } else {
                                    const existing = allUniqueMap.get(key);
                                    if (!existing.owners.includes(username)) {
                                        existing.owners.push(username);
                                    }
                                }
                            }
                        });
                    }
                } catch (err) {
                    console.warn(`Could not load collection for ${username}:`, err);
                }
            }

            const gamesList = Array.from(allUniqueMap.values());
            gamesList.sort((a, b) => {
                if (a.rating && b.rating) return b.rating - a.rating;
                if (a.rating) return -1;
                if (b.rating) return 1;
                return a.name.localeCompare(b.name);
            });
            return gamesList;
        }

        function renderModalCandidatesList(filterQuery = "") {
            const candidatesList = document.getElementById("modal-candidates-list");
            const countBadge = document.getElementById("modal-selection-count");
            if (!candidatesList) return;

            const q = filterQuery.toLowerCase().trim();
            const filtered = q
                ? modalCandidatePool.filter(c => c.name.toLowerCase().includes(q))
                : modalCandidatePool;

            if (countBadge) {
                countBadge.textContent = `${modalSelectedCandidateIds.size} selected`;
            }

            if (filtered.length === 0) {
                candidatesList.innerHTML = `
                    <div style="text-align: center; padding: 20px; color: var(--text-muted); font-size: 0.9rem;">
                        ${q ? `No games match "${window.escapeHTML(q)}"` : 'No games found in the candidates pool.'}
                    </div>
                `;
                return;
            }

            let html = "";
            filtered.forEach(rec => {
                const recId = String(rec.id);
                const isChecked = modalSelectedCandidateIds.has(recId) ? "checked" : "";
                const ownerBadge = (rec.owners && rec.owners.length > 0)
                    ? `<span style="font-size: 0.75rem; color: var(--text-muted); margin-left: 4px;">(${rec.owners.join(", ")})</span>`
                    : '';

                html += `
                    <label style="display: flex; align-items: center; gap: 10px; padding: 8px 12px; background: rgba(255,255,255,0.03); border: 1px solid var(--border); border-radius: 8px; cursor: pointer; transition: background 0.15s ease;">
                        <input type="checkbox" class="poll-candidate-cb" value="${window.escapeHTML(recId)}" ${isChecked} onchange="toggleModalCandidate('${window.escapeHTML(recId)}')" style="accent-color: var(--primary);">
                        <img src="${rec.thumbnail || 'https://cf.geekdo-images.com/images/placeholder_thumb.png'}" style="width: 36px; height: 36px; border-radius: 6px; object-fit: cover; border: 1px solid var(--border);" onerror="this.src='https://cf.geekdo-images.com/images/placeholder_thumb.png'">
                        <div style="display: flex; flex-direction: column; min-width: 0; flex: 1;">
                            <span style="font-weight: 600; color: var(--text-main); font-size: 0.9rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                                ${window.escapeHTML(rec.name)} ${ownerBadge}
                            </span>
                            ${rec.yearPublished && rec.yearPublished !== 'N/A' ? `<span style="font-size: 0.75rem; color: var(--text-muted);">${rec.yearPublished}</span>` : ''}
                        </div>
                        ${rec.rating ? `<span style="font-size: 0.8rem; color: #b45309; font-weight: 700; white-space: nowrap;">★ ${typeof rec.rating === 'number' ? rec.rating.toFixed(1) : rec.rating}</span>` : ''}
                    </label>
                `;
            });
            candidatesList.innerHTML = html;
        }

        window.toggleModalCandidate = function (candId) {
            candId = String(candId);
            if (modalSelectedCandidateIds.has(candId)) {
                modalSelectedCandidateIds.delete(candId);
            } else {
                modalSelectedCandidateIds.add(candId);
            }
            const countBadge = document.getElementById("modal-selection-count");
            if (countBadge) {
                countBadge.textContent = `${modalSelectedCandidateIds.size} selected`;
            }
        };

        window.filterModalCandidates = function (query) {
            renderModalCandidatesList(query);
        };

        // Voting Session Modal Handlers
        window.openVotingSessionModal = async function (recs) {
            const modal = document.getElementById("voting-session-modal");
            const stepConfig = document.getElementById("modal-step-config");
            const stepCreated = document.getElementById("modal-step-created");
            const candidatesList = document.getElementById("modal-candidates-list");
            const sourceDesc = document.getElementById("modal-source-desc");
            const searchInput = document.getElementById("modal-candidate-search");

            stepConfig.style.display = "block";
            stepCreated.style.display = "none";
            if (searchInput) searchInput.value = "";

            const hasExplicitRecs = recs && recs.length > 0;
            const attendees = getCheckedUsernames();

            if (!hasExplicitRecs && attendees.length === 0) {
                alert("Please select at least one playgroup member to load candidates for the voting poll!");
                return;
            }

            modal.style.display = "flex";

            // Host Identity logic: automatically link from settings or prompt inline
            const linkedContainer = document.getElementById("modal-host-linked-container");
            const missingContainer = document.getElementById("modal-host-missing-container");
            const hostDisplay = document.getElementById("modal-host-username-display");
            const inlineInput = document.getElementById("modal-inline-bgg-username");
            const inlineError = document.getElementById("modal-inline-bgg-error");

            if (inlineError) {
                inlineError.textContent = "";
                inlineError.style.display = "none";
            }

            const configuredBggUser = (window.Auth && window.Auth.getBggUsername ? window.Auth.getBggUsername() : (localStorage.getItem("bgg_username") || localStorage.getItem("bgg_last_username") || "")).trim();

            if (configuredBggUser) {
                if (linkedContainer) linkedContainer.style.display = "flex";
                if (hostDisplay) hostDisplay.textContent = configuredBggUser;
                if (missingContainer) missingContainer.style.display = "none";
            } else {
                if (linkedContainer) linkedContainer.style.display = "none";
                if (missingContainer) missingContainer.style.display = "block";
                if (inlineInput) inlineInput.value = "";
            }

            if (hasExplicitRecs) {
                if (sourceDesc) {
                    sourceDesc.textContent = "Select candidate games from your recommendation shortlist or filter by title. Attendees vote 👍 Want to Play, 😐 Fine, or ❌ Veto.";
                }
                modalCandidatePool = recs.map(r => ({ ...r, id: String(r.id) }));
                modalSelectedCandidateIds = new Set();
                renderModalCandidatesList();
            } else {
                if (sourceDesc) {
                    sourceDesc.textContent = `Aggregating unique owned games from active playgroup attendees (${attendees.join(", ")})...`;
                }
                candidatesList.innerHTML = `
                    <div style="text-align: center; padding: 30px; color: var(--text-muted);">
                        <div class="spinner" style="width: 24px; height: 24px; margin: 0 auto 12px auto;"></div>
                        Loading unique owned games from ${attendees.length} member${attendees.length > 1 ? 's' : ''}...
                    </div>
                `;

                try {
                    const ownedGames = await fetchGroupOwnedGames(attendees);
                    if (ownedGames.length === 0) {
                        candidatesList.innerHTML = `
                            <div style="text-align: center; padding: 25px; color: var(--danger);">
                                No games found in the selected members' collections. Make sure member BGG accounts have owned games or run recommendations first.
                            </div>
                        `;
                        return;
                    }

                    if (sourceDesc) {
                        sourceDesc.textContent = `Found ${ownedGames.length} unique owned games across ${attendees.length} members. Select games to include in tonight's voting poll:`;
                    }
                    modalCandidatePool = ownedGames;
                    modalSelectedCandidateIds = new Set();
                    renderModalCandidatesList();
                } catch (e) {
                    console.error("Error loading group library for poll:", e);
                    candidatesList.innerHTML = `
                        <div style="text-align: center; padding: 25px; color: var(--danger);">
                            Failed to load group games: ${window.escapeHTML(e.message || 'Unknown error')}
                        </div>
                    `;
                }
            }
        };

        window.closeVotingSessionModal = function () {
            const modal = document.getElementById("voting-session-modal");
            if (modal) modal.style.display = "none";
        };

        window.clearInlineBggError = function () {
            const inlineError = document.getElementById("modal-inline-bgg-error");
            if (inlineError) {
                inlineError.textContent = "";
                inlineError.style.display = "none";
            }
        };

        window.createVotingSession = async function () {
            if (modalSelectedCandidateIds.size === 0) {
                alert("Please select at least one candidate game for the voting poll!");
                return;
            }

            // Resolve host username: from settings/Auth or from inline input prompt
            let creatorName = (window.Auth && window.Auth.getBggUsername ? window.Auth.getBggUsername() : (localStorage.getItem("bgg_username") || localStorage.getItem("bgg_last_username") || "")).trim();

            if (!creatorName) {
                const inlineInput = document.getElementById("modal-inline-bgg-username");
                const inlineError = document.getElementById("modal-inline-bgg-error");
                const enteredVal = inlineInput ? inlineInput.value.trim() : "";
                if (!enteredVal) {
                    if (inlineError) {
                        inlineError.textContent = "⚠️ Please enter your BoardGameGeek username before launching the poll.";
                        inlineError.style.display = "block";
                    }
                    if (inlineInput) inlineInput.focus();
                    return;
                }
                creatorName = enteredVal;

                // Save to Auth & localStorage so settings are updated for future polls
                if (window.Auth && window.Auth.setBggUsername) {
                    window.Auth.setBggUsername(creatorName);
                } else {
                    localStorage.setItem("bgg_username", creatorName);
                    localStorage.setItem("bgg_last_username", creatorName);
                }

                // Sync to backend preferences if user is logged in
                if (typeof Auth !== 'undefined' && Auth.isLoggedIn && Auth.isLoggedIn()) {
                    try {
                        let currentPrefs = {};
                        const getRes = await fetchApi('/preferences');
                        if (getRes.ok) currentPrefs = await getRes.json();
                        await fetchApi('/preferences', {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({
                                ...currentPrefs,
                                bgg_username: creatorName
                            })
                        });
                    } catch (prefErr) {
                        console.warn("Could not sync bgg_username to preferences:", prefErr);
                    }
                }
            }

            const chosenCandidates = modalCandidatePool.filter(r => modalSelectedCandidateIds.has(String(r.id)));
            const durationHours = parseFloat(document.getElementById("modal-poll-duration").value || 24);
            const groupName = activeGroup ? activeGroup.name : "Game Night";
            const roster = activeGroup ? activeGroup.members : getCheckedUsernames();

            const submitBtn = document.getElementById("create-poll-submit-btn");
            submitBtn.disabled = true;
            submitBtn.textContent = "Creating...";

            try {
                const resp = await window.fetchApi("/session", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        group_name: groupName,
                        creator_name: creatorName,
                        creator_id: creatorName,
                        candidates: chosenCandidates,
                        duration_hours: durationHours,
                        roster: roster
                    })
                });

                if (resp.ok) {
                    const sessionData = await resp.json();
                    localStorage.setItem("bgg_poll_host_" + sessionData.session_id, creatorName);

                    const voteUrl = `${window.location.origin}${window.location.pathname.replace(/\/groups\/?$/, '')}/vote/?id=${sessionData.session_id}`;

                    document.getElementById("share-poll-url-input").value = voteUrl;
                    document.getElementById("open-poll-link-btn").href = voteUrl;

                    document.getElementById("modal-step-config").style.display = "none";
                    document.getElementById("modal-step-created").style.display = "block";
                    loadPastPolls();
                } else {
                    const errData = await resp.json().catch(() => ({}));
                    alert(errData.error || "Failed to create voting session.");
                }
            } catch (e) {
                console.error("Error creating session:", e);
                alert("Error creating voting session. Please check your connection.");
            } finally {
                submitBtn.disabled = false;
                submitBtn.textContent = "🚀 Launch Poll";
            }
        };

        window.copyPollLink = function () {
            const input = document.getElementById("share-poll-url-input");
            input.select();
            input.setSelectionRange(0, 99999);
            navigator.clipboard.writeText(input.value);
            const copyBtn = document.getElementById("copy-poll-link-btn");
            copyBtn.textContent = "✓ Copied!";
            setTimeout(() => { copyBtn.textContent = "📋 Copy"; }, 2000);
        };

        async function loadPastPolls() {
            const listContainer = document.getElementById("past-polls-list");
            if (!listContainer) return;

            try {
                const userBgg = (window.Auth && window.Auth.getBggUsername && window.Auth.getBggUsername()) || localStorage.getItem("bgg_username") || "";
                const userEmail = (window.Auth && window.Auth.isLoggedIn && window.Auth.isLoggedIn() && window.Auth.getEmail && window.Auth.getEmail()) || "";
                const identifiers = [userBgg, userEmail].filter(Boolean).join(",");
                const url = identifiers ? `/sessions?creator_id=${encodeURIComponent(identifiers)}` : "/sessions";
                const resp = await window.fetchApi(url);
                if (resp.ok) {
                    const data = await resp.json();
                    const sessions = data.sessions || [];
                    if (sessions.length === 0) {
                        listContainer.innerHTML = `
                            <div style="text-align: center; padding: 40px; color: var(--text-muted); border: 1px dashed var(--border); border-radius: 12px;">
                                <div style="font-size: 2rem; margin-bottom: 8px;">🗳️</div>
                                <h4 style="margin: 0 0 6px 0; color: var(--text-main);">No Polls Created Yet</h4>
                                <p style="margin: 0 0 16px 0; font-size: 0.9rem;">Click "+ Create Poll" or "Poll Group Library" to launch your first game night voting session!</p>
                                <button class="btn btn-primary" onclick="openVotingSessionModal()" style="font-size: 0.88rem; padding: 8px 16px;">+ Create a Poll</button>
                            </div>
                        `;
                        return;
                    }

                    const activeSessions = sessions.filter(s => !s.is_closed);
                    const closedSessions = sessions.filter(s => s.is_closed);

                    function getRemainingTimeStr(closesAt) {
                        const diffMs = new Date(closesAt) - new Date();
                        if (diffMs <= 0) return "Closing soon";
                        const hours = Math.floor(diffMs / (1000 * 60 * 60));
                        const minutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
                        if (hours > 24) {
                            const days = Math.floor(hours / 24);
                            return `${days} day${days > 1 ? 's' : ''} left`;
                        }
                        if (hours > 0) return `${hours}h ${minutes}m left`;
                        return `${minutes}m left`;
                    }

                    let html = "";

                    // 1. ACTIVE POLLS SECTION
                    html += `
                        <div style="margin-bottom: 10px;">
                            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
                                <span style="font-weight: 700; font-size: 1rem; color: var(--text-main);">🟢 Active Polls</span>
                                <span style="background: rgba(16, 185, 129, 0.2); color: #34d399; font-weight: 800; font-size: 0.75rem; padding: 2px 8px; border-radius: 10px;">${activeSessions.length}</span>
                            </div>
                    `;

                    if (activeSessions.length === 0) {
                        html += `
                            <div style="padding: 18px 20px; background: rgba(99, 102, 241, 0.04); border: 1px dashed var(--border); border-radius: 12px; font-size: 0.88rem; color: var(--text-muted); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
                                <span>No active voting sessions open right now.</span>
                                <button class="btn btn-outline" onclick="openVotingSessionModal()" style="font-size: 0.8rem; padding: 5px 12px;">+ Start New Poll</button>
                            </div>
                        `;
                    } else {
                        html += `<div style="display: flex; flex-direction: column; gap: 12px;">`;
                        activeSessions.forEach(sess => {
                            const totalVoters = sess.consensus ? sess.consensus.total_voters : 0;
                            const createdDate = new Date(sess.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
                            const voteUrl = `${window.location.origin}${window.location.pathname.replace(/\/groups\/?$/, '')}/vote/?id=${sess.session_id}`;
                            const timeLeft = sess.closes_at ? getRemainingTimeStr(sess.closes_at) : 'Active';

                            html += `
                                <div style="background: var(--card-bg); border: 1.5px solid rgba(16, 185, 129, 0.4); box-shadow: 0 4px 16px rgba(16, 185, 129, 0.08); border-radius: 12px; padding: 18px 20px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px;">
                                    <div style="display: flex; flex-direction: column; gap: 6px;">
                                        <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
                                             <strong style="font-size: 1.1rem; color: var(--text-main); font-family: 'Outfit', sans-serif;">${window.escapeHTML(sess.group_name || 'Game Night')}</strong>
                                            <span style="background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); padding: 3px 8px; border-radius: 6px; font-size: 0.75rem; font-weight: 700;">⏱️ ACTIVE • ${timeLeft}</span>
                                        </div>
                                        <div style="font-size: 0.85rem; color: var(--text-muted);">
                                            Created ${createdDate} by <strong>${window.escapeHTML(sess.creator_name === 'anonymous_host' ? 'Host' : (sess.creator_name || 'Host'))}</strong> • ${totalVoters} vote${totalVoters !== 1 ? 's' : ''} recorded • ${sess.candidates ? sess.candidates.length : 0} candidate games
                                        </div>
                                    </div>
                                    <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                                        <button type="button" class="btn btn-secondary" onclick="navigator.clipboard.writeText('${voteUrl}'); alert('Voting link copied to clipboard!');" style="font-size: 0.82rem; padding: 8px 12px;" title="Copy shareable voting link">
                                            📋 Share Link
                                        </button>
                                        <button type="button" class="btn btn-secondary" onclick="closeSessionEarly('${sess.session_id}')" style="font-size: 0.82rem; padding: 8px 12px; color: #fbbf24; border-color: rgba(245, 158, 11, 0.4);" title="End voting early and finalize results">
                                            🔒 Close Early
                                        </button>
                                        <button type="button" class="btn btn-secondary" onclick="cancelSessionPrompt('${sess.session_id}')" style="font-size: 0.82rem; padding: 8px 12px; color: #f87171; border-color: rgba(239, 68, 68, 0.4);" title="Cancel and delete this poll">
                                            🗑️
                                        </button>
                                        <a href="${voteUrl}" target="_blank" class="btn btn-primary" style="font-size: 0.85rem; padding: 8px 16px; font-weight: 700; background: linear-gradient(135deg, #10b981, #059669); border: none;">
                                            🗳️ Vote / View ↗
                                        </a>
                                    </div>
                                </div>
                            `;
                        });
                        html += `</div>`;
                    }
                    html += `</div>`;

                    // 2. COMPLETED POLLS SECTION
                    if (closedSessions.length > 0) {
                        html += `
                            <div style="margin-top: 10px;">
                                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
                                    <span style="font-weight: 700; font-size: 1rem; color: var(--text-main);">📜 Completed Polls</span>
                                    <span style="background: rgba(148, 163, 184, 0.2); color: var(--text-muted); font-weight: 800; font-size: 0.75rem; padding: 2px 8px; border-radius: 10px;">${closedSessions.length}</span>
                                </div>
                                <div style="display: flex; flex-direction: column; gap: 12px;">
                        `;

                        closedSessions.forEach(sess => {
                            const totalVoters = sess.consensus ? sess.consensus.total_voters : 0;
                            const winner = sess.consensus ? sess.consensus.winner : null;
                            const createdDate = new Date(sess.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
                            const voteUrl = `${window.location.origin}${window.location.pathname.replace(/\/groups\/?$/, '')}/vote/?id=${sess.session_id}`;

                            html += `
                                <div style="background: var(--card-bg); border: 1.5px solid var(--border); border-radius: 12px; padding: 16px 20px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px; opacity: 0.92;">
                                    <div style="display: flex; flex-direction: column; gap: 4px;">
                                        <div style="display: flex; align-items: center; gap: 10px;">
                                            <strong style="font-size: 1.05rem; color: var(--text-main); font-family: 'Outfit', sans-serif;">${window.escapeHTML(sess.group_name || 'Game Night')}</strong>
                                            <span style="background: rgba(239, 68, 68, 0.12); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.25); padding: 2px 7px; border-radius: 6px; font-size: 0.72rem; font-weight: 700;">🔒 FINALIZED</span>
                                        </div>
                                        <div style="font-size: 0.82rem; color: var(--text-muted);">
                                            Closed ${createdDate} • ${totalVoters} voter${totalVoters !== 1 ? 's' : ''} • ${sess.candidates ? sess.candidates.length : 0} candidates
                                        </div>
                                        ${winner ? `
                                            <div style="font-size: 0.88rem; color: #10b981; font-weight: 600; margin-top: 2px;">
                                                🏆 Consensus Winner: <strong>${window.escapeHTML(winner.name)}</strong>
                                            </div>
                                        ` : ''}
                                    </div>
                                    <div style="display: flex; gap: 8px; align-items: center;">
                                        <button type="button" class="btn btn-secondary" onclick="deleteSessionPrompt('${sess.session_id}')" style="font-size: 0.82rem; padding: 8px 12px; color: #f87171; border-color: rgba(239, 68, 68, 0.4);" title="Delete from history">
                                            🗑️ Delete
                                        </button>
                                        <a href="${voteUrl}" target="_blank" class="btn btn-secondary" style="font-size: 0.82rem; padding: 8px 14px;">
                                            📊 View Results ↗
                                        </a>
                                    </div>
                                </div>
                            `;
                        });
                        html += `</div></div>`;
                    }

                    listContainer.innerHTML = html;
                } else {
                    listContainer.innerHTML = `
                        <div style="text-align: center; padding: 40px; color: var(--text-muted); border: 1px dashed var(--border); border-radius: 12px;">
                            <div style="font-size: 2rem; margin-bottom: 8px;">🗳️</div>
                            <h4 style="margin: 0 0 6px 0; color: var(--text-main);">No Active Polls</h4>
                            <p style="margin: 0 0 16px 0; font-size: 0.9rem;">Click "+ Create Poll" or "Poll Group Library" to launch your first game night voting session!</p>
                            <button class="btn btn-primary" onclick="openVotingSessionModal()" style="font-size: 0.88rem; padding: 8px 16px;">+ Create a Poll</button>
                        </div>
                    `;
                }
            } catch (e) {
                console.error("Error loading polls:", e);
                listContainer.innerHTML = `
                    <div style="text-align: center; padding: 40px; color: var(--text-muted); border: 1px dashed var(--border); border-radius: 12px;">
                        <div style="font-size: 2rem; margin-bottom: 8px;">🗳️</div>
                        <h4 style="margin: 0 0 6px 0; color: var(--text-main);">No Polls Found</h4>
                        <p style="margin: 0 0 16px 0; font-size: 0.9rem;">Click "+ Create Poll" or "Poll Group Library" to launch your first game night voting session!</p>
                        <button class="btn btn-primary" onclick="openVotingSessionModal()" style="font-size: 0.88rem; padding: 8px 16px;">+ Create a Poll</button>
                    </div>
                `;
            }
        }
        window.loadPastPolls = loadPastPolls;

        window.closeSessionEarly = async function (sessionId) {
            if (!confirm("Are you sure you want to close this poll now? Voting will end immediately.")) return;
            try {
                const resp = await window.fetchApi('/session/close', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ session_id: sessionId })
                });
                if (resp.ok) {
                    loadPastPolls();
                } else {
                    const err = await resp.json().catch(() => ({}));
                    alert(err.error || "Failed to close poll.");
                }
            } catch (e) {
                console.error("Error closing session:", e);
                alert("Error closing poll.");
            }
        };

        window.deleteSessionPrompt = async function (sessionId) {
            if (!confirm("Are you sure you want to permanently delete this completed poll from your history?")) return;
            try {
                const resp = await window.fetchApi(`/session?session_id=${encodeURIComponent(sessionId)}`, {
                    method: 'DELETE'
                });
                if (resp.ok) {
                    loadPastPolls();
                } else {
                    const err = await resp.json().catch(() => ({}));
                    alert(err.error || "Failed to delete poll.");
                }
            } catch (e) {
                console.error("Error deleting session:", e);
                alert("Error deleting poll.");
            }
        };

        window.cancelSessionPrompt = async function (sessionId) {
            if (!confirm("Are you sure you want to cancel and remove this active voting poll?")) return;
            try {
                const resp = await window.fetchApi(`/session?session_id=${encodeURIComponent(sessionId)}`, {
                    method: 'DELETE'
                });
                if (resp.ok) {
                    loadPastPolls();
                } else {
                    const err = await resp.json().catch(() => ({}));
                    alert(err.error || "Failed to cancel poll.");
                }
            } catch (e) {
                console.error("Error cancelling session:", e);
                alert("Error cancelling poll.");
            }
        };

        // Restore and bind duration/complexity preferences
        const durationPref = localStorage.getItem("bgg_rec_duration_pref") || "any";
        let complexityPref = localStorage.getItem("bgg_rec_complexity_pref") || "any";

        // Normalize aliases between pages (e.g. low/high to light/heavy)
        if (complexityPref === "low") complexityPref = "light";
        if (complexityPref === "high") complexityPref = "heavy";

        const durationEl = document.getElementById("duration_pref");
        if (durationEl) {
            durationEl.value = durationPref;
            if (durationEl.selectedIndex === -1 || !durationEl.value) {
                durationEl.value = "any";
            }
        }

        const complexityEl = document.getElementById("complexity_pref");
        if (complexityEl) {
            complexityEl.value = complexityPref;
            if (complexityEl.selectedIndex === -1 || !complexityEl.value) {
                complexityEl.value = "any";
            }
        }

        document.getElementById("duration_pref").addEventListener("change", function () {
            localStorage.setItem("bgg_rec_duration_pref", this.value);
        });
        document.getElementById("complexity_pref").addEventListener("change", function () {
            localStorage.setItem("bgg_rec_complexity_pref", this.value);
        });

        // Collapsible sliders behavior
        weightsToggleBar.addEventListener("click", function () {
            const isVisible = weightsExpandableContent.style.display === "block";
            if (isVisible) {
                weightsExpandableContent.style.display = "none";
                weightsCaret.textContent = "▼";
                weightsToggleBar.style.borderBottomLeftRadius = "8px";
                weightsToggleBar.style.borderBottomRightRadius = "8px";
            } else {
                weightsExpandableContent.style.display = "block";
                weightsCaret.textContent = "▲";
                weightsToggleBar.style.borderBottomLeftRadius = "0px";
                weightsToggleBar.style.borderBottomRightRadius = "0px";
            }
        });

        // 3. API polling recommendation fetching
        generatePlanBtn.addEventListener("click", function () {
            const usernames = getCheckedUsernames();
            if (usernames.length === 0) {
                alert("Please check at least one attending playgroup member!");
                return;
            }

            // Auto-switch back to recommendations tab to view loading skeleton / results
            if (window.switchTab) {
                window.switchTab("recommendations");
            }

            // Cancel any active polling
            isPollingActive = false;
            if (pollingTimeout) clearTimeout(pollingTimeout);

            if (window.renderSkeletonCards) {
                window.renderSkeletonCards(resultsContainer, 4);
            } else {
                resultsContainer.innerHTML = "";
            }

            const spinner = statusCard.querySelector(".spinner");
            if (spinner) spinner.style.display = "none";

            statusCard.style.display = "flex";
            statusMessage.textContent = "Connecting to backend recommender engine...";
            generatePlanBtn.disabled = true;

            const w_mech = (wMechInput.value / 100).toFixed(2);
            const w_cat = (wCatInput.value / 100).toFixed(2);
            const w_pop = (wPopInput.value / 100).toFixed(2);
            const w_hot = (wHotInput.value / 100).toFixed(2);
            const player_count = usernames.length;
            const duration_pref = document.getElementById("duration_pref").value;
            const complexity_pref = document.getElementById("complexity_pref").value;

            // Generate deterministic group cache key
            const sortedNames = [...usernames].map(u => u.toLowerCase()).sort();
            const usernameKey = sortedNames.join("_");
            const cacheKey = `bgg_rec_${usernameKey}_owned_any_any_${player_count}_${duration_pref}_${complexity_pref}_${w_mech}_${w_cat}_${w_pop}_${w_hot}`;

            // Check client side cache (TTL = 7 days)
            const cachedDataStr = localStorage.getItem(cacheKey);
            if (cachedDataStr) {
                try {
                    const cachedData = JSON.parse(cachedDataStr);
                    const ageMs = Date.now() - cachedData.timestamp;
                    const sevenDaysMs = 7 * 24 * 60 * 60 * 1000;
                    if (ageMs < sevenDaysMs) {
                        console.log("Serving group recommendations from local storage cache.");
                        statusCard.style.display = "none";
                        generatePlanBtn.disabled = false;
                        renderRecommendations(cachedData.recommendations);
                        return;
                    } else {
                        localStorage.removeItem(cacheKey);
                    }
                } catch (e) {
                    console.error("Local cache read error:", e);
                    localStorage.removeItem(cacheKey);
                }
            }

            // Call API Gateway endpoint
            let params = new URLSearchParams({
                username: usernames.join(","),
                own_status: "owned",
                player_count: player_count,
                w_mech: w_mech,
                w_cat: w_cat,
                w_pop: w_pop,
                w_hot: w_hot
            });
            if (duration_pref !== "any") params.append("duration_pref", duration_pref);
            if (complexity_pref !== "any") params.append("complexity_pref", complexity_pref);

            const queryUrl = `/recommendations?${params.toString()}`;
            isPollingActive = true;

            function pollGroupRecommendations() {
                if (!isPollingActive) return;

                fetchApi(queryUrl)
                    .then(response => {
                        if (!response.ok) {
                            throw new Error("API response error");
                        }
                        return response.json();
                    })
                    .then(data => {
                        if (!isPollingActive) return;

                        if (data.status === "scraping") {
                            const usersScraping = data.scraping_users ? data.scraping_users.join(", ") : "some attendees";
                            statusMessage.textContent = `Scraping and building BGG profiles for: ${usersScraping}. This takes about 30 seconds...`;
                            pollingTimeout = setTimeout(pollGroupRecommendations, 5000);
                        } else if (data.status === "ready") {
                            isPollingActive = false;
                            statusCard.style.display = "none";
                            generatePlanBtn.disabled = false;

                            // Cache recommendations
                            try {
                                const cacheVal = {
                                    timestamp: Date.now(),
                                    recommendations: data.recommendations
                                };
                                localStorage.setItem(cacheKey, JSON.stringify(cacheVal));
                            } catch (e) {
                                console.error("Local storage cache write error:", e);
                            }

                            renderRecommendations(data.recommendations);
                        } else {
                            throw new Error("Unexpected API status response");
                        }
                    })
                    .catch(error => {
                        if (!isPollingActive) return;
                        console.error("API error:", error);
                        isPollingActive = false;
                        statusCard.style.display = "none";
                        generatePlanBtn.disabled = false;
                        resultsContainer.innerHTML = `<div style="color: var(--danger); font-weight: bold; padding: 20px; background: var(--danger-bg); border: 1px solid var(--danger-border); border-radius: 8px; margin: 0 auto; text-align: center;">Error: Failed to fetch playgroup recommendations. Check AWS Lambda logs.</div>`;
                    });
            }

            pollGroupRecommendations();
        });

        function renderRecommendations(recs) {
            if (!recs || recs.length === 0) {
                resultsContainer.innerHTML = `<div style="text-align: center; padding: 40px; color: var(--text-muted); font-size: 1.1rem; border: 1px dashed var(--border); border-radius: 12px; background: var(--card-bg); width: 100%;">No recommendations found matching the attendees collection. Try adding more users with rated games or relaxing year filters!</div>`;
                return;
            }

            let html = "";
            recs.forEach((rec, index) => {
                html += window.renderRecommendationCard(rec, index);
            });

            html += `
                <div class="rec-actions-bar" style="display: flex; gap: 10px; flex-wrap: wrap;">
                    <button type="button" class="btn btn-primary" id="group-start-poll-btn" style="display: inline-flex; align-items: center; gap: 8px; font-weight: 600;">
                        <span>🗳️ Start Async Voting Poll</span>
                    </button>
                    <button type="button" class="btn btn-secondary" id="group-export-graphic-btn" style="display: inline-flex; align-items: center; gap: 8px; font-weight: 600;">
                        <span>🖼️ Export Shareable Image</span>
                    </button>
                </div>
            `;

            resultsContainer.innerHTML = html;

            const pollBtn = document.getElementById("group-start-poll-btn");
            if (pollBtn) {
                pollBtn.onclick = () => {
                    window.openVotingSessionModal(recs);
                };
            }

            const exportBtn = document.getElementById("group-export-graphic-btn");
            if (exportBtn) {
                exportBtn.onclick = () => {
                    const groupTitle = activeGroupName ? activeGroupName.textContent : "Game Night";
                    if (typeof window.openGraphicExportModal === 'function') {
                        window.openGraphicExportModal(recs, groupTitle);
                    }
                };
            }
        }

        async function fetchUserXml(username) {
            const lower = username.toLowerCase();
            if (collectionXmlCache[lower]) return collectionXmlCache[lower];

            const apiBase = "{{ site.api_url }}";
            const url = apiBase
                ? `/collection?username=${username}`
                : `https://boardgamegeek.com/xmlapi2/collection?username=${username}&stats=1`;

            let xmlDoc = null;
            let attempts = 0;
            const maxAttempts = 6;

            while (attempts < maxAttempts) {
                attempts++;
                try {
                    const response = await fetchApi(url);
                    const text = await response.text();
                    const parser = new DOMParser();
                    xmlDoc = parser.parseFromString(text, "text/xml");

                    // Check for API errors
                    const errors = xmlDoc.getElementsByTagName('errors');
                    if (errors.length > 0) {
                        const errMsg = errors[0].getElementsByTagName('error')[0]?.textContent || 'Unknown API error.';
                        throw new Error("BGG API Error: " + errMsg);
                    }

                    // Check for BGG 202 processing queue message
                    const messageTag = xmlDoc.getElementsByTagName('message');
                    if (messageTag.length > 0 && (messageTag[0].textContent.includes('process') || messageTag[0].textContent.includes('queue') || messageTag[0].textContent.includes('accepted'))) {
                        console.log(`BGG is processing collection for attendee ${username}. Retrying in 5s (Attempt ${attempts}/${maxAttempts})...`);
                        if (attempts < maxAttempts) {
                            await new Promise(resolve => setTimeout(resolve, 5000));
                            continue;
                        } else {
                            throw new Error("BGG is still processing collection request for " + username);
                        }
                    }

                    break; // Success
                } catch (error) {
                    console.error(`Attempt ${attempts} to fetch XML for ${username} failed:`, error);
                    if (attempts < maxAttempts) {
                        await new Promise(resolve => setTimeout(resolve, 2000));
                    } else {
                        throw error;
                    }
                }
            }

            const items = xmlDoc.getElementsByTagName('item');
            if (items.length > 0) {
                collectionXmlCache[lower] = xmlDoc;
            }
            return xmlDoc;
        }

        async function fetchUserProfile(username, userGames) {
            const lower = username.toLowerCase();
            if (attendeeProfileCache[lower]) return attendeeProfileCache[lower];

            const apiBase = "{{ site.api_url }}";
            if (!apiBase) {
                const fallback = generateFallbackProfile(userGames);
                attendeeProfileCache[lower] = fallback;
                return fallback;
            }

            try {
                const response = await fetchApi(`/profile?username=${lower}`);
                if (response.ok) {
                    const profile = await response.json();
                    attendeeProfileCache[lower] = profile;
                    return profile;
                } else if (response.status === 404) {
                    console.warn(`Profile 404 for playgroup member ${lower}, generating fallback client-side.`);
                    const fallback = generateFallbackProfile(userGames);
                    attendeeProfileCache[lower] = fallback;
                    return fallback;
                } else {
                    throw new Error("HTTP " + response.status);
                }
            } catch (e) {
                console.error(`Failed to fetch taste profile for ${username}:`, e);
                const fallback = generateFallbackProfile(userGames);
                attendeeProfileCache[lower] = fallback;
                return fallback;
            }
        }

        function parseXmlGames(xmlDoc) {
            const games = [];
            const items = xmlDoc.getElementsByTagName('item');
            for (let i = 0; i < items.length; i++) {
                const id = items[i].getAttribute('objectid') || '';
                const name = items[i].getElementsByTagName('name')[0]?.textContent || 'N/A';
                const thumbnail = items[i].getElementsByTagName('thumbnail')[0]?.textContent || '';
                const image = items[i].getElementsByTagName('image')[0]?.textContent || '';
                const yearPublished = items[i].getElementsByTagName('yearpublished')[0]?.textContent || 'N/A';
                const status = items[i].getElementsByTagName('status')[0];
                let own = status && status.getAttribute('own') === '1';

                const stats = items[i].getElementsByTagName('stats')[0];
                const minPlayers = stats?.getAttribute('minplayers') || 'N/A';
                const maxPlayers = stats?.getAttribute('maxplayers') || 'N/A';
                const playingTime = stats?.getAttribute('playingtime') || 'N/A';
                const userRating = stats?.getElementsByTagName('rating')[0]?.getAttribute('value') || 'N/A';
                const bggAverage = stats?.getElementsByTagName('bayesaverage')[0]?.getAttribute('value') || 'N/A';

                games.push({
                    id: id,
                    name: name,
                    thumbnail: thumbnail || image || 'https://cf.geekdo-images.com/images/placeholder_thumb.png',
                    image: image,
                    own: own,
                    yearPublished: yearPublished === 'N/A' ? 'N/A' : parseInt(yearPublished),
                    bggRating: bggAverage === 'N/A' ? 'N/A' : parseFloat(bggAverage),
                    rating: bggAverage === 'N/A' ? null : parseFloat(bggAverage),
                    minPlayers: minPlayers === 'N/A' ? 'N/A' : parseInt(minPlayers),
                    maxPlayers: maxPlayers === 'N/A' ? 'N/A' : parseInt(maxPlayers),
                    playingTime: playingTime === 'N/A' ? 'N/A' : parseInt(playingTime),
                    userRating: userRating === 'N/A' ? 'N/A' : parseFloat(userRating)
                });
            }
            return games;
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

        async function updateGroupAnalytics() {
            const usernames = getCheckedUsernames();
            const analyticsDiv = document.getElementById("playgroup-taste-analytics");
            const emptyState = document.getElementById("analytics-empty-state");

            if (usernames.length === 0) {
                if (analyticsDiv) analyticsDiv.style.display = "none";
                if (emptyState) emptyState.style.display = "block";
                return;
            }

            if (emptyState) emptyState.style.display = "none";
            if (analyticsDiv) analyticsDiv.style.display = "block";
            document.getElementById("group-card-unique-games").textContent = "Loading...";
            document.getElementById("group-card-complexity-title").textContent = "Player Count Match";
            document.getElementById("group-card-complexity").textContent = "Loading...";
            document.getElementById("group-card-rating").textContent = "Loading...";

            try {
                const userResults = await Promise.all(usernames.map(async (u) => {
                    try {
                        const xml = await fetchUserXml(u);
                        const games = parseXmlGames(xml);
                        const profile = await fetchUserProfile(u, games);
                        return { username: u, games, profile };
                    } catch (e) {
                        console.error(`Error loading data for attendee ${u}:`, e);
                        return { username: u, games: [], profile: null };
                    }
                }));

                const uniqueGamesMap = new Map();
                let totalComplexitySum = 0;
                let attendeeComplexityCount = 0;

                const mergedMechs = {};
                const mergedCats = {};
                let profileCount = 0;

                userResults.forEach(res => {
                    if (!res.profile) return;
                    profileCount++;

                    if (res.profile.complexity_weights) {
                        const cw = res.profile.complexity_weights;
                        const wSum = (cw.Light || 0) * 1.5 + (cw["Medium-Light"] || 0) * 2.4 + (cw["Medium-Heavy"] || 0) * 3.15 + (cw.Heavy || 0) * 4.25;
                        const wTotal = (cw.Light || 0) + (cw["Medium-Light"] || 0) + (cw["Medium-Heavy"] || 0) + (cw.Heavy || 0);
                        if (wTotal > 0) {
                            totalComplexitySum += (wSum / wTotal);
                            attendeeComplexityCount++;
                        }
                    } else if (res.profile.avg_complexity) {
                        totalComplexitySum += res.profile.avg_complexity;
                        attendeeComplexityCount++;
                    }

                    if (res.profile.mech_weights) {
                        Object.entries(res.profile.mech_weights).forEach(([mech, val]) => {
                            mergedMechs[mech] = (mergedMechs[mech] || 0) + val;
                        });
                    }

                    if (res.profile.cat_weights) {
                        Object.entries(res.profile.cat_weights).forEach(([cat, val]) => {
                            mergedCats[cat] = (mergedCats[cat] || 0) + val;
                        });
                    }

                    res.games.forEach(g => {
                        if (g.own) {
                            const key = g.name.toLowerCase();
                            if (!uniqueGamesMap.has(key)) {
                                uniqueGamesMap.set(key, g);
                            }
                        }
                    });
                });

                if (profileCount > 0) {
                    Object.keys(mergedMechs).forEach(k => mergedMechs[k] = parseFloat((mergedMechs[k] / profileCount).toFixed(1)));
                    Object.keys(mergedCats).forEach(k => mergedCats[k] = parseFloat((mergedCats[k] / profileCount).toFixed(1)));
                }

                const uniqueGames = Array.from(uniqueGamesMap.values());
                const totalUniqueGamesCount = uniqueGames.length;
                const attendeeCount = usernames.length;
                const matchingPlayerCountGames = uniqueGames.filter(g => {
                    const min = parseInt(g.minPlayers);
                    const max = parseInt(g.maxPlayers);
                    return !isNaN(min) && !isNaN(max) && attendeeCount >= min && attendeeCount <= max;
                }).length;

                const bggRatedGames = uniqueGames.filter(g => g.bggRating !== 'N/A' && !isNaN(g.bggRating));
                const avgBggRating = bggRatedGames.length > 0
                    ? (bggRatedGames.reduce((sum, g) => sum + g.bggRating, 0) / bggRatedGames.length).toFixed(1)
                    : 'N/A';

                document.getElementById("group-card-unique-games").textContent = totalUniqueGamesCount;
                document.getElementById("group-card-complexity-title").textContent = `Games for ${attendeeCount} Player${attendeeCount !== 1 ? 's' : ''}`;
                document.getElementById("group-card-complexity").textContent = matchingPlayerCountGames;
                document.getElementById("group-card-rating").textContent = `${avgBggRating} ★`;

                drawPlaygroupCharts(mergedMechs, mergedCats, userResults, uniqueGames);

            } catch (e) {
                console.error("Error updating playgroup taste analytics:", e);
                document.getElementById("group-card-unique-games").textContent = "Error";
                document.getElementById("group-card-complexity").textContent = "Error";
                document.getElementById("group-card-rating").textContent = "Error";
            }
        }

        function drawPlaygroupCharts(mechs, cats, userResults, uniqueGames) {
            const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
            const textColor = isDark ? '#f8fafc' : '#0f172a';
            const mutedColor = isDark ? '#94a3b8' : '#64748b';
            const gridColor = isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(15, 23, 42, 0.08)';
            const radarBg = isDark ? 'rgba(99, 102, 241, 0.2)' : 'rgba(79, 70, 229, 0.2)';
            const radarBorder = isDark ? 'rgb(99, 102, 241)' : 'rgb(79, 70, 229)';
            const cardBg = isDark ? '#1e293b' : '#ffffff';

            const sortedMechs = Object.entries(mechs)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 8);

            const labelsMech = sortedMechs.map(item => item[0]);
            const dataMech = sortedMechs.map(item => item[1]);

            if (chartGroupMechanics) chartGroupMechanics.destroy();
            if (labelsMech.length > 0) {
                const ctxMech = document.getElementById('chart-group-mechanics').getContext('2d');
                chartGroupMechanics = new Chart(ctxMech, {
                    type: 'radar',
                    data: {
                        labels: labelsMech,
                        datasets: [{
                            label: 'Group Avg Affinity',
                            data: dataMech,
                            backgroundColor: radarBg,
                            borderColor: radarBorder,
                            pointBackgroundColor: radarBorder,
                            pointBorderColor: cardBg,
                            borderWidth: 2
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: {
                                labels: { color: textColor }
                            }
                        },
                        scales: {
                            r: {
                                angleLines: { display: true, color: gridColor },
                                grid: { color: gridColor },
                                suggestedMin: 0,
                                ticks: { backdropColor: 'transparent', color: mutedColor },
                                pointLabels: { color: textColor }
                            }
                        }
                    }
                });
            }

            const sortedCats = Object.entries(cats)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 8);

            const labelsCat = sortedCats.map(item => item[0]);
            const dataCat = sortedCats.map(item => item[1]);

            const catBg = isDark ? 'rgba(52, 211, 153, 0.7)' : 'rgba(16, 185, 129, 0.7)';
            const catBorder = isDark ? 'rgb(52, 211, 153)' : 'rgb(16, 185, 129)';

            if (chartGroupCategories) chartGroupCategories.destroy();
            if (labelsCat.length > 0) {
                const ctxCat = document.getElementById('chart-group-categories').getContext('2d');
                chartGroupCategories = new Chart(ctxCat, {
                    type: 'bar',
                    data: {
                        labels: labelsCat,
                        datasets: [{
                            label: 'Group Avg Affinity',
                            data: dataCat,
                            backgroundColor: catBg,
                            borderColor: catBorder,
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
                            x: {
                                beginAtZero: true,
                                grid: { color: gridColor },
                                ticks: { color: mutedColor }
                            },
                            y: {
                                grid: { display: false },
                                ticks: { color: mutedColor }
                            }
                        }
                    }
                });
            }

            let cLight = 0, cMedLight = 0, cMedHeavy = 0, cHeavy = 0;
            userResults.forEach(res => {
                if (res.profile) {
                    if (res.profile.complexity_weights) {
                        cLight += res.profile.complexity_weights["Light"] || 0;
                        cMedLight += res.profile.complexity_weights["Medium-Light"] || 0;
                        cMedHeavy += res.profile.complexity_weights["Medium-Heavy"] || 0;
                        cHeavy += res.profile.complexity_weights["Heavy"] || 0;
                    } else if (res.profile.avg_complexity) {
                        const comp = res.profile.avg_complexity;
                        if (comp < 2.0) cLight++;
                        else if (comp <= 2.8) cMedLight++;
                        else if (comp <= 3.5) cMedHeavy++;
                        else cHeavy++;
                    }
                }
            });

            if (chartGroupComplexity) chartGroupComplexity.destroy();
            const ctxComplexity = document.getElementById('chart-group-complexity-dist').getContext('2d');
            chartGroupComplexity = new Chart(ctxComplexity, {
                type: 'doughnut',
                data: {
                    labels: ['Light (<2.0)', 'Medium-Light (2.0-2.8)', 'Medium-Heavy (2.8-3.5)', 'Heavy (>3.5)'],
                    datasets: [{
                        data: [cLight, cMedLight, cMedHeavy, cHeavy],
                        backgroundColor: [
                            'rgba(16, 185, 129, 0.7)',
                            'rgba(59, 130, 246, 0.7)',
                            'rgba(245, 158, 11, 0.7)',
                            'rgba(236, 72, 153, 0.7)'
                        ],
                        borderColor: cardBg,
                        borderWidth: 2
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: { color: textColor }
                        }
                    }
                }
            });

            let dShort = 0, dMedium = 0, dLong = 0, dEpic = 0;
            uniqueGames.forEach(g => {
                const time = g.playingTime;
                if (time !== 'N/A' && time > 0) {
                    if (time < 30) dShort++;
                    else if (time <= 60) dMedium++;
                    else if (time <= 120) dLong++;
                    else dEpic++;
                }
            });

            const durBg = isDark ? 'rgba(99, 102, 241, 0.7)' : 'rgba(59, 130, 246, 0.7)';
            const durBorder = isDark ? 'rgb(99, 102, 241)' : 'rgb(59, 130, 246)';

            if (chartGroupDurations) chartGroupDurations.destroy();
            const ctxDurations = document.getElementById('chart-group-durations').getContext('2d');
            chartGroupDurations = new Chart(ctxDurations, {
                type: 'bar',
                data: {
                    labels: ['Short (<30m)', 'Medium (30-60m)', 'Long (60-120m)', 'Epic (>120m)'],
                    datasets: [{
                        label: 'Games Count',
                        data: [dShort, dMedium, dLong, dEpic],
                        backgroundColor: durBg,
                        borderColor: durBorder,
                        borderWidth: 1.5,
                        borderRadius: 6
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        y: {
                            beginAtZero: true,
                            grid: { color: gridColor },
                            ticks: { color: mutedColor }
                        },
                        x: {
                            grid: { display: false },
                            ticks: { color: mutedColor }
                        }
                    }
                }
            });
        }

    });
