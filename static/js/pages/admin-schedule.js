function clearInactiveRow(row) {
    row.querySelectorAll("input[type='text'], input[type='number']").forEach((field) => {
        if (!field.name.startsWith("cpu_level_")) {
            field.value = "";
        }
    });
    row.querySelectorAll("input[type='checkbox']").forEach((field) => {
        field.checked = false;
    });
    row.querySelectorAll("select").forEach((field) => {
        if (field.name.startsWith("cpu_level_source_")) {
            field.value = "manual";
        }
    });
}

function syncParticipantRows(card, teamToggleChanged = false) {
    const teamToggle = card.querySelector("[data-team-toggle]");
    const participantCountInput = card.querySelector("[data-participant-count-hidden]");
    const addParticipantButton = card.querySelector("[data-add-participant]");
    const removeParticipantButton = card.querySelector("[data-remove-participant]");
    const rows = Array.from(card.querySelectorAll("[data-participant-row]"));
    const showTeams = Boolean(teamToggle?.checked);
    let participantCount = parseInt(participantCountInput.value || "2", 10);

    if (showTeams && participantCount < 4) {
        participantCount = 4;
    }
    if (!showTeams && teamToggleChanged) {
        participantCount = 2;
    }
    if (!showTeams && participantCount < 2) {
        participantCount = 2;
    }
    participantCount = Math.max(2, Math.min(8, participantCount));
    participantCountInput.value = String(participantCount);

    rows.forEach((row, index) => {
        const active = index < participantCount;
        row.style.display = active ? "grid" : "none";

        row.querySelectorAll("[data-team-fields] input").forEach((field) => {
            field.disabled = !showTeams || !active;
            if (!showTeams) {
                field.value = "";
            }
        });

        if (!active) {
            clearInactiveRow(row);
        }
    });

    if (addParticipantButton) {
        addParticipantButton.disabled = participantCount >= 8;
    }
    if (removeParticipantButton) {
        removeParticipantButton.disabled = participantCount <= 2;
    }
    if (teamToggle) {
        const toggleChip = teamToggle.closest(".schedule-toggle-chip");
        if (toggleChip) {
            toggleChip.classList.toggle("is-active", showTeams);
        }
    }
}

function renumberBrandCards(section) {
    const startOrder = parseInt(section.dataset.startOrder || "1", 10);
    const cards = Array.from(section.querySelectorAll("[data-schedule-form]"));
    cards.forEach((card, index) => {
        const matchOrder = startOrder + index;
        const label = card.querySelector("[data-match-order-label]");
        const input = card.querySelector("[data-match-order-input]");
        if (input) {
            input.value = String(matchOrder);
        }
        if (label) {
            label.textContent = `Match ${matchOrder}`;
        }
    });
}

function wireMatchCard(card, section) {
    const teamToggle = card.querySelector("[data-team-toggle]");
    const addParticipantButton = card.querySelector("[data-add-participant]");
    const removeParticipantButton = card.querySelector("[data-remove-participant]");
    const fightTypeSelect = card.querySelector("[data-fight-type-select]");

    if (teamToggle) {
        teamToggle.addEventListener("change", () => {
            if (fightTypeSelect) {
                const tagFightTypeId = fightTypeSelect.dataset.tagFightTypeId;
                if (teamToggle.checked) {
                    card.dataset.previousFightTypeId = fightTypeSelect.value;
                    if (tagFightTypeId) {
                        fightTypeSelect.value = tagFightTypeId;
                    }
                } else if (tagFightTypeId && fightTypeSelect.value === tagFightTypeId) {
                    fightTypeSelect.value = card.dataset.previousFightTypeId || fightTypeSelect.options[0]?.value || "";
                }
            }
            syncParticipantRows(card, true);
        });
    }

    if (addParticipantButton) {
        addParticipantButton.addEventListener("click", () => {
            const countInput = card.querySelector("[data-participant-count-hidden]");
            const current = parseInt(countInput.value || "2", 10);
            if (current < 8) {
                countInput.value = String(current + 1);
                syncParticipantRows(card);
            }
        });
    }

    if (removeParticipantButton) {
        removeParticipantButton.addEventListener("click", () => {
            const countInput = card.querySelector("[data-participant-count-hidden]");
            const current = parseInt(countInput.value || "2", 10);
            if (current > 2) {
                countInput.value = String(current - 1);
                syncParticipantRows(card);
            }
        });
    }

    syncParticipantRows(card);
    if (section) {
        renumberBrandCards(section);
    }
}

function buildPickerMaps() {
    const el = document.getElementById("ssb-picker-data");
    if (!el) return {};
    const data = JSON.parse(el.textContent);
    return {
        location_id: Object.fromEntries(data.locations.map((l) => [l.name.toLowerCase(), String(l.id)])),
        ppv_id: Object.fromEntries([["", ""], ...data.ppvs.map((p) => [p.name.toLowerCase(), String(p.id)])]),
    };
}

function setPickerValidity(picker, valid) {
    picker.classList.toggle("is-invalid", !valid);
    if (valid) {
        picker.setCustomValidity("");
    } else {
        picker.setCustomValidity("Please choose a valid value from the autocomplete list.");
    }
}

function resolvePickerValue(picker, hidden, map) {
    const key = picker.value.trim().toLowerCase();
    const required = picker.dataset.pickerRequired === "true";
    if (!key) {
        if (hidden) {
            hidden.value = "";
        }
        setPickerValidity(picker, !required);
        return !required;
    }
    const id = map[key];
    const valid = id !== undefined;
    if (hidden) {
        hidden.value = valid ? id : "";
    }
    setPickerValidity(picker, valid);
    return valid;
}

function wireSharedPickers(section, maps) {
    section.querySelectorAll("[data-picker-for]").forEach((picker) => {
        const fieldName = picker.dataset.pickerFor;
        const hidden = section.querySelector(`[data-shared-field="${fieldName}"]`);
        const map = maps[fieldName] || {};

        const syncPicker = () => {
            resolvePickerValue(picker, hidden, map);
            syncBrandSharedFields(section);
        };

        picker.addEventListener("input", syncPicker);
        picker.addEventListener("change", syncPicker);
        syncPicker();
    });
}

function validateBrandPickers(section) {
    let valid = true;
    section.querySelectorAll("[data-picker-for]").forEach((picker) => {
        const fieldName = picker.dataset.pickerFor;
        const hidden = section.querySelector(`[data-shared-field="${fieldName}"]`);
        const maps = buildPickerMaps();
        const map = maps[fieldName] || {};
        valid = resolvePickerValue(picker, hidden, map) && valid;
    });
    syncBrandSharedFields(section);
    return valid;
}

function syncBrandSharedFields(section) {
    section.querySelectorAll("[data-shared-field]").forEach((source) => {
        const fieldName = source.dataset.sharedField;
        const value = source.value;
        section.querySelectorAll(`[data-shared-target='${fieldName}']`).forEach((target) => {
            target.value = value;
        });
    });
}

document.addEventListener("DOMContentLoaded", () => {
    const pickerMaps = buildPickerMaps();

    document.querySelectorAll(".schedule-brand-card").forEach((section) => {
        section.querySelectorAll("[data-schedule-form]").forEach((card) => {
            wireMatchCard(card, section);
            card.addEventListener("submit", (event) => {
                if (!validateBrandPickers(section)) {
                    event.preventDefault();
                    section.querySelector("[data-picker-for].is-invalid")?.focus();
                }
            });
        });

        wireSharedPickers(section, pickerMaps);

        syncBrandSharedFields(section);
        renumberBrandCards(section);
    });

    document.querySelectorAll("[data-add-match]").forEach((button) => {
        button.addEventListener("click", () => {
            const template = document.getElementById("schedule-match-card-template");
            const section = button.closest(".schedule-brand-card");
            const list = section.querySelector("[data-brand-list]");
            const fragment = template.content.cloneNode(true);
            const card = fragment.querySelector("[data-schedule-form]");
            const brandId = button.dataset.brandId;

            card.querySelector("input[name='brand_id']").value = brandId;

            list.appendChild(fragment);
            wireMatchCard(list.lastElementChild, section);
            list.lastElementChild.addEventListener("submit", (event) => {
                if (!validateBrandPickers(section)) {
                    event.preventDefault();
                    section.querySelector("[data-picker-for].is-invalid")?.focus();
                }
            });
            syncBrandSharedFields(section);
            renumberBrandCards(section);
        });
    });
});
