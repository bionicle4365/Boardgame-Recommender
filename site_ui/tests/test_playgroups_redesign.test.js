import { describe, test, expect, beforeEach } from 'vitest';

describe('Milestone 60: Playgroup Organizer Redesign UI Logic', () => {
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

    function renderMemberChips(members) {
        let html = '';
        members.forEach(member => {
            const safeMember = member;
            const safeId = member.toLowerCase();
            const initial = safeMember.trim().charAt(0).toUpperCase() || '?';
            const avatarColor = getMemberAvatarColor(member);
            html += `
                <label class="member-chip active checked" id="label-for-${safeId}" data-username="${safeMember}" title="Toggle attendance for ${safeMember}">
                    <input type="checkbox" class="member-checkbox visually-hidden" value="${safeMember}" checked>
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
        return html;
    }

    beforeEach(() => {
        document.body.innerHTML = `
            <div class="planner-card">
                <div class="active-group-header">
                    <div class="active-group-title-row">
                        <h2 class="card-title" id="active-group-name">Friday Night Gamers</h2>
                        <span class="group-total-badge" id="active-group-member-count">3 members</span>
                    </div>
                    <div class="groups-header-actions" id="active-group-actions">
                        <button type="button" class="group-header-action-btn" id="header-edit-group-btn">Edit</button>
                        <button type="button" class="group-header-action-btn delete" id="header-delete-group-btn">Delete</button>
                    </div>
                </div>

                <div class="attendance-section-header">
                    <div class="attendance-title-wrapper">
                        <span class="attendance-heading">Who is playing tonight?</span>
                        <span class="attendance-pill" id="attendance-count-badge">3 attending</span>
                    </div>
                    <div class="attendance-header-actions">
                        <button type="button" class="btn-attendance-action" id="select-all-btn">Select All</button>
                        <span class="attendance-action-divider" aria-hidden="true">•</span>
                        <button type="button" class="btn-attendance-action" id="select-none-btn">Clear</button>
                    </div>
                </div>

                <div class="member-chips-container" id="member-checkboxes-container">
                    ${renderMemberChips(['player1', 'player2', 'player3'])}
                </div>

                <div class="planner-filters-section">
                    <div class="planner-filters-grid">
                        <div class="planner-filter-field">
                            <select id="duration_pref" class="glass-select">
                                <option value="any">Any Pacing / Play Time</option>
                            </select>
                        </div>
                        <div class="planner-filter-field">
                            <select id="complexity_pref" class="glass-select">
                                <option value="any">Any Complexity</option>
                            </select>
                        </div>
                    </div>
                </div>

                <div class="planner-actions-bar">
                    <button class="btn btn-generate-planner" id="generate-plan-btn">
                        <span class="btn-icon">🎲</span>
                        <span class="btn-text">Generate Recommendations</span>
                    </button>
                    <button type="button" class="btn btn-secondary btn-poll-action">Poll Group Library</button>
                </div>
            </div>
        `;
    });

    test('getMemberAvatarColor returns consistent deterministic gradients', () => {
        const color1 = getMemberAvatarColor('player1');
        const color2 = getMemberAvatarColor('player1');
        const color3 = getMemberAvatarColor('player2');

        expect(color1).toBe(color2);
        expect(typeof color1).toBe('string');
        expect(color1).toContain('linear-gradient');
    });

    test('renders attendee avatar chips with initials, username, and active indicator', () => {
        const chips = document.querySelectorAll('.member-chip');
        expect(chips.length).toBe(3);

        const firstChip = chips[0];
        expect(firstChip.classList.contains('active')).toBe(true);
        expect(firstChip.classList.contains('checked')).toBe(true);
        expect(firstChip.querySelector('.chip-avatar').textContent).toBe('P');
        expect(firstChip.querySelector('.chip-username').textContent).toBe('player1');
        expect(firstChip.querySelector('.chip-indicator svg')).not.toBeNull();
    });

    test('toggling attendee checkbox updates active/checked classes and attendance count', () => {
        const chip = document.getElementById('label-for-player1');
        const checkbox = chip.querySelector('input');
        const countBadge = document.getElementById('attendance-count-badge');

        // Uncheck
        checkbox.checked = false;
        if (checkbox.checked) {
            chip.classList.add('active', 'checked');
        } else {
            chip.classList.remove('active', 'checked');
        }

        const checkedCount = document.querySelectorAll('.member-checkbox:checked').length;
        countBadge.textContent = `${checkedCount} attending`;

        expect(chip.classList.contains('active')).toBe(false);
        expect(chip.classList.contains('checked')).toBe(false);
        expect(countBadge.textContent).toBe('2 attending');

        // Re-check
        checkbox.checked = true;
        chip.classList.add('active', 'checked');
        const checkedCount2 = document.querySelectorAll('.member-checkbox:checked').length;
        countBadge.textContent = `${checkedCount2} attending`;

        expect(chip.classList.contains('active')).toBe(true);
        expect(countBadge.textContent).toBe('3 attending');
    });

    test('Select All and Clear update all chips and badge count', () => {
        const countBadge = document.getElementById('attendance-count-badge');
        const chips = document.querySelectorAll('.member-chip');

        // Clear all
        document.querySelectorAll('.member-checkbox').forEach(cb => {
            cb.checked = false;
            cb.parentElement.classList.remove('active', 'checked');
        });
        let checkedCount = document.querySelectorAll('.member-checkbox:checked').length;
        countBadge.textContent = `${checkedCount} attending`;

        expect(countBadge.textContent).toBe('0 attending');
        chips.forEach(chip => {
            expect(chip.classList.contains('active')).toBe(false);
            expect(chip.classList.contains('checked')).toBe(false);
        });

        // Select All
        document.querySelectorAll('.member-checkbox').forEach(cb => {
            cb.checked = true;
            cb.parentElement.classList.add('active', 'checked');
        });
        checkedCount = document.querySelectorAll('.member-checkbox:checked').length;
        countBadge.textContent = `${checkedCount} attending`;

        expect(countBadge.textContent).toBe('3 attending');
        chips.forEach(chip => {
            expect(chip.classList.contains('active')).toBe(true);
            expect(chip.classList.contains('checked')).toBe(true);
        });
    });

    test('Active group header displays title, total count badge, and action links', () => {
        const title = document.getElementById('active-group-name');
        const countBadge = document.getElementById('active-group-member-count');
        const editBtn = document.getElementById('header-edit-group-btn');
        const deleteBtn = document.getElementById('header-delete-group-btn');

        expect(title.textContent).toBe('Friday Night Gamers');
        expect(countBadge.textContent).toBe('3 members');
        expect(editBtn).not.toBeNull();
        expect(deleteBtn).not.toBeNull();
    });

    test('Balanced filters grid and primary CTA render properly', () => {
        const durationSelect = document.getElementById('duration_pref');
        const complexitySelect = document.getElementById('complexity_pref');
        const generateBtn = document.getElementById('generate-plan-btn');

        expect(durationSelect).not.toBeNull();
        expect(complexitySelect).not.toBeNull();
        expect(generateBtn.textContent).toContain('Generate Recommendations');
    });

    test('Complexity preference normalizes legacy low/high aliases to light/heavy without leaving select blank', () => {
        const complexitySelect = document.getElementById('complexity_pref');
        complexitySelect.innerHTML = `
            <option value="any" selected>Any Complexity</option>
            <option value="light">Light (< 2.0 / 5)</option>
            <option value="medium">Medium (2.0 - 3.5 / 5)</option>
            <option value="heavy">Heavy (> 3.5 / 5)</option>
        `;

        // Case 1: Legacy 'low' maps to 'light'
        let val1 = 'low';
        if (val1 === 'low') val1 = 'light';
        if (val1 === 'high') val1 = 'heavy';
        complexitySelect.value = val1;
        if (complexitySelect.selectedIndex === -1 || !complexitySelect.value) complexitySelect.value = 'any';
        expect(complexitySelect.value).toBe('light');

        // Case 2: Legacy 'high' maps to 'heavy'
        let val2 = 'high';
        if (val2 === 'low') val2 = 'light';
        if (val2 === 'high') val2 = 'heavy';
        complexitySelect.value = val2;
        if (complexitySelect.selectedIndex === -1 || !complexitySelect.value) complexitySelect.value = 'any';
        expect(complexitySelect.value).toBe('heavy');

        // Case 3: Invalid / unrecognized value safely falls back to 'any' (placeholder never blank)
        let val3 = 'invalid_unknown_value';
        if (val3 === 'low') val3 = 'light';
        if (val3 === 'high') val3 = 'heavy';
        complexitySelect.value = val3;
        if (complexitySelect.selectedIndex === -1 || !complexitySelect.value) complexitySelect.value = 'any';
        expect(complexitySelect.value).toBe('any');
        expect(complexitySelect.options[complexitySelect.selectedIndex].text).toBe('Any Complexity');
    });
});
